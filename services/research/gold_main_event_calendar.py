"""Main-only official schedule supplement; no edits to shared calendars or Advisor 1."""
import calendar
from datetime import datetime,timedelta,timezone
from html import unescape
import json
from pathlib import Path
import re
import urllib.request
from zoneinfo import ZoneInfo
from services.utils.atomic_json import atomic_write_json

CACHE_PATH='data/runtime/gold_main_event_calendar.json'


def month_url(year,month):
    return f'https://www.newyorkfed.org/research/calendars/i-{calendar.month_abbr[month].lower()}{year%100:02d}.html'


def parse_claims_calendar(html,year,month):
    if not re.search(r'>\s*'+calendar.month_name[month]+r'\s+'+str(year)+r'\s*<',html,re.I):
        raise ValueError('Official calendar month does not match requested month')
    events=[]
    for cell in re.findall(r'<td\b(?=[^>]*\bclass=["\'][^"\']*\bsomatdR\b)[^>]*>(.*?)</td>',html,re.I|re.S):
        text=re.sub(r'\s+',' ',unescape(re.sub(r'<[^>]+>',' ',cell))).strip()
        day=re.match(r'^(\d{1,2})\b',text)
        release=re.search(r'>\s*Initial Claims\s*</a>\s*<br\s*/?>\s*\((\d{1,2}):(\d{2})\)',cell,re.I)
        if not day or not release:
            continue
        eastern=datetime(year,month,int(day[1]),int(release[1]),int(release[2]),tzinfo=ZoneInfo('America/New_York'))
        utc=eastern.astimezone(timezone.utc)
        events.append(dict(title='Initial Jobless Claims',currency='USD',country='US',
            impact='MEDIUM',impact_basis='Main watch classification; source verifies schedule only',
            event_time=utc.astimezone().replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S'),
            event_time_utc=utc.isoformat(),enabled=True,source='MAIN_NYFED',
            provider='New York Fed official economic indicators calendar',
            source_url=month_url(year,month),source_detail='official_new_york_fed_schedule',
            calendar_confidence='VERIFIED',category='JOBLESS_CLAIMS'))
    if not events:
        raise ValueError('Official calendar contained no recognized claims dates')
    return events


def validate_main_calendar(data,*,now=None):
    now=now or datetime.now(timezone.utc)
    try:
        age=(now-datetime.fromisoformat(data['fetched_at'])).total_seconds()
        if not data.get('available') or not -5<=age<=86400 or not isinstance(data.get('events'),list):
            raise ValueError('Expired main-only calendar')
        return dict(data,cache_age_seconds=max(0,age))
    except (ValueError,TypeError,KeyError):
        return dict(available=False,status='NO_VALID_CACHE',events=[])


def load_main_calendar(*,now=None,path=CACHE_PATH):
    try:
        return validate_main_calendar(json.loads(Path(path).read_text(encoding='utf-8')),now=now)
    except (OSError,ValueError,TypeError):
        return dict(available=False,status='NO_VALID_CACHE',events=[])


def fetch_main_calendar(*,now=None,path=CACHE_PATH,timeout=5):
    now=now or datetime.now(timezone.utc)
    end=now+timedelta(days=14)
    months={(now.year,now.month),(end.year,end.month)}
    events=[]
    for year,month in sorted(months):
        request=urllib.request.Request(month_url(year,month),headers={'User-Agent':'GoldDemoCalendar/1.0'})
        with urllib.request.urlopen(request,timeout=timeout) as response:
            html=response.read(2_000_000).decode('utf-8',errors='replace')
        events.extend(parse_claims_calendar(html,year,month))
    events=[event for event in events if now-timedelta(days=2)<=datetime.fromisoformat(event['event_time_utc'])<=end]
    result=dict(available=True,status='OFFICIAL_SCHEDULE',fetched_at=now.isoformat(),events=events)
    atomic_write_json(path,result,indent=2)
    return result
