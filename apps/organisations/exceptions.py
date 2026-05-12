"""
Multi-tenancy exceptions.

These are raised when something goes wrong with tenant resolution or
access — they get converted to HTTP responses by the middleware.
"""

from __future__ import annotations


class TenantError(Exception):
    """Base class for tenant-related errors."""

    status_code: int = 400
    default_message: str = "Tenant error"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.default_message)


class TenantNotSpecified(TenantError):
    """The request didn't identify which tenant to operate on."""

    status_code = 400
    default_message = (
        "Tenant not specified. Include the X-Organisation-Id header " "or specify it in the URL."
    )


class TenantNotFound(TenantError):
    """The specified tenant doesn't exist or has been deactivated."""

    status_code = 404
    default_message = "Organisation not found."


class TenantAccessDenied(TenantError):
    """The caller has no active membership in the specified tenant."""

    status_code = 403
    default_message = (
        "You don't have access to this organisation, or your membership " "is inactive."
    )
