import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from tools.audit_gold_policy_outcomes import summarize


class PolicyOutcomeTests(unittest.TestCase):
    def test_prospective_cutoff_keeps_deployment_time_and_separates_carried_fills(self):
        deployment = dict(deployed_at='2026-10-08T00:00:00+00:00')
        start = '2026-10-08T00:10:00+00:00'
        trades = [dict(position_id=1, opened_at='2026-10-08T00:05:00+00:00',
                       closed_at='2026-10-08T00:11:00+00:00', profit=2.),
                  dict(position_id=2, opened_at=start,
                       closed_at='2026-10-08T00:11:00+00:00', profit=-1.)]
        status = dict(updated_at='2026-10-08T00:12:00+00:00',
                      config=dict(entry_coordination_mode='SCALP_PRIORITY'), positions=[],
                      lanes=dict(SCALP=dict(closed_trades=trades)))
        row = dict(observed_at=status['updated_at'], status=status)
        with TemporaryDirectory() as folder:
            path = Path(folder)
            (path / 'observations.jsonl').write_text(json.dumps(row) + '\n')
            result = summarize(path, deployment, start_utc=start)
            original = summarize(path, deployment)
        self.assertEqual(result['deployed_at'], deployment['deployed_at'])
        self.assertEqual(result['cohort_start_utc'], start)
        self.assertEqual(result['outcomes']['carried_entries']['realized'], 2.)
        self.assertEqual(result['outcomes']['new_entries']['realized'], -1.)
        self.assertEqual(original['outcomes']['new_entries']['realized'], 1.)

    def test_before_prospective_start_has_no_eligible_samples(self):
        with TemporaryDirectory() as folder:
            path = Path(folder)
            status = dict(updated_at='2026-10-08T00:01:00+00:00',
                          config=dict(entry_coordination_mode='SCALP_PRIORITY'))
            (path / 'observations.jsonl').write_text(json.dumps(dict(status=status)) + '\n')
            result = summarize(path, dict(deployed_at='2026-10-08T00:00:00+00:00'),
                               start_utc='2026-10-08T00:10:00+00:00')
        self.assertFalse(result['available'])


if __name__ == '__main__':
    unittest.main()
