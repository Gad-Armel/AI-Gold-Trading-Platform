"""Publication-aware source fusion. External text is data, never instructions."""
import hashlib
import json
import math
import re
from html import unescape
from dateutil.tz import gettz
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from services.utils.atomic_json import atomic_write_json

SOURCES = {
    'bls_cpi': ('https://www.bls.gov/feed/cpi.rss', 60),
    'bls_employment': ('https://www.bls.gov/feed/empsit.rss', 60),
    'ny_fed_funding': ('https://markets.newyorkfed.org/api/rates/all/latest.json', 1800),
}


def utc(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        try:
            result = parsedate_to_datetime(str(value))
        except (ValueError, TypeError, OverflowError):
            return None
    return result.astimezone(timezone.utc) if result.tzinfo is not None else None


def parse_release_time(payload):
    text = unescape(re.sub(r'<[^>]+>', ' ', payload.decode('utf-8', errors='replace')))
    text = re.sub(r'\s+', ' ', text)
    match = re.search(r'embargoed until\s+(\d{1,2}):(\d{2})\s*([ap])\.?m\.?\s*\(ET\)\s*\w+,\s*([A-Za-z]+ \d{1,2}, \d{4})', text, re.I)
    if not match:
        raise ValueError('BLS release time not verified in official header')
    hour, minute = int(match[1]), int(match[2])
    if not 1 <= hour <= 12 or not 0 <= minute < 60:
        raise ValueError('Invalid release clock')
    zone = gettz('America/New_York')
    if zone is None:
        raise ValueError('New York timezone unavailable')
    date = datetime.strptime(match[4], '%B %d, %Y')
    return date.replace(hour=hour % 12+(12 if match[3].lower() == 'p' else 0), minute=minute,
                        tzinfo=zone).astimezone(timezone.utc)


def parse_bls(payload, source, now, resolve_time=None):
    """Only recognize the official release; do not invent a forecast surprise."""
    tree = ElementTree.fromstring(payload)
    atom = '{http://www.w3.org/2005/Atom}'
    if tree.tag == atom+'feed':
        items = [dict(title=e.findtext(atom+'title'), date=e.findtext(atom+'published') or e.findtext(atom+'updated'),
                      link=next((x.get('href') for x in e.findall(atom+'link') if x.get('rel', 'alternate') == 'alternate'), ''))
                 for e in tree.findall(atom+'entry')]
    elif tree.tag == 'rss' and tree.find('channel') is not None:
        items = [dict(title=e.findtext('title'), date=e.findtext('pubDate'), link=e.findtext('link')) for e in tree.findall('.//item')]
    else:
        raise ValueError('Expected BLS Atom or RSS feed')
    if not items:
        raise ValueError('BLS feed contains no publication entries')
    events, unverified = [], []
    for item in items:
        title = item.get('title') or ''
        feed_time = utc(item.get('date'))
        link = item.get('link') or ''
        url = urlparse(link)
        expected = 'cpi' if source == 'bls_cpi' else 'empsit'
        if (feed_time is None or not 0 <= (now-feed_time).total_seconds() <= 21600
                or url.scheme != 'https' or url.hostname != 'www.bls.gov'
                or not (url.path.startswith('/news.release/'+expected+'.')
                        or url.path.startswith('/news.release/archives/'+expected+'_'))):
            continue
        try:
            if resolve_time is None:
                raise ValueError('Official header resolver unavailable')
            published = resolve_time(link)
            if published.tzinfo is None:
                raise ValueError('Release timezone missing')
        except Exception as error:
            unverified.append(dict(url=link, feed_timestamp=feed_time.isoformat(), error=type(error).__name__))
            continue
        if not 0 <= (now-published).total_seconds() <= 21600:
            continue
        events.append(dict(title='US CPI Inflation' if expected == 'cpi' else 'US Nonfarm Payrolls',
            currency='USD', impact='HIGH', event_time=published.isoformat(), enabled=True,
            source='OFFICIAL_BLS_RSS', provider='U.S. Bureau of Labor Statistics',
            external_id=f'BLS:{expected}:{published.isoformat()}',
            calendar_confidence='VERIFIED', actual=None, forecast=None, previous=None,
            comparison_basis='NONE', directional_quality=0., reaction_eligible=True,
            feed_timestamp=feed_time.isoformat(), timestamp_basis='VERIFIED_RELEASE_HEADER',
            source_url=link, source_title=title[:300]))
    return dict(events=events, role='PUBLICATION_DETECTION_ONLY', feed_entries=len(items),
                unverified_recent_releases=unverified)


def parse_funding(payload, now):
    data = json.loads(payload)
    rows = {r.get('type'): r for r in data.get('refRates', []) if isinstance(r, dict)}
    sofr, effr = rows.get('SOFR', {}), rows.get('EFFR', {})
    date = sofr.get('effectiveDate')
    if not date or date != effr.get('effectiveDate'):
        raise ValueError('Funding observations have mismatched dates')
    observation = datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    a, b = float(sofr['percentRate']), float(effr['percentRate'])
    if not all(math.isfinite(v) for v in (a, b)) or not 0 <= (now-observation).total_seconds() <= 5*86400:
        raise ValueError('Stale, future or nonfinite funding data')
    return dict(effective_date=date, sofr_percent=a, effr_percent=b,
                sofr_minus_effr_bps=round((a-b)*100, 6),
                role='DAILY_FUNDING_CONTEXT_ONLY', gold_direction=None,
                note='Different secured/unsecured markets; this spread is not a gold entry or exit signal.')


def fetch_source(name, *, timeout=5., now=None, root='data/research/gold_source_observations', fetch=None):
    now = now or datetime.now(timezone.utc)
    url = SOURCES[name][0]
    def read_url(target_url, seconds):
        with urlopen(Request(target_url, headers={'User-Agent': 'GoldSourceResearch/1.0',
                'Accept': 'application/rss+xml, application/json'}), timeout=seconds) as response:
            if response.geturl() != target_url:
                raise ValueError('Unexpected source redirect')
            body = response.read(1000001)
            if len(body) > 1000000:
                raise ValueError('Source response too large')
            return body
    reader = fetch or read_url
    payload = reader(url, timeout)
    if len(payload) > 1000000:
        raise ValueError('Source response too large')
    def resolve_time(link):
        path = Path(root)/'release_times'/(hashlib.sha256(link.encode()).hexdigest()+'.json')
        if path.exists():
            cached = json.loads(path.read_text(encoding='utf-8'))
            stamp = utc(cached.get('release_time'))
            if stamp is not None and cached.get('url') == link:
                return stamp
        stamp = parse_release_time(reader(link, timeout))
        atomic_write_json(path, dict(url=link, release_time=stamp.isoformat(), retrieved_at=now.isoformat()), indent=2)
        return stamp
    parsed = parse_bls(payload, name, now, resolve_time) if name.startswith('bls_') else parse_funding(payload, now)
    result = dict(parser_version=2, source=name, url=url, retrieved_at=now.isoformat(),
                  payload_sha256=hashlib.sha256(payload).hexdigest(), **parsed)
    target = Path(root)/name
    target.mkdir(parents=True, exist_ok=True)
    # Content-addressed observations preserve first retrieval and later revisions.
    observation_path = target/(result['payload_sha256']+'-v2.json')
    if not observation_path.exists():
        atomic_write_json(observation_path, result, indent=2)
    atomic_write_json(target/'latest.json', result, indent=2)
    return result


def source_status(values, errors, now=None):
    now = now or datetime.now(timezone.utc)
    statuses, events, funding = {}, [], {}
    for name, (_, cadence) in SOURCES.items():
        value = values.get(name) or {}
        stamp = utc(value.get('retrieved_at'))
        age = (now-stamp).total_seconds() if stamp else None
        fresh = age is not None and 0 <= age <= max(180, cadence*2)
        statuses[name] = dict(available=fresh and name not in errors,
            status='ERROR' if name in errors else 'PENDING_OR_STALE' if not fresh else 'RELEASE_TIME_UNVERIFIED' if value.get('unverified_recent_releases') else 'CURRENT',
            unverified_recent_releases=value.get('unverified_recent_releases', []),
            error=errors.get(name), age_seconds=age, url=SOURCES[name][0])
        if not fresh:
            continue
        # A failed refresh does not erase a still-recent verified publication.
        events.extend(value.get('events', []))
        if name == 'ny_fed_funding':
            effective = utc(str(value.get('effective_date'))+'T00:00:00+00:00')
            if effective and 0 <= (now-effective).total_seconds() <= 5*86400:
                funding = value
    return dict(providers=statuses, events=events, funding=funding)


def merge_publication_risk(news_risk, events, now=None):
    """Recent verified high-impact publications supplement calendar protection."""
    now = now or datetime.now(timezone.utc)
    result = dict(news_risk, block_reasons=list(news_risk.get('block_reasons', [])),
                  active_events=list(news_risk.get('active_events', [])))
    seen = set()
    for event in events:
        stamp = utc(event.get('event_time'))
        identity = (event.get('title'), event.get('event_time'))
        if (identity in seen or stamp is None or not 0 <= (now-stamp).total_seconds() <= 300
                or event.get('calendar_confidence') != 'VERIFIED' or event.get('impact') != 'HIGH'
                or not str(event.get('source', '')).startswith('OFFICIAL_')
                or not event.get('reaction_eligible')):
            continue
        seen.add(identity)
        result['allowed'] = False
        result['active_events'].append(event)
        result['block_reasons'].append('Fresh official release protection: '+event['title'])
    return result
