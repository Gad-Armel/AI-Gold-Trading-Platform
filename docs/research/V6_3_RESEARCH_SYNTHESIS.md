# V6.3 Research Synthesis

## Design conclusions

1. **Optimize net expectancy, not raw directional accuracy.** Very short-horizon strategies are highly sensitive to spread, slippage and execution timing. V6.3 retains cost-first gates and uses adaptive payoff geometry.
2. **Calibrate probabilities.** A score called “70%” is useful only if outcomes near that score actually win near 70% of the time. V6.3 measures Brier score and expected calibration error.
3. **Validate chronologically.** Random cross-validation leaks future regimes into the past. V6.3 uses expanding purged walk-forward folds.
4. **Allow abstention.** The 59% objective applies to the selected subset, not every market observation. Low-confidence candidates remain WAIT.
5. **Control concept drift.** A previously valid gold relationship can decay. V6.3 monitors multivariate feature stability and expires models.
6. **Prevent self-confirming learning.** Model-selected LEARNED trades are excluded from retraining, and correlated cross-lane episodes are de-duplicated.
7. **Keep market structure and macro context as safety evidence.** Gold trades nearly around the clock and is affected by global news; robust research also identifies an asymmetric inverse USD relationship. These inputs remain context—not automatic direction overrides.
8. **Use staged deployment.** Shadow, walk-forward, controlled demo and only then any discussion of live risk. Real trading remains disabled.

## Primary references

- Scikit-learn probability calibration: https://scikit-learn.org/stable/modules/calibration.html
- Scikit-learn time-series split: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- Learning under concept drift review: https://arxiv.org/abs/2004.05785
- CFTC automated-trading safeguards: https://www.cftc.gov/PressRoom/PressReleases/7283-15
- MetaTrader 5 Python order interface: https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py
- MetaTrader 5 deal-history interface: https://www.mql5.com/en/docs/python_metatrader5/mt5historydealsget_py
- CME Gold product/liquidity overview: https://www.cmegroup.com/markets/metals/precious/gold.html
- Economic Drivers of Gold: https://ssrn.com/abstract=4652113

The research supports the engineering choices; it does not establish that this particular strategy will be profitable. Profitability must be demonstrated on unseen shadow and controlled-demo trades.
