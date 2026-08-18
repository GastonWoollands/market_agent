class YahooError(Exception):
    """Base error for the Yahoo adapter."""


class YahooHttpError(YahooError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class YahooParseError(YahooError):
    pass
