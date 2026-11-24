import unittest
from unittest.mock import Mock
from services.research.gold_context_cache import ContextCache


class ContextCacheTests(unittest.TestCase):
    def test_runner_uses_distinct_analysis_and_exit_cache_bindings(self):
        import ast
        from pathlib import Path
        tree = ast.parse(Path('run_gold_consensus_bot.py').read_text(encoding='utf-8-sig'))
        bindings = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                fn = node.value.func
                if isinstance(fn, ast.Name) and fn.id in ('ContextCache', 'ExitContextCache'):
                    bindings[fn.id] = {target.id for target in node.targets if isinstance(target, ast.Name)}
        self.assertTrue(bindings['ContextCache'])
        self.assertTrue(bindings['ExitContextCache'])
        self.assertTrue(bindings['ContextCache'].isdisjoint(bindings['ExitContextCache']))

    def test_context_reused_until_expiry_and_isolated_from_mutation(self):
        cache = ContextCache()
        fetch = Mock(return_value={'blocks': []})
        first = cache.get('candle', fetch, now=10., ttl=5.)
        first['blocks'].append('not cached')
        self.assertEqual(cache.get('candle', fetch, now=14.9, ttl=5.)['blocks'], [])
        self.assertEqual(fetch.call_count, 1)
        cache.get('candle', fetch, now=15., ttl=5.)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(cache.hits, 1)
        self.assertEqual(cache.misses, 2)

    def test_expired_fetch_failure_never_returns_stale_value(self):
        cache = ContextCache()
        cache.get('context', lambda: {}, now=10., ttl=5.)
        with self.assertRaises(RuntimeError):
            cache.get('context', Mock(side_effect=RuntimeError('offline')), now=15., ttl=5.)
