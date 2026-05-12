"""
Manager pattern for tenant-scoped models.

Any model that belongs to an Organisation should use TenantScopedManager
as its default manager. This makes the queryset behaviour explicit:

  - The default .all() / .filter() still works (we don't break Django)
  - .for_organisation(org) is the preferred entry point — it documents
    intent and makes tenant scoping visible in code reviews
  - .all_tenants() is an explicit escape hatch for admin/superuser code
    that genuinely needs to see across tenants

The goal isn't to *prevent* unscoped queries — Django's ORM is too flexible
for that. The goal is to make scoped queries *the obvious path* so that
unscoped queries stick out in code review as something needing justification.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from .models import Organisation


class TenantScopedQuerySet(models.QuerySet):
    """QuerySet that knows how to filter by organisation."""

    def for_organisation(self, organisation: Organisation) -> TenantScopedQuerySet:
        """Return only objects belonging to the given organisation."""
        return self.filter(organisation=organisation)

    def active_for_organisation(self, organisation: Organisation) -> TenantScopedQuerySet:
        """
        Return only active objects belonging to the given organisation.
        Assumes the model has an `is_active` field.
        """
        return self.filter(organisation=organisation, is_active=True)


class TenantScopedManager(models.Manager):
    """
    Manager for models scoped to an Organisation.

    Usage on a model:

        class Payslip(models.Model):
            organisation = models.ForeignKey(Organisation, ...)
            ...
            objects = TenantScopedManager()

    Then in views:

        Payslip.objects.for_organisation(request.organisation)
    """

    def get_queryset(self) -> TenantScopedQuerySet:
        return TenantScopedQuerySet(self.model, using=self._db)

    def for_organisation(self, organisation: Organisation) -> TenantScopedQuerySet:
        """Preferred entry point — explicit tenant scoping."""
        return self.get_queryset().for_organisation(organisation)

    def active_for_organisation(self, organisation: Organisation) -> TenantScopedQuerySet:
        """Preferred entry point for active records — explicit tenant scoping."""
        return self.get_queryset().active_for_organisation(organisation)

    def all_tenants(self) -> TenantScopedQuerySet:
        """
        Escape hatch — return ALL records across all tenants.

        Use this only when you genuinely need cross-tenant data (e.g. in
        admin dashboards, system maintenance commands, audit aggregations).
        Anywhere in business-logic code, this should be treated as a
        code-review red flag requiring justification.
        """
        return self.get_queryset()
