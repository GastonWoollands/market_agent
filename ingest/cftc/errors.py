from ingest.http import VendorError, VendorHttpError, VendorParseError


class CftcError(VendorError):
    """Base error for the CFTC Public Reporting adapter."""


class CftcHttpError(CftcError, VendorHttpError):
    pass


class CftcParseError(CftcError, VendorParseError):
    pass
