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
