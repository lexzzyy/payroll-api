"""
Custom User model.

Identity is keyed on email (not username). The model deliberately keeps
authentication concerns (login, password, verification) separate from
profile data — though for v1 they live on the same row for simplicity.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import timedelta
from hashlib import sha256

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model where email is the unique identifier instead of
    username. The User is global; their roles and tenant scopes are
    represented by Membership rows in the organisations app.
    """

    # Stable, non-sequential public identifier. Internal FKs still use
    # the integer pk; this UUID is what we expose in URLs and APIs.
    public_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )

    email = models.EmailField(
        _("email address"),
        unique=True,
        help_text=_("Used to log in. Must be unique."),
    )
    full_name = models.CharField(
        _("full name"),
        max_length=150,
        blank=True,
    )
    phone_number = models.CharField(
        _("phone number"),
        max_length=32,
        blank=True,
        help_text=_("E.164 format recommended (e.g. +2348012345678)."),
    )

    # Localisation — drives how dates/times/currencies are displayed.
    preferred_language = models.CharField(
        max_length=8,
        default="en",
        help_text=_("ISO 639-1 code (e.g. 'en', 'fr')."),
    )
    country_code = models.CharField(
        max_length=2,
        blank=True,
        help_text=_("ISO 3166-1 alpha-2 code (e.g. 'NG', 'GB')."),
    )
    timezone_name = models.CharField(
        max_length=64,
        default="UTC",
        help_text=_("IANA timezone name (e.g. 'Africa/Lagos')."),
    )

    # Account state
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can access the admin site."),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Unselect instead of deleting accounts to preserve audit trails."),
    )
    email_verified = models.BooleanField(
        default=False,
        help_text=_("Set True when the user clicks the verification link."),
    )
    email_verified_at = models.DateTimeField(null=True, blank=True)

    # Audit
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []  # email + password are always required

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.email

    @property
    def short_name(self) -> str:
        """First word of full_name, or email local-part as fallback."""
        if self.full_name:
            return self.full_name.split()[0]
        return self.email.split("@")[0]

    def get_full_name(self) -> str:
        """Standard Django interface — returns the human-readable name."""
        return self.full_name or self.email

    def get_short_name(self) -> str:
        """Standard Django interface."""
        return self.short_name

    def mark_email_verified(self) -> None:
        """Flip the verification flag and timestamp it. Save immediately."""
        if self.email_verified:
            return
        self.email_verified = True
        self.email_verified_at = timezone.now()
        self.save(update_fields=["email_verified", "email_verified_at"])


class EmailVerification(models.Model):
    """
    Single-use, time-bounded email verification tokens.

    The plain token is sent to the user via email. Only its hash is stored
    in the database — so even a full database dump wouldn't let an attacker
    activate any account.
    """

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="email_verifications",
    )
    token_hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text=_("SHA-256 hex digest of the plain token. 64 hex chars."),
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Set when the token is consumed. Tokens are single-use."),
    )

    # Token lifetime — 24 hours from issue
    TOKEN_LIFETIME = timedelta(hours=24)

    class Meta:
        verbose_name = _("email verification")
        verbose_name_plural = _("email verifications")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "used_at"]),
        ]

    def __str__(self) -> str:
        return f"Verification for {self.user.email} (created {self.created_at:%Y-%m-%d})"

    @classmethod
    def generate(cls, user: User) -> tuple[EmailVerification, str]:
        """
        Create a new verification record for the user.

        Returns the record and the *plain* token. The plain token is what
        gets emailed; only the hash is persisted.
        """
        plain_token = secrets.token_urlsafe(48)  # ~64 chars, URL-safe
        token_hash = sha256(plain_token.encode()).hexdigest()
        verification = cls.objects.create(
            user=user,
            token_hash=token_hash,
            expires_at=timezone.now() + cls.TOKEN_LIFETIME,
        )
        return verification, plain_token

    @classmethod
    def find_valid(cls, plain_token: str) -> EmailVerification | None:
        """
        Look up a non-expired, non-used verification record by plain token.

        Returns None if the token doesn't match any record, has expired,
        or has already been used. The caller cannot distinguish between
        these cases — that's intentional.
        """
        token_hash = sha256(plain_token.encode()).hexdigest()
        return (
            cls.objects.filter(
                token_hash=token_hash,
                used_at__isnull=True,
                expires_at__gt=timezone.now(),
            )
            .select_related("user")
            .first()
        )

    def consume(self) -> None:
        """Mark this token as used. Single-use enforcement."""
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])
