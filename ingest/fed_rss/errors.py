class FedRssError(Exception):
    """Base error for the Federal Reserve Board RSS adapter."""


class FedRssHttpError(FedRssError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class FedRssParseError(FedRssError):
    pass
