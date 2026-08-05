# V6.3.2 Conservative Shadow Fills

## Why this release exists

A V6.3.1 shadow session opened an EXPLORATORY SELL and later first observed it at approximately `+$2.15`, even though the adaptive planned target could not exceed `$1.20`.

The strategy had correctly detected a target crossing, but the shadow engine credited the entire later polling quote. That can overstate expectancy because a broker-side take-profit would normally be working at the planned barrier before the next Python poll.

## Fill policy

### Profitable target crossing

```text
final_profit_usd = planned target_profit_usd
observed_market_profit_usd = P/L at the newly observed executable quote
barrier_overshoot_usd = observed_market_profit_usd - final_profit_usd
shadow_fill_model = PLANNED_TARGET_BARRIER
```

The simulated exit price is reconstructed with the MT5 profit calculator when available and the contract-size fallback otherwise.

### Adverse hard-stop crossing

```text
final_profit_usd = P/L at the observed executable quote
shadow_fill_model = OBSERVED_EXECUTABLE_QUOTE
```

Losses are not capped at the planned stop. This preserves conservative gap/slippage treatment.

## Why the policy is asymmetric

Crediting a later favorable polling quote can create optimistic bias. Ignoring a later adverse quote can create optimistic bias too. Therefore:

- favorable target overshoot is not credited;
- adverse stop overshoot is fully charged.

## Research impact

Older V6.3.1 history can remain in the research folder, but analysis should distinguish records without `shadow_fill_model`. New V6.3.2 records contain both planned-fill and observed-quote diagnostics.

The strategy identifier changed, so older demo approvals and trained champions are incompatible and must not be copied into V6.3.2.

## Safety status

- shadow-first;
- real-account execution disabled;
- controlled demo approval required;
- one position maximum;
- no pyramiding;
- all existing structure, spread, news and model protections retained.
