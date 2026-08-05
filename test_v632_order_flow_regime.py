from __future__ import annotations

import unittest

from services.microstructure.feature_engine import build_microstructure_features


class V632OrderFlowRegimeTests(unittest.TestCase):
    @staticmethod
    def _ticks(direction: int) -> list[dict]:
        ticks = []
        bid = 4000.00
        ask = 4000.20
        for index in range(30):
            step = direction * 0.01 if index % 2 == 0 else direction * 0.005
            bid += step
            ask += step
            ticks.append({
                "time_msc": 1_700_000_000_000 + index * 100,
                "bid": bid,
                "ask": ask,
                "mid": (bid + ask) / 2.0,
                "spread": ask - bid,
            })
        return ticks

    def test_quote_flow_proxy_sign_matches_price_pressure(self) -> None:
        buy = build_microstructure_features("XAUUSD", self._ticks(1), m1_atr=1.0)
        sell = build_microstructure_features("XAUUSD", self._ticks(-1), m1_atr=1.0)
        self.assertGreater(buy.windows["3"].quote_flow_imbalance_proxy, 0.5)
        self.assertLess(sell.windows["3"].quote_flow_imbalance_proxy, -0.5)
        self.assertEqual(buy.micro_regime, "IMPULSE")
        self.assertEqual(sell.micro_regime, "IMPULSE")

    def test_micro_regime_is_serialized(self) -> None:
        features = build_microstructure_features("XAUUSD", self._ticks(1), m1_atr=1.0)
        payload = features.to_dict()
        self.assertIn("micro_regime", payload)
        self.assertIn("quote_flow_imbalance_proxy", payload["windows"]["3"])
        self.assertIn("arrival_acceleration", payload["windows"]["3"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
