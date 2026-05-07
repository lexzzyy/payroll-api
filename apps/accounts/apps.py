from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """
    Custom user accounts: identity, authentication, and profile.

    Note: This app must be loaded before any migration runs because it
    defines the AUTH_USER_MODEL referenced by django.contrib.auth.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Accounts"
