"""
Smoke tests — verify that the Django project loads correctly.
These are temporary; they'll be replaced by real tests once we build apps.
"""

import django
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model


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


@pytest.mark.django_db
def test_user_creation():
    """Custom User model can be created with email and password."""
    User = get_user_model()
    user = User.objects.create_user(
        email="Tijesuni@Example.COM",
        password="securepass123",
        full_name="Tijesuni Test",
    )
    assert user.email == "tijesuni@example.com"  # normalized to lowercase
    assert user.check_password("securepass123")
    assert user.is_active is True
    assert user.email_verified is False
    assert user.is_staff is False
    assert str(user) == "tijesuni@example.com"


@pytest.mark.django_db
def test_superuser_creation():
    """Superusers are auto-verified and have full privileges."""
    User = get_user_model()
    admin = User.objects.create_superuser(
        email="admin@example.com",
        password="adminpass123",
    )
    assert admin.is_staff is True
    assert admin.is_superuser is True
    assert admin.email_verified is True


@pytest.mark.django_db
def test_user_email_must_be_unique():
    """Two users cannot share the same email (case-insensitive)."""
    from django.db import IntegrityError

    User = get_user_model()
    User.objects.create_user(email="test@example.com", password="pass1234567")
    with pytest.raises(IntegrityError):
        User.objects.create_user(email="test@example.com", password="pass7654321")
