"""
Serializers for the accounts app.

Serializers convert between Python/Django objects and JSON for API
input/output, and handle validation in the process.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.organisations.models import Membership, Organisation, Role

User = get_user_model()


class LoginSerializer(TokenObtainPairSerializer):
    """
    Validates email + password and issues access/refresh tokens.

    Inherits from simplejwt's TokenObtainPairSerializer, which already
    does the heavy lifting. We override `username_field` so it accepts
    'email' rather than 'username', and we attach the user to the
    request after validation so the view can record the login IP.
    """

    username_field = User.USERNAME_FIELD  # "email"

    def validate(self, attrs):
        # Standard simplejwt validation — issues tokens if credentials are valid
        data = super().validate(attrs)

        # Block unverified users from logging in. We do this *after* credential
        # validation so we don't leak whether an email is registered.
        if not self.user.email_verified:
            raise serializers.ValidationError(
                {
                    "detail": (
                        "Email not verified. Please verify your email " "address before logging in."
                    ),
                    "code": "email_not_verified",
                }
            )

        # Block inactive accounts (soft-deleted users)
        if not self.user.is_active:
            raise serializers.ValidationError(
                {"detail": "This account has been deactivated.", "code": "inactive"}
            )

        # Stash the user on the request so the view can record IP
        self.context["request"]._user_for_ip_tracking = self.user

        # Enrich the response with a minimal user payload — saves a
        # follow-up GET /me request on login
        data["user"] = {
            "public_id": str(self.user.public_id),
            "email": self.user.email,
            "full_name": self.user.full_name,
            "is_staff": self.user.is_staff,
        }
        return data


class LogoutSerializer(serializers.Serializer):
    """Validates that a refresh token was supplied in the request body."""

    refresh = serializers.CharField(required=True)


class CurrentUserSerializer(serializers.ModelSerializer):
    """Public profile of the currently authenticated user."""

    class Meta:
        model = User
        fields = (
            "public_id",
            "email",
            "full_name",
            "phone_number",
            "preferred_language",
            "country_code",
            "timezone_name",
            "email_verified",
            "is_staff",
            "created_at",
        )
        read_only_fields = fields  # this endpoint is read-only


class SignupSerializer(serializers.Serializer):
    """
    User self-signup.

    Creates the User, their first Organisation (where they're Owner), and
    the corresponding Membership — all in one atomic transaction.
    """

    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        required=True,
        write_only=True,
        min_length=10,
        style={"input_type": "password"},
    )
    full_name = serializers.CharField(required=True, max_length=150)
    organisation_name = serializers.CharField(
        required=True,
        max_length=200,
        help_text="The legal name of your organisation.",
    )
    country_code = serializers.CharField(
        required=True,
        max_length=2,
        help_text="ISO 3166-1 alpha-2, e.g. 'NG', 'GB'.",
    )
    default_currency = serializers.CharField(required=True, max_length=3)
    timezone_name = serializers.CharField(
        required=False,
        max_length=64,
        default="UTC",
    )

    def validate_email(self, value: str) -> str:
        """Normalise email and reject if already registered."""
        normalised = value.lower().strip()
        if User.objects.filter(email=normalised).exists():
            raise serializers.ValidationError(
                "An account with this email may already exist. "
                "If you've signed up before, please log in instead."
            )
        return normalised

    def validate_password(self, value: str) -> str:
        """Run Django's configured password validators."""
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def validate_country_code(self, value: str) -> str:
        return value.upper()

    def validate_default_currency(self, value: str) -> str:
        return value.upper()

    @transaction.atomic
    def create(self, validated_data: dict) -> User:
        """
        Create User, Organisation, and Membership atomically.

        If any step fails, all are rolled back — no half-created accounts.
        """
        from django.utils import timezone

        org_name = validated_data.pop("organisation_name")
        country = validated_data.pop("country_code")
        currency = validated_data.pop("default_currency")
        tz = validated_data.pop("timezone_name", "UTC")

        # Create the user
        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            full_name=validated_data["full_name"],
            country_code=country,
            timezone_name=tz,
        )

        # Create the organisation
        org = Organisation.objects.create(
            legal_name=org_name,
            country_code=country,
            default_currency=currency,
            timezone_name=tz,
            created_by=user,
        )

        # Create the owner membership (auto-accepted, since this is self-signup)
        Membership.objects.create(
            user=user,
            organisation=org,
            role=Role.OWNER,
            accepted_at=timezone.now(),
        )

        return user


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    def validate_email(self, value: str) -> str:
        return value.lower().strip()


class VerifyEmailSerializer(serializers.Serializer):
    token = serializers.CharField(required=True, min_length=20)
