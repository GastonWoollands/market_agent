class AgentError(Exception):
    """Base error for the Outlook agent writer."""


class AgentHttpError(AgentError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class CitationError(AgentError):
    def __init__(self, issues: list[str]) -> None:
        super().__init__("citation check failed: " + ", ".join(issues))
        self.issues = issues
