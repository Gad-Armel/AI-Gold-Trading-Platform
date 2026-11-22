"""Resumable read-only daily quote export. Never sends broker orders."""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import MetaTrader5 as mt5
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from config import gold_consensus_settings as settings
from services.market_data.gold_broker_clock import to_broker_time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=30)
    args = parser.parse_args()
    if not 1<=args.days<=60:
        raise ValueError('Bounded export requires 1–60 days')
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end-timedelta(days=args.days)
    output = PROJECT/'data/research/entry_efficiency/historical_ticks'
    output.mkdir(parents=True, exist_ok=True)
    if not mt5.initialize():
        raise RuntimeError(mt5.last_error())
    reports = []
    try:
        day = start
        while day<end:
            name = day.strftime('%Y%m%d')
            path, meta = output/(name+'.npz'), output/(name+'.json')
            if path.exists() and meta.exists():
                report = json.loads(meta.read_text())
                if (report.get('broker_utc_offset_seconds')==settings.MT5_SERVER_UTC_OFFSET_SECONDS
                        and report.get('artifact_bytes')==path.stat().st_size):
                    reports.append(report)
                    day += timedelta(days=1)
                    continue
            rates = mt5.copy_ticks_range('XAUUSD', to_broker_time(day),
                to_broker_time(day+timedelta(days=1)), mt5.COPY_TICKS_ALL)
            if rates is None:
                report = dict(day=name, status='UNAVAILABLE', error=str(mt5.last_error()))
                reports.append(report)
                print(json.dumps(report), flush=True)
                day += timedelta(days=1)
                continue
            utc_msc = rates['time_msc']-int(settings.MT5_SERVER_UTC_OFFSET_SECONDS*1000)
            valid = (np.isfinite(rates['bid']) & np.isfinite(rates['ask']) & (rates['bid']>0)
                & (rates['ask']>=rates['bid']) & (utc_msc>=day.timestamp()*1000)
                & (utc_msc<(day+timedelta(days=1)).timestamp()*1000))
            times = utc_msc[valid]
            order = np.argsort(times, kind='stable')
            times = times[order]
            np.savez_compressed(path, utc_time_msc=times, bid=rates['bid'][valid][order],
                                ask=rates['ask'][valid][order])
            report = dict(day=name, status='EXPORTED', received_ticks=len(rates), usable_ticks=len(times),
                broker_utc_offset_seconds=settings.MT5_SERVER_UTC_OFFSET_SECONDS,
                artifact_bytes=path.stat().st_size,
                first_utc_msc=int(times[0]) if len(times) else None,
                last_utc_msc=int(times[-1]) if len(times) else None,
                maximum_gap_seconds=float(np.diff(times).max()/1000) if len(times)>1 else None)
            meta.write_text(json.dumps(report, indent=2))
            reports.append(report)
            print(json.dumps(dict(day=name, usable_ticks=len(times))), flush=True)
            day += timedelta(days=1)
        manifest = dict(start_utc=start.isoformat(), end_utc=end.isoformat(), days=reports,
                        exported_at=datetime.now(timezone.utc).isoformat())
        (output/'manifest.json').write_text(json.dumps(manifest, indent=2))
        print(json.dumps(dict(total_ticks=sum(r.get('usable_ticks', 0) for r in reports),
                              unavailable_days=sum(r['status']=='UNAVAILABLE' for r in reports))), flush=True)
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
