"""Chronological executable-quote markouts; no orders, fitting or portfolio claims."""
import bisect
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def epoch(value):
    return datetime.fromisoformat(value).timestamp()


def main():
    quotes = []
    for line in (ROOT/'data/research/gold_forward/quotes_20261008.jsonl').open():
        q = json.loads(line)
        if 0 <= q['quote_age_seconds'] <= 2 and 0 < q['bid'] <= q['ask']:
            quotes.append((epoch(q['observed_at']), q['bid'], q['ask']))
    quotes.sort()
    times = [q[0] for q in quotes]
    samples = []
    for folder in sys.argv[1:]:
        last = {}
        for line in (Path(folder)/'observations.jsonl').open(encoding='utf-8'):
            row = json.loads(line)
            now = epoch(row['observed_at'])
            status = row.get('status', {})
            if now-epoch(status.get('updated_at', row['observed_at'])) > 5:
                continue
            i = bisect.bisect_left(times, now)
            if i == len(quotes) or quotes[i][0]-now > 2:
                continue
            start, bid, ask = quotes[i]
            for lane, data in status.get('lanes', {}).items():
                decision = data['decision']
                direction = decision.get('direction')
                if (not decision.get('allowed') or direction not in ('BUY', 'SELL')
                        or now-last.get(lane, 0) < 300):
                    continue
                last[lane] = now
                sample = dict(period=Path(folder).name, lane=lane, at=row['observed_at'],
                              direction=direction, evidence=decision['evidence'],
                              spread=ask-bid, markouts={})
                for delay in (60, 300, 900):
                    j = bisect.bisect_left(times, start+delay)
                    if j < len(quotes) and quotes[j][0]-start-delay <= 2:
                        _, end_bid, end_ask = quotes[j]
                        # One ounce (.01 lot * 100), executable spread plus $.10
                        # round-trip slippage; no fixed stop or adaptive exit.
                        sample['markouts'][str(delay)] = round(
                            (end_bid-ask if direction == 'BUY' else bid-end_ask)-.10, 4)
                samples.append(sample)
    report = dict(limitations=[
        'Recorded allowed signals, not actual fills or a portfolio replay.',
        'Samples spaced five minutes per lane; 15-minute outcomes overlap.',
        'Both periods were previously inspected; neither is a blind holdout.',
        'Historical signal policy changed during collection.',
        'Markouts include executable spread and $.10 round-trip slippage, but omit stops, adaptive exits, fees and financing.',
        'Future quotes are used only as labels; input decisions precede entry quotes.'], groups=[])
    for period in sorted({r['period'] for r in samples}):
        for lane in ('SCALP', 'INTRADAY', 'SWING'):
            for band in ('ALL', '85_PLUS'):
                selected = [r for r in samples if r['period'] == period and r['lane'] == lane
                            and (band == 'ALL' or r['evidence'] >= 85)]
                outcomes = {}
                for delay in ('60', '300', '900'):
                    values = [r['markouts'][delay] for r in selected if delay in r['markouts']]
                    outcomes[delay] = dict(n=len(values),
                        mean_usd=round(sum(values)/len(values), 4) if values else None,
                        positive_fraction=round(sum(v > 0 for v in values)/len(values), 4) if values else None)
                report['groups'].append(dict(period=period, lane=lane, band=band, outcomes=outcomes))
    out = ROOT/'data/research/entry_efficiency'
    out.mkdir(parents=True, exist_ok=True)
    (out/'signal_markouts.json').write_text(json.dumps(report, indent=2))
    (out/'signal_markout_samples.json').write_text(json.dumps(samples, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
