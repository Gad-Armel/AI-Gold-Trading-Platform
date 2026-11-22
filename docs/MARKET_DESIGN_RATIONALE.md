# V6.2 Market Design Rationale

The previous bot predicted direction more often than it found tradable net edge. V6.2 therefore separates a directional candidate from permission to trade.

The initial executable hypothesis is intentionally narrow because the uploaded history was positive only in the lowest observed spread band and near VWAP. Aligned short-window tape, persistence and structural consensus reduce late or unsupported entries. Every broader condition remains observable in shadow records so future rules can be supported by chronological evidence rather than intuition.

The order-block module is objective and conservative. It requires displacement and a prior-range break, tracks invalidation and repeated mitigation, and contributes only one vote. It cannot authorize a trade alone.

Automatic self-modification is disabled. Adaptation occurs through data collection, walk-forward analysis, settings-hash approval and expiration. This prevents the bot from learning directly from its most recent losses and overfitting them into the next live decision.
