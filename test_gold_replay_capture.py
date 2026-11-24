import json
from pathlib import Path
import tempfile
import unittest
from tools.replay_gold_entry_coordination import freeze_capture


class ReplayCaptureTests(unittest.TestCase):
    def test_prospective_cutoff_excludes_old_observation_and_old_status(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            rows=[]
            for observed,updated in ((0,0),(15,0),(30,15),(45,45)):
                rows.append(json.dumps(dict(observed_at=f'2026-10-08T12:00:{observed:02d}+00:00',
                    candles={},status=dict(updated_at=f'2026-10-08T12:00:{updated:02d}+00:00')))+'\n')
            (folder/'observations.jsonl').write_text(''.join(rows),encoding='utf-8')
            frozen,metadata=freeze_capture(folder,start_utc='2026-10-08T12:00:15+00:00')
            self.assertEqual(len(frozen),2)
            self.assertEqual(metadata['first'],'2026-10-08T12:00:30+00:00')
            self.assertEqual(metadata['excluded_before_cutoff'],2)
            with self.assertRaises(ValueError):
                freeze_capture(folder,start_utc='2026-10-08T12:00:15')

    def row(self,second):
        return json.dumps(dict(observed_at=f'2026-10-08T12:00:{second:02d}+00:00',candles={},status={}))+'\n'

    def test_append_cannot_change_previously_frozen_pair_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            path=folder/'observations.jsonl'
            path.write_text(self.row(0)+self.row(15),encoding='utf-8')
            frozen,metadata=freeze_capture(folder)
            with path.open('a',encoding='utf-8') as handle:
                handle.write(self.row(30))
            later,later_metadata=freeze_capture(folder)
            self.assertEqual(len(frozen),2)
            self.assertEqual(metadata['last'],'2026-10-08T12:00:15+00:00')
            self.assertEqual(len(later),3)
            self.assertNotEqual(metadata['sha256'],later_metadata['sha256'])

    def test_partial_trailing_write_is_excluded_but_complete_corruption_raises(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            path=folder/'observations.jsonl'
            path.write_text(self.row(0)+'{"observed_at":',encoding='utf-8')
            frozen,metadata=freeze_capture(folder)
            self.assertEqual(len(frozen),1)
            self.assertEqual(metadata['complete_observations'],1)
            path.write_text(self.row(0)+'invalid complete record\n',encoding='utf-8')
            with self.assertRaises(json.JSONDecodeError):
                freeze_capture(folder)


if __name__=='__main__':
    unittest.main()
