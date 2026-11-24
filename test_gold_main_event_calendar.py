import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
from services.research.gold_main_event_calendar import parse_claims_calendar,load_main_calendar,validate_main_calendar
from services.risk.news_event_filter import assess_news_event_risk


def page(month,year,day,hour='08:30'):
    return f'<div>{month} {year}</div><td class="somatdR dirColL"><div>{day}<br><a href="https://www.workforcesecurity.doleta.gov/">Initial Claims</a><br>({hour})</div></td>'


class MainCalendarTests(unittest.TestCase):
    def test_official_october_date_uses_daylight_saving_offset(self):
        event=parse_claims_calendar(page('October',2026,'08'),2026,10)[0]
        self.assertEqual(event['event_time_utc'],'2026-10-08T12:30:00+00:00')
        self.assertEqual(event['impact'],'MEDIUM')
        self.assertEqual(event['calendar_confidence'],'VERIFIED')

    def test_official_exception_date_is_not_forced_to_thursday(self):
        event=parse_claims_calendar(page('November',2026,'25'),2026,11)[0]
        self.assertEqual(event['event_time_utc'],'2026-11-25T13:30:00+00:00')

    def test_wrong_month_and_unrecognized_page_cannot_invent_events(self):
        for html in (page('September',2026,'08'),'<div>October 2026</div>'):
            with self.assertRaises(ValueError):
                parse_claims_calendar(html,2026,10)

    @patch('services.risk.news_event_filter._load_news_events',return_value=[])
    @patch('config.settings.BLOCK_MEDIUM_IMPACT_NEWS',False)
    def test_extra_verified_watch_does_not_add_an_unrequested_block(self,*_):
        event=parse_claims_calendar(page('October',2026,'08'),2026,10)[0]
        now=datetime.strptime(event['event_time'],'%Y-%m-%d %H:%M:%S')
        risk=assess_news_event_risk('XAUUSD',now,extra_events=[event])
        self.assertTrue(risk['allowed'])
        self.assertTrue(risk['active_events'][0]['verified'])
        self.assertFalse(risk['active_events'][0]['blocking'])
        self.assertEqual(assess_news_event_risk('XAUUSD',now)['active_events'],[])

    def test_expired_cache_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'calendar.json'
            path.write_text('{"fetched_at":"2026-10-01T00:00:00+00:00","events":[]}')
            self.assertFalse(load_main_calendar(path=path,now=datetime(2026,10,8,tzinfo=timezone.utc))['available'])

    def test_background_retained_value_cannot_bypass_expiry(self):
        data=dict(available=True,fetched_at='2026-10-01T00:00:00+00:00',events=[dict(title='Old')])
        result=validate_main_calendar(data,now=datetime(2026,10,8,tzinfo=timezone.utc))
        self.assertFalse(result['available'])
        self.assertEqual(result['events'],[])


if __name__=='__main__':
    unittest.main()
