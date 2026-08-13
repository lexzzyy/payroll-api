"""Tests for role-based permission classes."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.organisations.models import Membership, Organisation, Role


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def organisation(db):
    User = get_user_model()
    owner = User.objects.create_user(email="owner@example.com", password="pass1234567")
    owner.email_verified = True
    owner.save()
    org = Organisation.objects.create(
        legal_name="Perm Test Co",
        country_code="NG",
        default_currency="NGN",
        created_by=owner,
    )
    return org


def _make_member(org, email, role):
    """Helper: create a verified user with an accepted membership."""
    User = get_user_model()
    user = User.objects.create_user(email=email, password="pass1234567")
    user.email_verified = True
    user.save()
    Membership.objects.create(
        user=user,
        organisation=org,
        role=role,
        accepted_at=timezone.now(),
    )
    return user


def _auth(api_client, user, org):
    """Log a user in and set the org header. Returns the client."""
    login = api_client.post(
        reverse("accounts:login"),
        {"email": user.email, "password": "pass1234567"},
        format="json",
    )
    token = login.data["access"]
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {token}",
        HTTP_X_ORGANISATION_ID=str(org.public_id),
    )
    return api_client


# ----------------------------------------------------------------------
# Member area — any role can access
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_owner_can_access_member_area(api_client, organisation):
    owner = _make_member(organisation, "o@example.com", Role.OWNER)
    client = _auth(api_client, owner, organisation)
    response = client.get(reverse("organisations:member-area"))
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_employee_can_access_member_area(api_client, organisation):
    emp = _make_member(organisation, "e@example.com", Role.EMPLOYEE)
    client = _auth(api_client, emp, organisation)
    response = client.get(reverse("organisations:member-area"))
    assert response.status_code == status.HTTP_200_OK


# ----------------------------------------------------------------------
# HR area — Owner and HR Manager only
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_hr_manager_can_access_hr_area(api_client, organisation):
    hr = _make_member(organisation, "hr@example.com", Role.HR_MANAGER)
    client = _auth(api_client, hr, organisation)
    response = client.get(reverse("organisations:hr-area"))
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_owner_can_access_hr_area(api_client, organisation):
    owner = _make_member(organisation, "o2@example.com", Role.OWNER)
    client = _auth(api_client, owner, organisation)
    response = client.get(reverse("organisations:hr-area"))
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_employee_cannot_access_hr_area(api_client, organisation):
    emp = _make_member(organisation, "e2@example.com", Role.EMPLOYEE)
    client = _auth(api_client, emp, organisation)
    response = client.get(reverse("organisations:hr-area"))
    assert response.status_code == status.HTTP_403_FORBIDDEN


# ----------------------------------------------------------------------
# Owner area — Owner only
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_owner_can_access_owner_area(api_client, organisation):
    owner = _make_member(organisation, "o3@example.com", Role.OWNER)
    client = _auth(api_client, owner, organisation)
    response = client.get(reverse("organisations:owner-area"))
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_hr_manager_cannot_access_owner_area(api_client, organisation):
    hr = _make_member(organisation, "hr2@example.com", Role.HR_MANAGER)
    client = _auth(api_client, hr, organisation)
    response = client.get(reverse("organisations:owner-area"))
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_employee_cannot_access_owner_area(api_client, organisation):
    emp = _make_member(organisation, "e3@example.com", Role.EMPLOYEE)
    client = _auth(api_client, emp, organisation)
    response = client.get(reverse("organisations:owner-area"))
    assert response.status_code == status.HTTP_403_FORBIDDEN


# ----------------------------------------------------------------------
# No tenant context — access denied
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_no_org_header_denies_hr_area(api_client, organisation):
    hr = _make_member(organisation, "hr3@example.com", Role.HR_MANAGER)
    login = api_client.post(
        reverse("accounts:login"),
        {"email": hr.email, "password": "pass1234567"},
        format="json",
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    response = api_client.get(reverse("organisations:hr-area"))
    assert response.status_code == status.HTTP_403_FORBIDDEN
