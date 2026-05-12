"""
Smoke tests — verify that the Django project loads correctly.
These are temporary; they'll be replaced by real tests once we build apps.
"""

import django
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model

from apps.organisations.models import Membership, Organisation, Role


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


@pytest.mark.django_db
def test_organisation_creation():
    """Organisations are created with auto-generated slugs."""
    User = get_user_model()
    creator = User.objects.create_user(
        email="founder@example.com",
        password="securepass123",
    )
    org = Organisation.objects.create(
        legal_name="Acme Corp",
        country_code="NG",
        default_currency="NGN",
        timezone_name="Africa/Lagos",
        created_by=creator,
    )
    assert org.slug == "acme-corp"
    assert org.is_active is True
    assert str(org) == "Acme Corp"


@pytest.mark.django_db
def test_organisation_slug_uniqueness():
    """Duplicate org names get differentiated slugs."""
    User = get_user_model()
    creator = User.objects.create_user(
        email="founder2@example.com",
        password="securepass123",
    )
    org1 = Organisation.objects.create(
        legal_name="Same Name Ltd",
        country_code="NG",
        default_currency="NGN",
        created_by=creator,
    )
    org2 = Organisation.objects.create(
        legal_name="Same Name Ltd",
        country_code="GB",
        default_currency="GBP",
        created_by=creator,
    )
    assert org1.slug == "same-name-ltd"
    assert org2.slug == "same-name-ltd-2"


@pytest.mark.django_db
def test_membership_links_user_to_organisation():
    """A Membership row connects a User to an Organisation with a Role."""
    User = get_user_model()
    user = User.objects.create_user(
        email="member@example.com",
        password="securepass123",
    )
    org = Organisation.objects.create(
        legal_name="Member Test Co",
        country_code="NG",
        default_currency="NGN",
        created_by=user,
    )
    membership = Membership.objects.create(
        user=user,
        organisation=org,
        role=Role.OWNER,
    )
    assert membership.is_owner is True
    assert membership.is_hr_manager is False
    assert membership.is_pending is True  # not yet accepted
    membership.accept()
    assert membership.is_pending is False


@pytest.mark.django_db
def test_user_cannot_have_two_memberships_in_same_org():
    """The (user, organisation) pair must be unique."""
    from django.db import IntegrityError

    User = get_user_model()
    user = User.objects.create_user(
        email="dup@example.com",
        password="securepass123",
    )
    org = Organisation.objects.create(
        legal_name="Dup Test Co",
        country_code="NG",
        default_currency="NGN",
        created_by=user,
    )
    Membership.objects.create(user=user, organisation=org, role=Role.OWNER)
    with pytest.raises(IntegrityError):
        Membership.objects.create(
            user=user,
            organisation=org,
            role=Role.HR_MANAGER,
        )


@pytest.mark.django_db
def test_user_can_have_memberships_in_multiple_orgs():
    """A single user can be a member of many organisations."""
    User = get_user_model()
    user = User.objects.create_user(
        email="multi@example.com",
        password="securepass123",
    )
    org_a = Organisation.objects.create(
        legal_name="Org A",
        country_code="NG",
        default_currency="NGN",
        created_by=user,
    )
    org_b = Organisation.objects.create(
        legal_name="Org B",
        country_code="GB",
        default_currency="GBP",
        created_by=user,
    )
    Membership.objects.create(user=user, organisation=org_a, role=Role.OWNER)
    Membership.objects.create(
        user=user,
        organisation=org_b,
        role=Role.HR_MANAGER,
    )
    assert user.memberships.count() == 2


@pytest.mark.django_db
def test_organisation_can_be_created_without_creator():
    """System-seeded orgs (e.g. from data imports) don't require a creator."""
    org = Organisation.objects.create(
        legal_name="System Seeded Org",
        country_code="NG",
        default_currency="NGN",
    )
    assert org.created_by is None
    assert org.is_active is True
