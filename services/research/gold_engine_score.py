"""Per-engine paper evidence; never authorizes broker trading."""
from collections import deque
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class EngineScoreConfig:
    window: int = 20
    prior_count: int = 5
    minimum_results: int = 8
    pause_below: float = -.05
    resume_above: float = .05
    pause_seconds: float = 72*3600.
    minimum_new_results: int = 3

    def __post_init__(self):
        if (type(self.window) is not int or type(self.prior_count) is not int or
                type(self.minimum_results) is not int or type(self.minimum_new_results) is not int or
                not 1 <= self.minimum_results <= self.window <= 1000 or self.prior_count < 0 or
                not 1 <= self.minimum_new_results <= self.window or
                not all(math.isfinite(value) for value in (self.pause_below, self.resume_above, self.pause_seconds)) or
                self.pause_below >= self.resume_above or self.pause_seconds <= 0):
            raise ValueError('Invalid paper engine score policy')


class EngineScore:
    def __init__(self, config=EngineScoreConfig()):
        self.config = config
        self.results = deque(maxlen=config.window)
        self.seen = set()
        self.state = 'PAPER_ACTIVE'
        self.paused_at = None
        self.new_results = 0
        self.last_observed_at = None

    def observe(self, result_id, net_r, *, now):
        if not result_id or not math.isfinite(net_r) or not math.isfinite(now):
            raise ValueError('A unique closed result and finite net R/clock are required')
        if self.last_observed_at is not None and now < self.last_observed_at:
            raise ValueError('Paper outcomes must be processed chronologically')
        if result_id in self.seen:
            return self.report(now=now)
        self.seen.add(result_id)
        self.last_observed_at = now
        self.results.append(float(net_r))
        if self.state == 'PAPER_PAUSED':
            self.new_results += 1
        score = sum(self.results)/(len(self.results)+self.config.prior_count)
        if len(self.results) >= self.config.minimum_results:
            if self.state != 'PAPER_PAUSED' and score < self.config.pause_below:
                self.state, self.paused_at, self.new_results = 'PAPER_PAUSED', now, 0
            elif (self.state == 'PAPER_PAUSED' and self.new_results >= self.config.minimum_new_results
                  and score > self.config.resume_above):
                self.state, self.paused_at = 'PAPER_ACTIVE', None
        return self.report(now=now)

    def report(self, *, now):
        if not math.isfinite(now) or (self.last_observed_at is not None and now < self.last_observed_at):
            raise ValueError('Invalid score observation clock')
        expired = self.paused_at is not None and now-self.paused_at >= self.config.pause_seconds
        return dict(state='PAPER_REVIEW_DUE' if expired else self.state,
            results=len(self.results), net_r_sum=sum(self.results),
            shrunk_mean_r=sum(self.results)/(len(self.results)+self.config.prior_count),
            paused_at=self.paused_at, review_due_at=self.paused_at+self.config.pause_seconds
                if self.paused_at is not None else None,
            new_paper_results_since_pause=self.new_results,
            execution_enabled=False, calibrated_probability=None,
            reason='Expiry requests review; elapsed time alone cannot prove recovery')
