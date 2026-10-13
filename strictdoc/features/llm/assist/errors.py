"""The error of a request that cannot be served."""


class AssistError(Exception):
    """A request that cannot be served: an HTTP status and a message."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
