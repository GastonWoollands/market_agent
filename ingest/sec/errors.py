class SecError(Exception):
    """Base error for the SEC EDGAR adapter."""


class SecHttpError(SecError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SecParseError(SecError):
    pass
