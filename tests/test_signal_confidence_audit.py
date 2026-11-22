import unittest

import numpy as np
import pandas as pd

from tools.audit_gold_signal_confidence import episode_indices, summarize


class SignalConfidenceAuditTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame(dict(normal_entry_epoch=[0., 1., 15., 50.], normal_exit=[10., 11., 25., 60.],
                                 stress_exit=[45., 46., 60., 90.], normal_profit=[1.] * 4,
                                 stress_profit=[.5] * 4, day=["20260101"] * 4))

    def test_overlapping_observations_cannot_multiply_the_trade_count(self):
        self.assertEqual(episode_indices(self.frame(), np.ones(4), .65).tolist(), [0, 3])
        self.assertEqual(episode_indices(self.frame(), np.ones(4), .65, stress=True).tolist(), [0])

    def test_commission_is_charged_once_per_executed_episode(self):
        result = summarize(self.frame(), np.ones(4), .65, commission=.1)
        self.assertEqual(result["trades"], 2)
        self.assertAlmostEqual(result["net"], 1.8)
        self.assertIsNone(result["expectancy_day_bootstrap_95"])

    def test_invalid_probabilities_and_out_of_order_entries_fail(self):
        with self.assertRaises(ValueError):
            episode_indices(self.frame(), [float("nan")] * 4, .65)
        with self.assertRaises(ValueError):
            episode_indices(self.frame().iloc[::-1], np.ones(4), .65)
