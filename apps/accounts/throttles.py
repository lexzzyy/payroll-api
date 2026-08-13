"""
Custom throttle classes for auth endpoints.

DRF throttles read DEFAULT_THROTTLE_RATES from settings. These subclasses
just declare their scope and (for login) customise the cache key so we
throttle on email+IP rather than IP alone.
"""

from __future__ import annotations

from rest_framework.throttling import SimpleRateThrottle


class LoginRateThrottle(SimpleRateThrottle):
    """
    Throttle login attempts by email + IP combination.

    Keying on email (not just IP) means an attacker can't cycle through
    many emails from one IP, and legitimate users behind shared IPs
    (offices, NAT) aren't unfairly blocked by others' attempts.
    """

    scope = "login"

    def get_cache_key(self, request, view):
        email = (request.data.get("email") or "").lower().strip()
        ident = self.get_ident(request)  # client IP
        if not email:
            # No email supplied — fall back to IP-only throttling
            return self.cache_format % {"scope": self.scope, "ident": ident}
        return self.cache_format % {
            "scope": self.scope,
            "ident": f"{email}:{ident}",
        }


class SignupRateThrottle(SimpleRateThrottle):
    """Throttle signup attempts by IP."""

    scope = "signup"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class PasswordResetRateThrottle(SimpleRateThrottle):
    """Throttle password reset requests by IP."""

    scope = "password_reset"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class ResendVerificationRateThrottle(SimpleRateThrottle):
    """Throttle resend-verification requests by IP."""

    scope = "resend_verification"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }
