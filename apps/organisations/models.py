"""
Organisation and Membership models — the multi-tenant foundation.

Every business object in the system belongs to exactly one Organisation.
Users connect to Organisations via Membership rows that carry a Role
(Owner / HR Manager / Employee).
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


class Role(models.TextChoices):
    """
    Roles a User can hold within an Organisation.

    Stored as a string so the database is human-readable and so adding
    a new role doesn't shift existing values.
    """

    OWNER = "owner", _("Owner")
    HR_MANAGER = "hr_manager", _("HR Manager")
    EMPLOYEE = "employee", _("Employee")


class Organisation(models.Model):
    """
    A customer company using the platform. The unit of tenant isolation:
    every business object (employee, payslip, leave request) belongs to
    exactly one Organisation.
    """

    public_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )
    slug = models.SlugField(
        max_length=80,
        unique=True,
        help_text=_("URL-friendly identifier, e.g. 'oyo-college-of-nursing'."),
    )

    # Identity
    legal_name = models.CharField(
        _("legal name"),
        max_length=200,
        help_text=_("Registered company name as it appears on legal documents."),
    )
    trading_name = models.CharField(
        _("trading name"),
        max_length=200,
        blank=True,
        help_text=_("Public-facing name, if different from legal name."),
    )

    # Localisation — drives payroll calculation and display formatting
    country_code = models.CharField(
        max_length=2,
        help_text=_(
            "ISO 3166-1 alpha-2 (e.g. 'NG', 'GB'). Determines which payroll " "calculator is used."
        ),
    )
    default_currency = models.CharField(
        max_length=3,
        help_text=_("ISO 4217 (e.g. 'NGN', 'GBP', 'USD')."),
    )
    timezone_name = models.CharField(
        max_length=64,
        default="UTC",
        help_text=_("IANA timezone name (e.g. 'Africa/Lagos')."),
    )

    # Tax / regulatory identifiers — country-dependent which apply
    tax_id = models.CharField(
        _("tax identification number"),
        max_length=50,
        blank=True,
        help_text=_("Primary tax registration number for this organisation."),
    )

    # State
    is_active = models.BooleanField(
        default=True,
        help_text=_(
            "Soft-deletion flag. Inactive organisations cannot be accessed "
            "but their data is preserved for audit."
        ),
    )

    # Audit
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="organisations_created",
        help_text=_(
            "The user who created this organisation. NULL for "
            "system-seeded orgs (imports, fixtures, automated flows)."
        ),
    )

    class Meta:
        verbose_name = _("organisation")
        verbose_name_plural = _("organisations")
        ordering = ("legal_name",)
        indexes = [
            models.Index(fields=["country_code", "is_active"]),
        ]

    def __str__(self) -> str:
        return self.trading_name or self.legal_name

    def save(self, *args, **kwargs) -> None:
        """Auto-generate slug from legal_name if not provided."""
        if not self.slug:
            base_slug = slugify(self.legal_name)[:75]
            slug = base_slug
            counter = 1
            # Ensure uniqueness even if multiple orgs share a name
            while Organisation.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                counter += 1
                slug = f"{base_slug}-{counter}"
            self.slug = slug
        super().save(*args, **kwargs)


class Membership(models.Model):
    """
    Links a User to an Organisation with a specific Role.

    A User can have many Memberships (be part of multiple organisations).
    An Organisation has many Memberships (multiple users with various
    roles).

    The (user, organisation) pair is unique — a user cannot have two
    different roles in the same organisation. To change a user's role,
    update the existing Membership.
    """

    public_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(
        max_length=32,
        choices=Role.choices,
        default=Role.EMPLOYEE,
        help_text=_("The user's role within this organisation."),
    )

    # State and lifecycle
    is_active = models.BooleanField(
        default=True,
        help_text=_("Inactive memberships block access but preserve audit history."),
    )
    invited_at = models.DateTimeField(default=timezone.now, editable=False)
    accepted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the invited user accepted the invitation."),
    )

    # Audit
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memberships_invited",
        help_text=_("The user who issued the invitation. Null if self-created."),
    )

    class Meta:
        verbose_name = _("membership")
        verbose_name_plural = _("memberships")
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["user", "organisation"],
                name="unique_user_organisation_membership",
            ),
        ]
        indexes = [
            models.Index(fields=["organisation", "role", "is_active"]),
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.user.email} @ {self.organisation} ({self.get_role_display()})"

    @property
    def is_pending(self) -> bool:
        """True if the membership has been invited but not yet accepted."""
        return self.accepted_at is None

    @property
    def is_owner(self) -> bool:
        return self.role == Role.OWNER

    @property
    def is_hr_manager(self) -> bool:
        return self.role == Role.HR_MANAGER

    def accept(self) -> None:
        """Mark this invitation as accepted. Idempotent."""
        if self.accepted_at is not None:
            return
        self.accepted_at = timezone.now()
        self.save(update_fields=["accepted_at"])
