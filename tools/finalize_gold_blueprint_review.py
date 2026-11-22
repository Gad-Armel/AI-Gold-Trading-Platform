"""Assemble completed review evidence; no broker/trading access."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
review = ROOT/'data/research/blueprint_review_20261009'
manifest_path = review/'review_manifest.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
capture = ROOT/manifest['observation_folder']
summary = json.loads((capture/'summary.json').read_text(encoding='utf-8'))
constraints = json.loads((capture/'constraints_audit.json').read_text(encoding='utf-8'))
execution = json.loads((capture/'execution_quality.json').read_text(encoding='utf-8'))
broker = json.loads((review/'live_broker_audit.json').read_text(encoding='utf-8'))
now = datetime.now(timezone.utc)
elapsed = (now-datetime.fromisoformat(manifest['review_started_at'])).total_seconds()/60
if elapsed < 60 or summary['minutes'] < 60:
    raise RuntimeError('The requested review and monitoring hour are not complete')
hashes = {path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
          for path in manifest['source_sha256']}
manifest.update(review_completed_at=now.isoformat(), actual_review_minutes=round(elapsed,2),
    monitor_minutes=summary['minutes'], final_tests_passed=168,
    runtime_source_hashes_unchanged=hashes == manifest['source_sha256'],
    final_source_sha256=hashes)
manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
section = '\n## Completed one-hour live observation\n\n'
section += (f"Review completed at {now:%H:%M:%S} UTC after {elapsed:.2f} minutes. "
    f"The read-only broker capture covered {summary['minutes']:.2f} minutes, "
    f"from {summary['started_at']} through {summary['latest_at']}, with "
    f"{summary['observations']} observations.\n\n")
section += (f"**This observation window lost money:** realized/balance change "
    f"${summary['balance_change']:.2f}; realized plus floating/equity change "
    f"${summary['equity_change']:.2f}. Maximum observed equity drawdown was "
    f"${summary['maximum_equity_drawdown']:.2f}. There were {summary['wins']} "
    f"winning and {summary['losses']} losing closed positions; gross gains "
    f"${summary['gross_gains']:.2f}, gross losses ${summary['gross_losses']:.2f}, "
    f"PF {summary['profit_factor']}. The window includes positions already open "
    "at its start and multiple engineering versions. These are observed outcomes, "
    "not a causal comparison of those versions.\n\n")
section += (f"Maximum owned position count was {constraints['maximum_owned_positions']}; "
    f"{constraints['samples_at_capacity']} samples showed three positions. "
    f"Capacity violations: {constraints['capacity_violation_samples']}; "
    f"samples with missing broker SL: {len(constraints['unprotected_samples'])}; "
    f"unexpected volumes: {len(constraints['unexpected_volume_samples'])}; "
    f"mixed-direction baskets: {constraints['mixed_direction_samples']}; "
    f"secondary-lane positions: {len(constraints['secondary_position_samples'])}. "
    "Ten-second sampling cannot certify all intervening ticks or guarantee "
    "stop fills at their requested price.\n\n")
for kind,stats in execution['summary'].items():
    section += (f"{kind}: {stats['confirmed_deals']} confirmed returned deals, "
        f"median order_send {stats['median_order_send_ms']:.2f} ms, "
        f"mean actual adverse price slippage {stats['mean_actual_adverse_price_slippage']:.5f}, "
        f"response/history price mismatches {stats['reported_price_mismatches']}.\n\n")
section += ("One unbound offline test journal record is explicitly excluded from actual "
    "fill statistics; that test now mocks its journal. No user journal was deleted.\n\n")
cohort = broker['cohorts']['scalp_only']
section += (f"The separate broader SCALP-only cohort, audited at {broker['as_of']}, "
    f"had {cohort['closed_trades']} closed tickets, net ${cohort['net']:.2f} "
    f"and PF {cohort['profit_factor']:.3f}. Its earlier positive snapshots must "
    "not be substituted for the negative review-hour result. Both are small, "
    "overlapping descriptive samples. Neither establishes a profitable edge.\n\n")
section += ("The final bot remains running on DEMO with SCALP-only execution. "
    "No failed detector was enabled and no calibrated probability was invented. "
    "Predictive entry improvement remains unproven. Evidence: the capture "
    "folder's summary.json, constraints_audit.json, execution_quality.json, "
    "entry_context_audit.json and performance.png; review_manifest.json preserves "
    "the completed duration and source hashes.\n")
report_path = review/'REVIEW.md'
report = report_path.read_text(encoding='utf-8').split('\n## Completed one-hour live observation')[0]
report_path.write_text(report+section,encoding='utf-8')
print(json.dumps({key:manifest[key] for key in ('review_completed_at','actual_review_minutes',
    'monitor_minutes','runtime_source_hashes_unchanged')},indent=2))
