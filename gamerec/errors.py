"""Exception hierarchy for RAWG API interaction.

Every error carries a ``user_message`` that is safe to render directly in the
UI: short, plain, and free of stack traces or credentials.
"""

from __future__ import annotations


class RawgError(Exception):
    """Base class for every failure raised by :mod:`gamerec.api`."""

    #: Fallback copy shown when a subclass does not provide its own.
    default_message = "Something went wrong talking to RAWG."

    def __init__(self, message: str = "", user_message: str | None = None) -> None:
        super().__init__(message or self.default_message)
        self.user_message = user_message or self.default_message


class MissingApiKey(RawgError):
    default_message = "No RAWG API key configured. Add one to start browsing."


class InvalidApiKey(RawgError):
    default_message = "That RAWG API key was rejected. Check it and try again."


class RateLimited(RawgError):
    default_message = "RAWG is rate limiting requests. Give it a minute and retry."

    def __init__(
        self,
        message: str = "",
        user_message: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, user_message)
        self.retry_after = retry_after


class NetworkError(RawgError):
    default_message = "Can't reach RAWG. Check your internet connection."


class ServiceError(RawgError):
    default_message = "RAWG is having trouble right now. Try again shortly."


class NotFound(RawgError):
    default_message = "That game could not be found on RAWG."


def describe(exc: BaseException) -> tuple[str, str]:
    """Map an exception to a ``(state_kind, user_message)`` pair for the UI.

    ``state_kind`` selects the visual treatment: connectivity and rate-limit
    problems get the softer "offline" styling because they are transient and
    not the user's fault, everything else reads as an error.
    """
    if isinstance(exc, (NetworkError, RateLimited)):
        return "offline", exc.user_message
    if isinstance(exc, RawgError):
        return "error", exc.user_message
    return "error", "Something went wrong. Please try again."
