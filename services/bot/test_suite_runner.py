import os
import subprocess
import sys
from datetime import datetime

from config import settings


DEFAULT_TEST_SCRIPTS = [
    "test_paper_trade_system.py",
    "test_advanced_risk_engine.py",
    "test_news_event_filter.py",
    "test_ai_pipeline.py",
    "test_scalping_system.py",
    "test_scalping_next_phases.py",
    "run_system_audit.py",
    "run_scalping_audit.py",
    "run_validation_command_center.py",
    "test_live_gate_protection.py",
    "test_auto_calendar_sync.py",
]


def _get_log_folder():
    base_log_path = getattr(settings, "LOG_FILE_PATH", "logs/bot_cycle_log.csv")
    base_log_folder = os.path.dirname(base_log_path) or "logs"

    if getattr(settings, "USE_DAILY_LOG_FOLDERS", False):
        date_format = getattr(settings, "LOG_DATE_FORMAT", "%Y-%m-%d")
        today_folder = datetime.now().strftime(date_format)
        base_log_folder = os.path.join(base_log_folder, today_folder)

    os.makedirs(base_log_folder, exist_ok=True)
    return base_log_folder


def get_test_suite_report_path():
    return os.path.join(_get_log_folder(), "test_suite_report.txt")


def _run_script(script_name):
    timeout_seconds = int(getattr(settings, "RUN_TEST_TIMEOUT_SECONDS", 120))

    if not os.path.exists(script_name):
        return {
            "script": script_name,
            "passed": False,
            "return_code": None,
            "output": "",
            "error": f"Missing script: {script_name}",
        }

    try:
        result = subprocess.run(
            [sys.executable, script_name],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

        return {
            "script": script_name,
            "passed": result.returncode == 0,
            "return_code": result.returncode,
            "output": result.stdout,
            "error": result.stderr,
        }

    except subprocess.TimeoutExpired:
        return {
            "script": script_name,
            "passed": False,
            "return_code": None,
            "output": "",
            "error": f"Test timed out after {timeout_seconds} seconds.",
        }

    except Exception as error:
        return {
            "script": script_name,
            "passed": False,
            "return_code": None,
            "output": "",
            "error": str(error),
        }


def run_master_test_suite():
    scripts = list(DEFAULT_TEST_SCRIPTS)

    if getattr(settings, "RUN_MAIN_IN_TEST_SUITE", False):
        scripts.insert(0, "main.py")

    results = []

    for script in scripts:
        results.append(_run_script(script))

    passed_count = sum(1 for result in results if result["passed"])
    failed_count = len(results) - passed_count

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_tests": len(results),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "all_passed": failed_count == 0,
        "results": results,
    }


def save_master_test_suite_report():
    result = run_master_test_suite()
    report_path = get_test_suite_report_path()

    lines = []
    lines.append("=" * 70)
    lines.append("MASTER TEST SUITE REPORT")
    lines.append("=" * 70)
    lines.append(f"Generated At: {result['generated_at']}")
    lines.append(f"Total Tests: {result['total_tests']}")
    lines.append(f"Passed: {result['passed_count']}")
    lines.append(f"Failed: {result['failed_count']}")
    lines.append(f"All Passed: {result['all_passed']}")
    lines.append("=" * 70)

    for test_result in result["results"]:
        lines.append("")
        lines.append("-" * 70)
        lines.append(f"Script: {test_result['script']}")
        lines.append(f"Passed: {test_result['passed']}")
        lines.append(f"Return Code: {test_result['return_code']}")

        if test_result["error"]:
            lines.append("ERROR:")
            lines.append(test_result["error"])

        if test_result["output"]:
            lines.append("OUTPUT:")
            lines.append(test_result["output"])

    lines.append("")
    lines.append("=" * 70)
    lines.append("END OF MASTER TEST SUITE REPORT")
    lines.append("=" * 70)

    with open(report_path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))

    result["report_path"] = report_path
    return result