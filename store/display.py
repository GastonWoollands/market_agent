from decimal import Decimal


def resolve_price(quote_price: Decimal | None, last_close: Decimal | None) -> Decimal | None:
    if quote_price is not None:
        return quote_price
    return last_close


def resolve_change_pct(
    quote_change: Decimal | None,
    last_close: Decimal | None,
    prev_close: Decimal | None,
) -> Decimal | None:
    if quote_change is not None:
        return quote_change
    if last_close is None or prev_close is None or prev_close == 0:
        return None
    return (last_close / prev_close - 1) * Decimal("100")


def resolve_level_change(last: Decimal | None, prev: Decimal | None) -> Decimal | None:
    if last is None or prev is None:
        return None
    return last - prev


def resolve_yield_change_bp(
    price: Decimal | None,
    quote_change_pct: Decimal | None,
    last_close: Decimal | None,
    prev_close: Decimal | None,
) -> Decimal | None:
    """Yield indices (^TNX etc.) quote percent levels; the move that matters is bp, not %."""
    if price is not None and quote_change_pct is not None:
        prior = price / (1 + quote_change_pct / Decimal("100"))
        return (price - prior) * Decimal("100")
    if last_close is None or prev_close is None:
        return None
    return (last_close - prev_close) * Decimal("100")
