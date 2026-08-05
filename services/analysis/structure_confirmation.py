from config import settings


def _get_value(source, *keys, default=None):
    if source is None:
        return default

    for key in keys:
        if isinstance(source, dict):
            value = source.get(key)
        else:
            value = getattr(source, key, None)

        if value is not None:
            return value

    return default


def _normalize_confidence(value):
    try:
        value = float(value)

        if value > 1:
            return value / 100

        return value

    except Exception:
        return 0.0


def _safe_upper(value):
    if value is None:
        return "UNKNOWN"

    return str(value).upper()


def confirm_structure(structure):
    """
    Confirms whether market structure is strong enough for trade analysis.
    """

    structure_bias = _safe_upper(
        _get_value(
            structure,
            "structure_bias",
            "bias",
            default="UNKNOWN",
        )
    )

    structure_confidence = _normalize_confidence(
        _get_value(
            structure,
            "structure_confidence",
            "confidence",
            default=0,
        )
    )

    min_confidence = float(getattr(settings, "MIN_STRUCTURE_CONFIDENCE", 0.50))

    if structure_bias == "NEUTRAL_STRUCTURE":
        return {
            "confirmed": False,
            "bias": structure_bias,
            "confidence": structure_confidence,
            "message": "Structure is neutral. No directional edge.",
        }

    if structure_bias not in [
        "BULLISH_STRUCTURE",
        "BUY_STRUCTURE",
        "BEARISH_STRUCTURE",
        "SELL_STRUCTURE",
    ]:
        return {
            "confirmed": False,
            "bias": structure_bias,
            "confidence": structure_confidence,
            "message": f"Structure bias is not tradable: {structure_bias}.",
        }

    if structure_confidence < min_confidence:
        return {
            "confirmed": False,
            "bias": structure_bias,
            "confidence": structure_confidence,
            "message": f"Structure confidence too low: {structure_confidence}. Required: {min_confidence}.",
        }

    return {
        "confirmed": True,
        "bias": structure_bias,
        "confidence": structure_confidence,
        "message": f"{structure_bias} confirmed.",
    }


def attach_structure_confirmation(structure, structure_confirmation):
    if isinstance(structure, dict):
        structure["structure_confirmed"] = structure_confirmation.get("confirmed", False)
        structure["structure_confirmation_bias"] = structure_confirmation.get("bias", "UNKNOWN")
        structure["structure_confirmation_message"] = structure_confirmation.get("message", "")
        return structure

    try:
        setattr(structure, "structure_confirmed", structure_confirmation.get("confirmed", False))
        setattr(structure, "structure_confirmation_bias", structure_confirmation.get("bias", "UNKNOWN"))
        setattr(structure, "structure_confirmation_message", structure_confirmation.get("message", ""))
    except Exception:
        pass

    return structure