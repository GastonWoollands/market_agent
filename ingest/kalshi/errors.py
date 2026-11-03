from ingest.http import VendorError, VendorHttpError, VendorParseError


class KalshiError(VendorError):
    """Base error for the Kalshi adapter."""


class KalshiHttpError(KalshiError, VendorHttpError):
    pass


class KalshiParseError(KalshiError, VendorParseError):
    pass
