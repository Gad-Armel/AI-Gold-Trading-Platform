"""Bounded, process-local de-duplication of confirmed entry setup events.

The caller supplies a market event identity, e.g. the closed S5 breakout/retest
bar plus its structural level. A loop timestamp is not a market event identity.
Reported order acceptance is not a confirmed fill; only reconciled deal history
may call ``record_fill(..., confirmed=True)``. This module never sends orders.
"""
from collections import OrderedDict


class EntryEpisodeGuard:
    def __init__(self, maximum=200):
        if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 200:
            raise ValueError('Episode history limit must be an integer from 1 to 200')
        self.maximum = maximum
        self._filled = OrderedDict()

    @staticmethod
    def _key(setup_id, direction):
        if (not isinstance(setup_id, str) or not setup_id.strip() or len(setup_id) > 256
                or direction not in ('BUY', 'SELL')):
            return None
        return setup_id, direction

    def blocks(self, setup_id, direction):
        key = self._key(setup_id, direction)
        if key is None:
            return ['A valid market setup identity and direction are required.']
        if key in self._filled:
            return ['This market setup already produced a confirmed entry; wait for a new event.']
        return []

    def allowed(self, setup_id, direction):
        return not self.blocks(setup_id, direction)

    def record_fill(self, setup_id, direction, *, deal_id, confirmed=False):
        key = self._key(setup_id, direction)
        if key is None:
            raise ValueError('Valid market setup identity and direction required')
        if (confirmed is not True or isinstance(deal_id, bool)
                or not isinstance(deal_id, int) or deal_id <= 0):
            raise ValueError('Reconciled confirmed fill and positive broker deal ID required')
        # A repeated broker read is idempotent and does not extend retention.
        if key not in self._filled:
            self._filled[key] = deal_id
            while len(self._filled) > self.maximum:
                self._filled.popitem(last=False)

    def snapshot(self):
        return dict(maximum=self.maximum, filled_setup_count=len(self._filled),
                    retained=[dict(setup_id=key[0], direction=key[1], deal_id=deal)
                              for key, deal in self._filled.items()])

    def restore(self, snapshot):
        """Restore a validated snapshot atomically; caller verifies account identity."""
        if not isinstance(snapshot, dict):
            raise ValueError('Episode snapshot must be an object')
        maximum = snapshot.get('maximum')
        retained = snapshot.get('retained')
        count = snapshot.get('filled_setup_count')
        if (isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 200
                or not isinstance(retained, list) or len(retained) > maximum
                or isinstance(count, bool) or not isinstance(count, int) or count != len(retained)):
            raise ValueError('Invalid episode history limit or retained count')
        restored = OrderedDict()
        for row in retained:
            if not isinstance(row, dict) or set(row) != {'setup_id', 'direction', 'deal_id'}:
                raise ValueError('Invalid retained episode record')
            key = self._key(row['setup_id'], row['direction'])
            deal = row['deal_id']
            if (key is None or key in restored or isinstance(deal, bool)
                    or not isinstance(deal, int) or deal <= 0):
                raise ValueError('Invalid or duplicate retained episode identity/fill')
            restored[key] = deal
        self.maximum = maximum
        self._filled = restored
