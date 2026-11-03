from ingest.http import VendorError, VendorHttpError, VendorParseError


class FinraError(VendorError):
    """Base error for the FINRA API Platform adapter."""


class FinraHttpError(FinraError, VendorHttpError):
    pass


class FinraParseError(FinraError, VendorParseError):
    pass
