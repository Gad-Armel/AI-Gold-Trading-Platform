from __future__ import annotations

import argparse
import unittest
from datetime import datetime, timedelta, timezone

from tools.update_gold_institutional_context import build_context


class GoldInstitutionalContextToolTests(unittest.TestCase):
    def test_context_requires_provenance_and_preserves_point_in_time_values(self) -> None:
        args = argparse.Namespace(
            source="World Gold Council monthly release",
            observed_at=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            central_bank_net_tonnes=42.0, etf_net_tonnes=-7.0,
            managed_money_net_change_4w=12000.0, managed_money_percentile_52w=0.7,
        )
        payload = build_context(args)
        self.assertEqual(payload["central_bank_net_tonnes_change"], 42.0)
        self.assertEqual(payload["usage"], "SWING_CONTEXT_ONLY")
        self.assertTrue(payload["source"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
