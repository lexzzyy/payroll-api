"""Tests for the organisation invitation flow."""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.organisations.models import (
    Membership,
    Organisation,
    OrganisationInvitation,
    Role,
)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def org_with_owner(db):
    User = get_user_model()
    owner = User.objects.create_user(email="owner@example.com", password="pass1234567")
    owner.email_verified = True
    owner.save()
    org = Organisation.objects.create(
        legal_name="Invite Test Co",
        country_code="NG",
        default_currency="NGN",
        created_by=owner,
    )
    Membership.objects.create(
        user=owner, organisation=org, role=Role.OWNER, accepted_at=timezone.now()
    )
    return org, owner


def _auth(api_client, user, org):
    login = api_client.post(
        reverse("accounts:login"),
        {"email": user.email, "password": "pass1234567"},
        format="json",
    )
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {login.data['access']}",
        HTTP_X_ORGANISATION_ID=str(org.public_id),
    )
    return api_client


@pytest.mark.django_db
def test_owner_can_send_invitation(api_client, org_with_owner):
    org, owner = org_with_owner
    client = _auth(api_client, owner, org)
    with patch("apps.organisations.views.send_invitation_email.delay") as mock_task:
        response = client.post(
            reverse("organisations:invitations"),
            {"email": "newhire@example.com", "role": Role.EMPLOYEE},
            format="json",
        )
    assert response.status_code == status.HTTP_201_CREATED
    assert OrganisationInvitation.objects.filter(
        organisation=org, email="newhire@example.com"
    ).exists()
    mock_task.assert_called_once()


@pytest.mark.django_db
def test_employee_cannot_send_invitation(api_client, org_with_owner):
    org, owner = org_with_owner
    User = get_user_model()
    emp = User.objects.create_user(email="emp@example.com", password="pass1234567")
    emp.email_verified = True
    emp.save()
    Membership.objects.create(
        user=emp, organisation=org, role=Role.EMPLOYEE, accepted_at=timezone.now()
    )
    client = _auth(api_client, emp, org)
    response = client.post(
        reverse("organisations:invitations"),
        {"email": "x@example.com", "role": Role.EMPLOYEE},
        format="json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_cannot_invite_existing_member(api_client, org_with_owner):
    org, owner = org_with_owner
    client = _auth(api_client, owner, org)
    with patch("apps.organisations.views.send_invitation_email.delay"):
        response = client.post(
            reverse("organisations:invitations"),
            {"email": owner.email, "role": Role.EMPLOYEE},
            format="json",
        )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_cannot_send_duplicate_pending_invitation(api_client, org_with_owner):
    org, owner = org_with_owner
    client = _auth(api_client, owner, org)
    with patch("apps.organisations.views.send_invitation_email.delay"):
        client.post(
            reverse("organisations:invitations"),
            {"email": "dupe@example.com", "role": Role.EMPLOYEE},
            format="json",
        )
        response = client.post(
            reverse("organisations:invitations"),
            {"email": "dupe@example.com", "role": Role.EMPLOYEE},
            format="json",
        )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_new_user_accepts_invitation(api_client, org_with_owner):
    org, owner = org_with_owner
    invitation, plain_token = OrganisationInvitation.generate(
        organisation=org, email="brandnew@example.com", role=Role.EMPLOYEE, invited_by=owner
    )
    response = api_client.post(
        reverse("organisations:invitation-accept"),
        {
            "token": plain_token,
            "full_name": "Brand New",
            "password": "strongpass123",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK

    User = get_user_model()
    user = User.objects.get(email="brandnew@example.com")
    assert user.email_verified is True
    assert Membership.objects.filter(
        user=user, organisation=org, role=Role.EMPLOYEE, is_active=True
    ).exists()


@pytest.mark.django_db
def test_existing_user_accepts_invitation(api_client, org_with_owner):
    org, owner = org_with_owner
    User = get_user_model()
    existing = User.objects.create_user(email="existing@example.com", password="pass1234567")
    existing.email_verified = True
    existing.save()

    invitation, plain_token = OrganisationInvitation.generate(
        organisation=org, email="existing@example.com", role=Role.HR_MANAGER, invited_by=owner
    )
    response = api_client.post(
        reverse("organisations:invitation-accept"),
        {"token": plain_token},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    assert Membership.objects.filter(
        user=existing, organisation=org, role=Role.HR_MANAGER, is_active=True
    ).exists()


@pytest.mark.django_db
def test_invitation_token_is_single_use(api_client, org_with_owner):
    org, owner = org_with_owner
    invitation, plain_token = OrganisationInvitation.generate(
        organisation=org, email="once@example.com", role=Role.EMPLOYEE, invited_by=owner
    )
    api_client.post(
        reverse("organisations:invitation-accept"),
        {"token": plain_token, "password": "strongpass123"},
        format="json",
    )
    response = api_client.post(
        reverse("organisations:invitation-accept"),
        {"token": plain_token, "password": "strongpass123"},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_owner_can_revoke_invitation(api_client, org_with_owner):
    org, owner = org_with_owner
    invitation, _ = OrganisationInvitation.generate(
        organisation=org, email="revoke@example.com", role=Role.EMPLOYEE, invited_by=owner
    )
    client = _auth(api_client, owner, org)
    response = client.delete(
        reverse("organisations:invitation-revoke", args=[invitation.public_id])
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
    invitation.refresh_from_db()
    assert invitation.revoked_at is not None


@pytest.mark.django_db
def test_revoked_invitation_cannot_be_accepted(api_client, org_with_owner):
    org, owner = org_with_owner
    invitation, plain_token = OrganisationInvitation.generate(
        organisation=org, email="revoked@example.com", role=Role.EMPLOYEE, invited_by=owner
    )
    invitation.revoke()
    response = api_client.post(
        reverse("organisations:invitation-accept"),
        {"token": plain_token, "password": "strongpass123"},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
