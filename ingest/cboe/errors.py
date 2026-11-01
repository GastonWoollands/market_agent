class CboeError(Exception):
    """Base error for the Cboe adapter."""


class CboeHttpError(CboeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class CboeParseError(CboeError):
    pass
