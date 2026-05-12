from django.apps import AppConfig


class OrganisationsConfig(AppConfig):
    """
    Multi-tenancy: organisations and user memberships.

    Every business object in the system belongs to exactly one
    Organisation. Memberships link Users to Organisations with a Role
    that determines their permissions within that tenant.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.organisations"
    label = "organisations"
    verbose_name = "Organisations"
