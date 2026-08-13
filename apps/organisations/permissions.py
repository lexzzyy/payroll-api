"""
DRF permission classes for role-based access control.

Because JWT authentication runs at the DRF layer (after Django middleware),
request.organisation may not be set by the middleware for token-authenticated
requests. These permission classes resolve the tenant themselves using the
now-authenticated request.user.
"""

from __future__ import annotations

from uuid import UUID

from rest_framework.permissions import BasePermission

from .models import Membership, Organisation, Role


def resolve_tenant(request) -> bool:
    """
    Resolve and attach tenant context to the request if not already done.
    Returns True if a valid tenant context is present, False otherwise.
    Safe to call multiple times — idempotent.
    """
    if getattr(request, "organisation", None) is not None:
        return True

    if not request.user or not request.user.is_authenticated:
        return False

    org_id = request.headers.get("X-Organisation-Id")
    if not org_id:
        return False

    try:
        UUID(org_id)
    except (ValueError, TypeError):
        return False

    try:
        organisation = Organisation.objects.get(public_id=org_id, is_active=True)
    except Organisation.DoesNotExist:
        return False

    try:
        membership = Membership.objects.select_related("organisation").get(
            user=request.user,
            organisation=organisation,
            is_active=True,
            accepted_at__isnull=False,
        )
    except Membership.DoesNotExist:
        return False

    request.organisation = organisation
    request.membership = membership
    request.role = membership.role
    return True


class IsOrganisationMember(BasePermission):
    """Allow any user with an active, accepted membership in the tenant."""

    message = "You must be a member of this organisation."

    def has_permission(self, request, view) -> bool:
        return resolve_tenant(request)


class IsOrganisationHRManager(BasePermission):
    """Allow Owners and HR Managers. Blocks Employees."""

    message = "This action requires HR Manager or Owner privileges."

    def has_permission(self, request, view) -> bool:
        if not resolve_tenant(request):
            return False
        return request.role in (Role.OWNER, Role.HR_MANAGER)


class IsOrganisationOwner(BasePermission):
    """Allow only the organisation Owner."""

    message = "This action requires Owner privileges."

    def has_permission(self, request, view) -> bool:
        if not resolve_tenant(request):
            return False
        return request.role == Role.OWNER


class IsSelfOrHRManager(BasePermission):
    """
    Object-level permission: allow if the requesting user owns the object,
    OR if they're an HR Manager / Owner in the organisation.
    """

    message = "You can only access your own records unless you are HR."

    def has_permission(self, request, view) -> bool:
        return resolve_tenant(request)

    def has_object_permission(self, request, view, obj) -> bool:
        if request.role in (Role.OWNER, Role.HR_MANAGER):
            return True
        obj_user_id = getattr(obj, "user_id", None)
        if obj_user_id is None and hasattr(obj, "user"):
            obj_user_id = obj.user.id
        return obj_user_id == request.user.id
