"""Exceptions whose message is safe to show to the user."""


class UserFacingError(RuntimeError):
    """An LLM failure with a curated, user-readable message.

    Only these messages are forwarded to the browser; any other exception is
    logged and replaced by a generic message (no internals leak to the UI).
    """
