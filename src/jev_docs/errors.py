"""User-facing errors, without credentials or raw provider bodies."""


class JevDocsError(Exception):
    """A document-processing failure safe to display to the user."""

    def __init__(self, message: str, *, requests: list | None = None):
        super().__init__(message)
        self.requests = requests or []


class DocumentError(JevDocsError):
    pass


class ContextLimitError(JevDocsError):
    pass


class ProviderError(JevDocsError):
    pass
