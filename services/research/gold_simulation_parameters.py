"""Isolate mutable parameters between sequential/process-worker simulations."""
import copy


def run_isolated(simulator, baseline, overrides, callback):
    unknown = set(overrides)-set(baseline)
    if unknown:
        raise ValueError('Unknown simulation parameters: '+', '.join(sorted(unknown)))
    previous = copy.deepcopy(simulator.P)
    parameters = copy.deepcopy(baseline)
    parameters.update(copy.deepcopy(overrides))
    try:
        simulator.P = parameters
        return callback()
    finally:
        simulator.P = previous
