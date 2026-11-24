"""Short-lived context cache; never use for quotes, risk or order authority."""
from copy import deepcopy


class ContextCache:
    def __init__(self):
        self.values = {}
        self.hits = 0
        self.misses = 0

    def get(self, key, fetch, *, now, ttl):
        cached = self.values.get(key)
        if cached is None or now < cached[0] or now-cached[0] >= ttl:
            self.misses += 1
            value = fetch()
            self.values[key] = (now, deepcopy(value))
        else:
            self.hits += 1
        return deepcopy(self.values[key][1])
