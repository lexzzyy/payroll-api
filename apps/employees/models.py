"""
Employee model — a person on an organisation's payroll.

An Employee is tenant-scoped (belongs to one Organisation) and may be
linked to a User account, though many employees never log in. The Employee
record holds employment facts (hire date, job title, employment type,
bank details) but NOT salary amounts — those live in SalaryStructure so
they can be versioned over time.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.organisations.managers import TenantScopedManager
from apps.organisations.models import Organisation


class EmploymentType(models.TextChoices):
    """How the employee is engaged."""

    FULL_TIME = "full_time", _("Full-time")
    PART_TIME = "part_time", _("Part-time")
    CONTRACT = "contract", _("Contract")
    INTERN = "intern", _("Intern")


class EmployeeStatus(models.TextChoices):
    """Current employment status."""

    ACTIVE = "active", _("Active")
    ON_LEAVE = "on_leave", _("On leave")
    SUSPENDED = "suspended", _("Suspended")
    TERMINATED = "terminated", _("Terminated")


class Employee(models.Model):
    """A person on an organisation's payroll."""

    public_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.PROTECT,
        related_name="employees",
    )

    # Optional link to a login account — many employees never log in.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee_records",
        help_text=_("Linked login account, if the employee uses the system."),
    )

    # Employee-number, unique within an organisation
    employee_number = models.CharField(
        max_length=32,
        help_text=_("Organisation-assigned staff/payroll number."),
    )

    # Identity (stored on the Employee, not the User, because an employee
    # may have no User account)
    full_name = models.CharField(_("full name"), max_length=200)
    email = models.EmailField(_("work email"), blank=True)
    phone_number = models.CharField(max_length=32, blank=True)

    # Employment facts
    job_title = models.CharField(max_length=150, blank=True)
    department = models.CharField(max_length=150, blank=True)
    employment_type = models.CharField(
        max_length=20,
        choices=EmploymentType.choices,
        default=EmploymentType.FULL_TIME,
    )
    status = models.CharField(
        max_length=20,
        choices=EmployeeStatus.choices,
        default=EmployeeStatus.ACTIVE,
    )
    hire_date = models.DateField(help_text=_("First day of employment."))
    termination_date = models.DateField(null=True, blank=True)

    # Payment details (bank account for disbursement)
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account_number = models.CharField(max_length=20, blank=True)
    bank_account_name = models.CharField(max_length=200, blank=True)

    # Tax / statutory identifiers (country-dependent which apply)
    tax_id = models.CharField(
        _("tax identification number"),
        max_length=50,
        blank=True,
    )
    pension_pin = models.CharField(max_length=50, blank=True)

    # Audit
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantScopedManager()

    class Meta:
        verbose_name = _("employee")
        verbose_name_plural = _("employees")
        ordering = ("full_name",)
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "employee_number"],
                name="unique_employee_number_per_org",
            ),
        ]
        indexes = [
            models.Index(fields=["organisation", "status"]),
            models.Index(fields=["organisation", "department"]),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.employee_number})"

    @property
    def is_active(self) -> bool:
        return self.status == EmployeeStatus.ACTIVE

    @property
    def short_name(self) -> str:
        return self.full_name.split()[0] if self.full_name else ""
