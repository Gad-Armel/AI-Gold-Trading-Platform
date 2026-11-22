from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
import pandas as pd

from ..config import ensure_dirs
from ..providers.fred import build_current_context, fetch_vintage_snapshot
from ..providers.health import run_health_checks
from ..config import env_status
from ..providers.bls import health_check
from ..providers.mt5_ticks import collect_ticks
from ..data.snapshot_store import load_snapshots
from ..data.dataset import flatten_snapshot_rows, load_dataset, dataset_status, save_dataset, merge_features_labels
from ..data.labels import build_labels
from ..data.quality import annotate_file, annotate_ticks, audit_ticks
from ..model.train import train


def main() -> int:
    parser = argparse.ArgumentParser(description="XAUUSD V-FINAL research engine")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("macro")
    p_vintage = sub.add_parser("macro-vintage")
    p_vintage.add_argument("--as-of", required=True, help="ISO UTC date/time; returns the latest FRED values known at that date")
    sub.add_parser("health")
    sub.add_parser("env")
    sub.add_parser("bls-health")
    p_status = sub.add_parser("status")
    p_status.add_argument("--dataset", default=None)
    p_collect = sub.add_parser("collect-ticks")
    p_collect.add_argument("--symbol", default="XAUUSD")
    p_collect.add_argument("--start", required=True, help="ISO UTC datetime")
    p_collect.add_argument("--end", required=True, help="ISO UTC datetime")
    p_collect.add_argument("--output", default="data/raw/xauusd_ticks.csv")
    p_range = sub.add_parser("collect-range")
    p_range.add_argument("--symbol", default="XAUUSD")
    p_range.add_argument("--start", required=True)
    p_range.add_argument("--end", required=True)
    p_range.add_argument("--days", type=int, default=1)
    p_range.add_argument("--output-dir", default="data/raw/multi_day")
    p_audit = sub.add_parser("audit-ticks")
    p_audit.add_argument("--ticks", required=True)
    p_audit.add_argument("--output", default=None)
    p_ticks = sub.add_parser("build-dataset")
    p_ticks.add_argument("--ticks", required=True)
    p_ticks.add_argument("--quality-ticks", default=None)
    p = sub.add_parser("train")
    p.add_argument("--horizon", default=None)
    p.add_argument("--direction", default=None)
    p.add_argument("--dataset", default=None)
    p.add_argument("--promote", action="store_true",
                   help="Mark the artifact execution-approved only if every validation gate passes.")
    args = parser.parse_args()
    ensure_dirs()
    if args.cmd == "macro": print(json.dumps(build_current_context(), indent=2, default=str)); return 0
    if args.cmd == "macro-vintage": print(json.dumps(fetch_vintage_snapshot(args.as_of), indent=2, default=str)); return 0
    if args.cmd == "health": print(json.dumps(run_health_checks(), indent=2, default=str)); return 0
    if args.cmd == "env": print(json.dumps(env_status(), indent=2, default=str)); return 0
    if args.cmd == "bls-health": print(json.dumps(health_check(), indent=2)); return 0
    if args.cmd == "collect-range":
        from pathlib import Path
        start = datetime.fromisoformat(args.start.replace('Z','+00:00')); end = datetime.fromisoformat(args.end.replace('Z','+00:00'))
        outdir=Path(args.output_dir); outdir.mkdir(parents=True,exist_ok=True); results=[]
        cur=start
        from datetime import timedelta
        for i in range(args.days):
            nxt=min(end,cur+timedelta(days=1)); path=outdir/f'{args.symbol.lower()}_{cur.date().isoformat()}.csv'
            results.append(collect_ticks(args.symbol,cur,nxt,str(path))); cur=nxt
            if cur>=end: break
        print(json.dumps({'files':results,'days':len(results)},indent=2,default=str)); return 0
    if args.cmd == "collect-ticks":
        start = datetime.fromisoformat(args.start.replace("Z", "+00:00")); end = datetime.fromisoformat(args.end.replace("Z", "+00:00"))
        print(json.dumps(collect_ticks(args.symbol, start, end, args.output), indent=2, default=str)); return 0
    if args.cmd == "status":
        frame = load_dataset(args.dataset)
        result = dataset_status(frame)
        result["dataset"] = str(args.dataset or "data/labels/vfinal_dataset.csv")
        print(json.dumps(result, indent=2, default=str)); return 0
    if args.cmd == "audit-ticks":
        target, report = annotate_file(args.ticks, output=args.output)
        print(json.dumps({"annotated_path": str(target), **report}, indent=2, default=str)); return 0
    if args.cmd == "build-dataset":
        snapshots = load_snapshots()
        raw_ticks = pd.read_csv(args.ticks)
        if args.quality_ticks:
            ticks = pd.read_csv(args.quality_ticks)
            quality_report = audit_ticks(raw_ticks, ticks)
        else:
            ticks = annotate_ticks(raw_ticks)
            quality_report = audit_ticks(raw_ticks, ticks)
        labels = build_labels(snapshots, ticks)
        frame = merge_features_labels(snapshots, labels)
        path = save_dataset(frame)
        print(json.dumps({"path": str(path), "tick_quality": quality_report, **dataset_status(frame)}, indent=2, default=str)); return 0
    if args.cmd == "train":
        frame = load_dataset(args.dataset)
        print(json.dumps(train(frame, horizon=args.horizon, direction=args.direction,
                               promote=args.promote), indent=2, default=str)); return 0
    return 1

if __name__ == "__main__": raise SystemExit(main())
