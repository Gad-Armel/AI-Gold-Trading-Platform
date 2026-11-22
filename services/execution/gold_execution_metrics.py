"""Broker-result diagnostics; accepted orders are not confirmed deal fills."""
import math


def execution_metrics(request, result, *, elapsed_ms, point, contract_size):
    code = result.get('retcode')
    states = {10009:'REPORTED_DONE', 10010:'REPORTED_PARTIAL', 10008:'ACCEPTED_PENDING'}
    def finite(value, positive=False):
        try:
            value = float(value)
            return value if math.isfinite(value) and (not positive or value > 0) else None
        except (TypeError, ValueError):
            return None
    reported = finite(result.get('price'), True)
    volume = finite(result.get('volume'), True)
    requested = finite(request.get('price'), True)
    point, contract = finite(point, True), finite(contract_size, True)
    # Close BUY positions send SELL requests; this sign handles both actions.
    sign = 1 if request.get('type') == 0 else -1
    slippage = sign*(reported-requested) if reported and requested and code in (10009,10010) else None
    return dict(state=states.get(code, 'NOT_CONFIRMED'), order_send_elapsed_ms=round(elapsed_ms, 3),
                requested_price=requested, reported_price=reported, reported_volume=volume,
                reported_adverse_slippage_price=slippage,
                reported_adverse_slippage_points=slippage/point if slippage is not None and point else None,
                reported_adverse_slippage_usd=slippage*volume*contract
                    if slippage is not None and volume and contract else None,
                deal_history_confirmation_required=True,
                retry_performed=False)
