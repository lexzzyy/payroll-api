"""
Organisation views.

For Phase 2.7, these are minimal endpoints that demonstrate and test the
role-based permission classes. Real organisation-management endpoints
(invite members, update settings) come in Phase 2.9 and Week 3.
"""

from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import (
    IsOrganisationHRManager,
    IsOrganisationMember,
    IsOrganisationOwner,
)


class MemberOnlyView(APIView):
    """GET /api/v1/orgs/member-area/ — any member can access."""

    permission_classes = [IsAuthenticated, IsOrganisationMember]

    def get(self, request):
        return Response(
            {
                "detail": "Welcome, member.",
                "organisation": request.organisation.legal_name,
                "your_role": request.role,
            }
        )


class HRManagerOnlyView(APIView):
    """GET /api/v1/orgs/hr-area/ — only Owners and HR Managers."""

    permission_classes = [IsAuthenticated, IsOrganisationHRManager]

    def get(self, request):
        return Response(
            {
                "detail": "Welcome, HR.",
                "organisation": request.organisation.legal_name,
                "your_role": request.role,
            }
        )


class OwnerOnlyView(APIView):
    """GET /api/v1/orgs/owner-area/ — only the Owner."""

    permission_classes = [IsAuthenticated, IsOrganisationOwner]

    def get(self, request):
        return Response(
            {
                "detail": "Welcome, Owner.",
                "organisation": request.organisation.legal_name,
                "your_role": request.role,
            }
        )
