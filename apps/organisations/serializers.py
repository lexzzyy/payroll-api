"""Serializers for the organisations app."""

from __future__ import annotations

from rest_framework import serializers

from .models import OrganisationInvitation, Role


class InvitationCreateSerializer(serializers.Serializer):
    """Validate a new invitation request."""

    email = serializers.EmailField(required=True)
    role = serializers.ChoiceField(
        choices=[(Role.HR_MANAGER, "HR Manager"), (Role.EMPLOYEE, "Employee")],
        default=Role.EMPLOYEE,
    )

    def validate_email(self, value: str) -> str:
        return value.lower().strip()


class InvitationReadSerializer(serializers.ModelSerializer):
    """Serialize an invitation for listing."""

    invited_by_email = serializers.EmailField(
        source="invited_by.email", read_only=True, default=None
    )
    is_pending = serializers.BooleanField(read_only=True)

    class Meta:
        model = OrganisationInvitation
        fields = (
            "public_id",
            "email",
            "role",
            "invited_by_email",
            "created_at",
            "expires_at",
            "accepted_at",
            "is_pending",
        )
        read_only_fields = fields


class InvitationAcceptSerializer(serializers.Serializer):
    """Accept an invitation. Password required only for new users."""

    token = serializers.CharField(required=True, min_length=20)
    full_name = serializers.CharField(required=False, max_length=150)
    password = serializers.CharField(
        required=False,
        min_length=10,
        write_only=True,
        style={"input_type": "password"},
    )
