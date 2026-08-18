class PolymarketError(Exception):
    """Base error for the Polymarket Gamma adapter."""


class PolymarketHttpError(PolymarketError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class PolymarketParseError(PolymarketError):
    pass
