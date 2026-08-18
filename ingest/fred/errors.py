class FredError(Exception):
    """Base error for the FRED adapter."""


class FredHttpError(FredError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class FredParseError(FredError):
    pass
