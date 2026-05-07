"""
Custom User model.

Identity is keyed on email (not username). The model deliberately keeps
authentication concerns (login, password, verification) separate from
profile data — though for v1 they live on the same row for simplicity.
"""

from __future__ import annotations

import uuid

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
