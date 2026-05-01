"""
Smoke tests — verify that the Django project loads correctly.
These are temporary; they'll be replaced by real tests once we build apps.
"""

import django
from django.conf import settings


def test_django_can_load():
    """Django should be importable and configured."""
    assert django.VERSION[0] >= 5


def test_settings_loaded():
    """Settings module should be loaded with required keys."""
    assert settings.SECRET_KEY
    assert settings.DATABASES["default"]["ENGINE"]
    assert "rest_framework" in settings.INSTALLED_APPS


def test_currencies_configured():
    """Multi-currency support should be wired up."""
    assert "USD" in settings.CURRENCIES
    assert "NGN" in settings.CURRENCIES
    assert "GBP" in settings.CURRENCIES
