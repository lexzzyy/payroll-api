"""
Organisation views.

For Phase 2.7, these are minimal endpoints that demonstrate and test the
role-based permission classes. Real organisation-management endpoints
(invite members, update settings) come in Phase 2.9 and Week 3.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Membership, OrganisationInvitation
from .permissions import (
    IsOrganisationHRManager,
    IsOrganisationMember,
    IsOrganisationOwner,
)
from .serializers import (
    InvitationAcceptSerializer,
    InvitationCreateSerializer,
    InvitationReadSerializer,
)
from .tasks import send_invitation_email

User = get_user_model()


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


class InvitationListCreateView(APIView):
    """
    GET  /api/v1/orgs/invitations/  — list pending invitations (HR+)
    POST /api/v1/orgs/invitations/  — send a new invitation (HR+)
    """

    permission_classes = [IsAuthenticated, IsOrganisationHRManager]

    def get(self, request):
        invitations = OrganisationInvitation.objects.filter(
            organisation=request.organisation,
            accepted_at__isnull=True,
            revoked_at__isnull=True,
        ).select_related("invited_by")
        serializer = InvitationReadSerializer(invitations, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        role = serializer.validated_data["role"]

        # Already a member?
        if Membership.objects.filter(
            organisation=request.organisation,
            user__email=email,
            is_active=True,
        ).exists():
            return Response(
                {"detail": "This person is already a member of the organisation."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Existing pending invite?
        if OrganisationInvitation.objects.filter(
            organisation=request.organisation,
            email=email,
            accepted_at__isnull=True,
            revoked_at__isnull=True,
        ).exists():
            return Response(
                {"detail": "A pending invitation already exists for this email."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invitation, plain_token = OrganisationInvitation.generate(
            organisation=request.organisation,
            email=email,
            role=role,
            invited_by=request.user,
        )
        send_invitation_email.delay(invitation.id, plain_token)

        return Response(
            {
                "detail": f"Invitation sent to {email}.",
                "invitation": InvitationReadSerializer(invitation).data,
            },
            status=status.HTTP_201_CREATED,
        )


class InvitationRevokeView(APIView):
    """DELETE /api/v1/orgs/invitations/{public_id}/ — revoke a pending invite."""

    permission_classes = [IsAuthenticated, IsOrganisationHRManager]

    def delete(self, request, public_id):
        try:
            invitation = OrganisationInvitation.objects.get(
                public_id=public_id,
                organisation=request.organisation,
                accepted_at__isnull=True,
                revoked_at__isnull=True,
            )
        except OrganisationInvitation.DoesNotExist:
            return Response(
                {"detail": "Pending invitation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        invitation.revoke()
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvitationAcceptView(APIView):
    """
    POST /api/v1/orgs/invitations/accept/ — accept an invitation.

    Public endpoint (no auth). Creates the user if they don't exist,
    then creates an active Membership. Idempotent-ish: a consumed token
    can't be reused.
    """

    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        serializer = InvitationAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        invitation = OrganisationInvitation.find_valid(serializer.validated_data["token"])
        if invitation is None:
            return Response(
                {"detail": "Invalid or expired invitation."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = invitation.email
        user = User.objects.filter(email=email).first()

        if user is None:
            # New user — password required
            password = serializer.validated_data.get("password")
            if not password:
                return Response(
                    {"detail": "A password is required to create your account."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                validate_password(password)
            except DjangoValidationError as exc:
                return Response(
                    {"password": list(exc.messages)},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user = User.objects.create_user(
                email=email,
                password=password,
                full_name=serializer.validated_data.get("full_name", ""),
            )
            # Invitation acceptance verifies the email implicitly
            user.mark_email_verified()

        # Create or activate membership
        membership, created = Membership.objects.get_or_create(
            user=user,
            organisation=invitation.organisation,
            defaults={"role": invitation.role, "accepted_at": timezone.now()},
        )
        if not created:
            membership.role = invitation.role
            membership.is_active = True
            membership.accepted_at = timezone.now()
            membership.save(update_fields=["role", "is_active", "accepted_at"])

        # Consume the invitation
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["accepted_at"])

        return Response(
            {
                "detail": f"You've joined {invitation.organisation.legal_name}.",
                "organisation": invitation.organisation.legal_name,
                "role": invitation.role,
            },
            status=status.HTTP_200_OK,
        )
