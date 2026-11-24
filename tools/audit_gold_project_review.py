"""Read-only source inventory and protected-file verification; no broker connection."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import gold_consensus_settings as settings


def audit():
    paths = set(ROOT.glob("*.py"))
    for folder in ("config", "services", "tools", "vfinal", "tests", "mql5"):
        paths.update(path for path in (ROOT / folder).rglob("*") if path.suffix in (".py", ".mq5", ".mqh", ".ps1", ".js", ".cjs"))
    inventory, syntax_errors, order_calls = [], [], []
    for path in sorted(paths):
        content = path.read_bytes()
        relative = path.relative_to(ROOT).as_posix()
        inventory.append(dict(path=relative, bytes=len(content), sha256=hashlib.sha256(content).hexdigest()))
        if path.suffix != ".py":
            continue
        try:
            tree = ast.parse(content.decode("utf-8-sig"), filename=relative)
        except (SyntaxError, UnicodeError) as error:
            syntax_errors.append(dict(path=relative, error=str(error)))
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "order_send":
                order_calls.append(dict(path=relative, line=node.lineno))
    baseline_path = ROOT / "data/research/project_cleanup/inventory_before.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    protected = [item for item in baseline["files"] if item["category"] == "protected_advisor1"]
    mismatches = [item["path"] for item in protected if not (ROOT / item["path"]).is_file()
                  or hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest() != item["sha256"]]
    versions = {}
    for name in ("numpy", "pandas", "scikit-learn", "MetaTrader5", "pytest", "pyarrow"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    native_source = (ROOT / "mql5/Experts/GoldScalpAI/GoldScalpAI.mq5").read_text(encoding="utf-8-sig")
    return dict(
        generated_at=datetime.now(timezone.utc).isoformat(), orders_sent=False, mt5_connection_attempted=False,
        source_files=len(inventory), syntax_errors=syntax_errors, python_order_send_sites=order_calls,
        protected_advisor1_files=len(protected), protected_advisor1_mismatches=mismatches,
        environment=dict(python=sys.version, executable=sys.executable, packages=versions),
        python_policy=dict(max_positions=settings.MAX_POSITION_SLOTS, fixed_lot=settings.LOT_SIZE,
                           extended_position_evidence=settings.SCALP_EXTENDED_POSITION_EVIDENCE,
                           loop_target_seconds=settings.LOOP_INTERVAL_SECONDS,
                           session_loss_stop_enabled=settings.SESSION_LOSS_STOP_ENABLED,
                           scalp=settings.HORIZON_LANES["SCALP"]),
        native_source_version=re.search(r'#property version\s+"([^"]+)"', native_source).group(1),
        inventory=inventory,
        limitations=["Syntax parsing and hashes do not establish trading correctness or profitability.",
                     "This inventories project source; it does not attest to the installed/running MT5 binary.",
                     "Account state, credentials, .env and live broker history are not read by this tool."],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/research/review_20261015/project_audit.json")
    args = parser.parse_args()
    result = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    validation = dict(generated_at=result['generated_at'], advisor1_protected_files=result['protected_advisor1_files'],
                      advisor1_mismatches=result['protected_advisor1_mismatches'], python_syntax_errors=result['syntax_errors'],
                      test_reports={}, native_compilation={}, orders_sent=False, native_deployed=False,
                      javascript_tests="Not run: Node.js is unavailable; dashboard JavaScript was not changed.")
    for name in ('pytest', 'targeted'):
        path = args.output.parent / (name + '.xml')
        if not path.exists():
            continue
        root = ET.parse(path).getroot()
        suites = list(root.iter('testsuite'))
        failures = [dict(suite=case.get('classname'), test=case.get('name'))
                    for case in root.iter('testcase') if case.find('failure') is not None or case.find('error') is not None]
        validation['test_reports'][name] = dict(
            tests=sum(int(suite.get('tests', 0)) for suite in suites),
            failures=sum(int(suite.get('failures', 0)) for suite in suites),
            errors=sum(int(suite.get('errors', 0)) for suite in suites),
            skipped=sum(int(suite.get('skipped', 0)) for suite in suites),
            failed_cases=failures)
    for name in ('GoldScalpAI', 'GoldScalpSelfTest', 'GoldScalpDashboardPreview', 'GoldScalpNewsFeed', 'GoldScalpNewsBridge'):
        path = ROOT / 'mql5/validation' / (name + '.compile.log')
        if path.exists():
            content = path.read_bytes()
            summary = re.findall(r'Result: [^\r\n]+', content.decode('utf-16' if content.startswith(b'\xff\xfe') else 'utf-8-sig', errors='replace'))
            validation['native_compilation'][name] = summary[-1] if summary else 'No result line'
    tester_log = ROOT / '.mt5-validation/Tester/logs/20261015.log'
    if tester_log.exists():
        content = tester_log.read_bytes()
        matches = re.findall(r'GOLD_SELF_TEST checks=(\d+) failures=(\d+)', content.decode('utf-16' if content.startswith(b'\xff\xfe') else 'utf-8-sig', errors='replace'))
        if matches:
            checks, failures = matches[-1]
            validation['native_selftest'] = dict(checks=int(checks), failures=int(failures), mode='isolated mathematical tester; no broker orders')
    started = datetime(2026, 10, 15, 6, 47, 24, tzinfo=timezone.utc)
    validation['review_started_utc'] = started.isoformat()
    validation['review_elapsed_seconds'] = round((datetime.now(timezone.utc) - started).total_seconds(), 1)
    validation['minimum_requested_review_seconds'] = 1800
    validation['minimum_duration_reached'] = validation['review_elapsed_seconds'] >= 1800
    (args.output.parent / 'validation.json').write_text(json.dumps(validation, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key != "inventory"}, indent=2))
    return int(bool(result["syntax_errors"] or result["protected_advisor1_mismatches"]))


if __name__ == "__main__":
    raise SystemExit(main())
