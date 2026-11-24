import unittest
from concurrent.futures import Future
from unittest.mock import Mock, patch
from services.research.background_refresh import BackgroundRefresh


class BackgroundRefreshTests(unittest.TestCase):
    def test_pending_request_is_never_duplicated_and_failure_preserves_value(self):
        executor=Mock();pending=Future();executor.submit.return_value=pending
        with patch('services.research.background_refresh.ThreadPoolExecutor',return_value=executor):
            refresh=BackgroundRefresh()
        self.assertEqual(refresh.poll('macro',0,lambda:1,{}),{})
        refresh.poll('macro',0,lambda:2)
        self.assertEqual(executor.submit.call_count,1)
        pending.set_result({'observation':'original'})
        failure=Future();executor.submit.return_value=failure
        self.assertEqual(refresh.poll('macro',0,lambda:3),{'observation':'original'})
        failure.set_exception(RuntimeError('secret must not be displayed'))
        self.assertEqual(refresh.poll('macro',0,lambda:4),{'observation':'original'})
        self.assertEqual(refresh.errors['macro'],'RuntimeError')
        refresh.close();executor.shutdown.assert_called_once_with(wait=False,cancel_futures=True)


if __name__=='__main__':unittest.main()
