import unittest
from unittest.mock import patch

from services.risk import automatic_economic_calendar as calendar


class FreeCalendarPolicyTests(unittest.TestCase):
    def test_main_free_only_policy_never_calls_fmp_even_when_globally_enabled(self):
        with patch.object(calendar, '_fmp_calendar_enabled', return_value=True), \
                patch.object(calendar, '_free_calendar_enabled', return_value=True), \
                patch.object(calendar, '_load_sync_metadata', return_value={'fmp_calendar_enabled': True}), \
                patch.object(calendar, '_should_sync', return_value=True), \
                patch.object(calendar, 'fetch_free_official_calendar', return_value={'success': True, 'raw_events': []}) as free, \
                patch.object(calendar, '_sync_with_events', return_value={'success': True}) as save, \
                patch.object(calendar, 'fetch_fmp_calendar') as paid:
            result = calendar.sync_auto_economic_calendar(free_only=True)
            self.assertTrue(result['success'])
            free.assert_called_once()
            paid.assert_not_called()
            self.assertFalse(save.call_args.kwargs['fmp_api_call_made'])
            self.assertFalse(save.call_args.kwargs['fmp_calendar_enabled'])

    def test_provider_change_refreshes_old_paid_provider_metadata(self):
        with patch.object(calendar, '_load_sync_metadata', return_value={'fmp_calendar_enabled': True}), \
                patch.object(calendar, '_should_sync', return_value=False) as should, \
                patch.object(calendar, 'load_events', return_value=[]):
            calendar.sync_auto_economic_calendar(free_only=True)
            should.assert_called_once_with(force=True)

    def test_invalid_policy_is_not_silently_accepted(self):
        with self.assertRaises(ValueError):
            calendar.sync_auto_economic_calendar(free_only='false')
