from models.market_state import SignalPackageState


def format_signal_package_for_ai(signal_package: SignalPackageState) -> str:
    """
    Converts the signal package into clean text for the future AI brain.

    The AI should receive a clear summary, not messy raw Python objects.
    """

    lines = []

    lines.append("========== MARKET SIGNAL PACKAGE ==========")

    lines.append("\n--- MARKET INFO ---")
    lines.append(f"Symbol: {signal_package.symbol}")
    lines.append(f"Timestamp UTC: {signal_package.timestamp}")
    lines.append(f"Price: {signal_package.price}")
    lines.append(f"Primary Session: {signal_package.primary_session}")
    lines.append(f"Active Sessions: {signal_package.active_sessions}")

    lines.append("\n--- MARKET CONDITIONS ---")
    lines.append(f"Price Valid: {signal_package.price_valid}")
    lines.append(f"Candles Loaded: {signal_package.candles_loaded}")
    lines.append(f"Spread Safe: {signal_package.spread_safe}")
    lines.append(f"Session Active: {signal_package.session_active}")

    lines.append("\n--- TREND ---")
    lines.append(f"Overall Trend: {signal_package.overall_trend}")
    lines.append(f"Trend Confidence: {signal_package.trend_confidence}")

    lines.append("Timeframe Trends:")
    for timeframe, trend_value in signal_package.timeframe_trends.items():
        lines.append(f"- {timeframe}: {trend_value}")

    lines.append("\n--- VOLATILITY ---")
    lines.append(f"Overall Volatility: {signal_package.overall_volatility}")
    lines.append(f"Volatility Confidence: {signal_package.volatility_confidence}")
    lines.append(f"Trade Risk Level: {signal_package.trade_risk_level}")

    lines.append("\n--- STRUCTURE ---")
    lines.append(f"Structure Bias: {signal_package.structure_bias}")
    lines.append(f"Structure Confidence: {signal_package.structure_confidence}")
    lines.append(f"Nearest Support: {signal_package.nearest_support}")
    lines.append(f"Nearest Resistance: {signal_package.nearest_resistance}")
    lines.append(f"Distance To Support: {signal_package.distance_to_support}")
    lines.append(f"Distance To Resistance: {signal_package.distance_to_resistance}")

    lines.append("\n--- DECISION ENGINE ---")
    lines.append(f"Decision Action: {signal_package.decision_action}")
    lines.append(f"Decision Trade Allowed: {signal_package.decision_trade_allowed}")
    lines.append(f"Decision Confidence: {signal_package.decision_confidence}")

    lines.append("\n--- REASONS ---")

    for reason_group, reasons in signal_package.reasons.items():
        lines.append(f"\n{reason_group.upper()}:")

        if not reasons:
            lines.append("- No reasons provided.")
            continue

        for reason in reasons:
            lines.append(f"- {reason}")

    return "\n".join(lines)