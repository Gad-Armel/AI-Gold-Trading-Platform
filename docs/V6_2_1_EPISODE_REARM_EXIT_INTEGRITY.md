# V6.2.1 Episode Rearm and Exit Integrity

## Problem

The V6.2 shadow engine processed exits before entries, but then evaluated the entry gate again in the same function call. If a profitable position hit its target while the candidate gate remained allowed, the engine could append the close to history and immediately replace the console action with a new open. This made the console omit the close and generated serially dependent trades from one uninterrupted impulse.

## Normal exit rearm

After a target, time exit, no-progress exit, opposite-tape exit or break-even exit:

1. the position closes and no new position can open in that cycle;
2. signal persistence resets;
3. the lane waits for at least one fully invalid candidate observation;
4. only a later, newly confirmed candidate may open.

## Hard-stop thesis reset

A catastrophe hard stop means the current directional thesis was invalidated. The same lane and direction remain locked until the higher-timeframe structural consensus is no longer aligned with the stopped direction. A fresh persistence sequence must then form before a later entry.

## Safety

The rearm logic is inside the shadow state machine and contains no broker-order path. Approved demo execution already blocks same-cycle re-entry; V6.2.1 additionally resets its persistence state after a close so future approved behavior cannot reuse an old confirmation streak.
