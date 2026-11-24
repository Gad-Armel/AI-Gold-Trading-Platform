"""Run unittest suites plus the repository's dependency-free function tests."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))


def main():
    suite=unittest.TestSuite()
    suite.addTests(unittest.TestLoader().discover(str(root),pattern='test_*.py'))
    suite.addTests(unittest.TestLoader().discover(str(root/'tests'),pattern='test_*.py'))
    spec=importlib.util.spec_from_file_location('gold_core_checks',root/'tests/test_core.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    for name in sorted(vars(module)):
        if name.startswith('test_') and callable(getattr(module,name)):
            suite.addTest(unittest.FunctionTestCase(getattr(module,name)))
    target=root/'data/research/xauusd_audit';target.mkdir(parents=True,exist_ok=True)
    with (target/'validation.txt').open('w',encoding='utf-8') as handle:
        result=unittest.TextTestRunner(stream=handle,verbosity=2).run(suite)
    summary=dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
                 skipped=len(result.skipped),passed=result.wasSuccessful())
    (target/'validation.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary))
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
