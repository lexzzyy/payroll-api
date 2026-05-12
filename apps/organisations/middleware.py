"""
Multi-tenant scoping middleware.

Runs on every authenticated request and:
  1. Determines which Organisation the request is for
  2. Verifies the user has an active membership in it
  3. Attaches `request.organisation`, `request.membership`, and
     `request.role` so views can use them without re-querying

The tenant is identified from (in priority order):
  1. The X-Organisation-Id HTTP header (UUID of the organisation)
  2. The organisation_slug URL kwarg (set by URL routing)

Anonymous (unauthenticated) requests are passed through untouched — auth
runs separately and rejects unauthenticated requests at the view level.

Exempt paths (admin, schema, health checks) bypass tenant resolution
entirely since they're not tenant-scoped.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from django.http import HttpRequest, HttpResponse, JsonResponse

from .exceptions import (
    TenantAccessDenied,
    TenantError,
    TenantNotFound,
)
from .models import Membership, Organisation

# Paths that don't require tenant scoping.
# Add new prefixes here as the API grows.
EXEMPT_PATH_PREFIXES = (
    "/admin/",
    "/api/schema/",
    "/api/docs/",
    "/health/",
    "/static/",
    "/media/",
)


class OrganisationScopeMiddleware:
    """
    Attach organisation, membership, and role to every authenticated request.

    For tenant-scoped requests, sets:
        request.organisation : Organisation instance
        request.membership   : Membership instance
        request.role         : str (one of Role.values)

    For exempt or anonymous requests, these attributes are not set.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Default values — views can rely on these attributes always existing
        request.organisation = None
        request.membership = None
        request.role = None

        # Skip tenant resolution for exempt paths
        if self._is_exempt(request.path):
            return self.get_response(request)

        # Skip for unauthenticated requests; auth happens separately
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return self.get_response(request)

        # Resolve and attach the tenant context
        try:
            self._resolve_tenant(request)
        except TenantError as exc:
            return self._error_response(exc)

        return self.get_response(request)

    # ----------------------------------------------------------------
    # Internals
    # ----------------------------------------------------------------

    def _is_exempt(self, path: str) -> bool:
        return path.startswith(EXEMPT_PATH_PREFIXES)

    def _resolve_tenant(self, request: HttpRequest) -> None:
        """
        Resolve the tenant for this request and attach context.

        Raises TenantError subclasses on failure; the caller converts
        these to HTTP responses.
        """
        org_id = self._extract_organisation_id(request)

        # If no organisation ID was provided, that's allowed for some
        # endpoints (e.g. listing the user's own memberships). The view
        # itself will reject the request if it requires tenant context.
        if not org_id:
            return

        # Look up the organisation
        try:
            organisation = Organisation.objects.get(public_id=org_id, is_active=True)
        except (Organisation.DoesNotExist, ValueError):
            raise TenantNotFound() from None

        # Look up the user's membership in this organisation
        try:
            membership = Membership.objects.select_related("organisation").get(
                user=request.user,
                organisation=organisation,
                is_active=True,
                accepted_at__isnull=False,
            )
        except Membership.DoesNotExist:
            raise TenantAccessDenied() from None

        # Attach to request — views and DRF permissions read these
        request.organisation = organisation
        request.membership = membership
        request.role = membership.role

    def _extract_organisation_id(self, request: HttpRequest) -> str | None:
        """
        Pull the organisation identifier from the request.

        Checks (in order):
            1. X-Organisation-Id HTTP header (UUID)
            2. organisation_slug URL kwarg
        """
        # Try header first — most common for API clients
        org_id = request.headers.get("X-Organisation-Id")
        if org_id:
            try:
                UUID(org_id)  # validate format
            except ValueError:
                raise TenantNotFound() from None
            return org_id

        # Try URL kwarg — set by the URL router for slug-based routes
        resolver_match = getattr(request, "resolver_match", None)
        if resolver_match:
            slug = resolver_match.kwargs.get("organisation_slug")
            if slug:
                # Look up the org by slug to get its public_id
                try:
                    org = Organisation.objects.get(slug=slug, is_active=True)
                    return str(org.public_id)
                except Organisation.DoesNotExist:
                    raise TenantNotFound() from None

        return None

    def _error_response(self, exc: TenantError) -> JsonResponse:
        return JsonResponse(
            {"error": str(exc), "code": exc.__class__.__name__},
            status=exc.status_code,
        )
