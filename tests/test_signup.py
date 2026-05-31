"""Tests for signup, email verification, and resend flows."""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import EmailVerification
from apps.organisations.models import Membership, Organisation, Role


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def valid_signup_data():
    return {
        "email": "newuser@example.com",
        "password": "strongpassword123",
        "full_name": "New User",
        "organisation_name": "Test Org Ltd",
        "country_code": "NG",
        "default_currency": "NGN",
        "timezone_name": "Africa/Lagos",
    }


@pytest.mark.django_db
def test_signup_creates_user_organisation_and_membership(api_client, valid_signup_data):
    with patch("apps.accounts.views.send_verification_email.delay") as mock_task:
        response = api_client.post(reverse("accounts:signup"), valid_signup_data, format="json")

    assert response.status_code == status.HTTP_201_CREATED

    User = get_user_model()
    user = User.objects.get(email="newuser@example.com")
    assert user.full_name == "New User"
    assert user.email_verified is False
    assert user.country_code == "NG"

    org = Organisation.objects.get(legal_name="Test Org Ltd")
    assert org.country_code == "NG"
    assert org.default_currency == "NGN"

    membership = Membership.objects.get(user=user, organisation=org)
    assert membership.role == Role.OWNER
    assert membership.accepted_at is not None

    # Verification task was queued
    mock_task.assert_called_once()
    assert mock_task.call_args[0][0] == user.id


@pytest.mark.django_db
def test_signup_with_duplicate_email_is_rejected(api_client, valid_signup_data):
    User = get_user_model()
    User.objects.create_user(email=valid_signup_data["email"], password="anyoldpassword123")

    response = api_client.post(reverse("accounts:signup"), valid_signup_data, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "email" in response.data


@pytest.mark.django_db
def test_signup_with_weak_password_is_rejected(api_client, valid_signup_data):
    valid_signup_data["password"] = "short"
    response = api_client.post(reverse("accounts:signup"), valid_signup_data, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "password" in response.data


@pytest.mark.django_db
def test_signup_normalises_email_to_lowercase(api_client, valid_signup_data):
    valid_signup_data["email"] = "MixedCase@Example.COM"
    with patch("apps.accounts.views.send_verification_email.delay"):
        api_client.post(reverse("accounts:signup"), valid_signup_data, format="json")

    User = get_user_model()
    assert User.objects.filter(email="mixedcase@example.com").exists()


@pytest.mark.django_db
def test_email_verification_consumes_valid_token(api_client):
    User = get_user_model()
    user = User.objects.create_user(email="verifyme@example.com", password="pass1234567")
    _, plain_token = EmailVerification.generate(user)

    response = api_client.post(
        reverse("accounts:verify-email"), {"token": plain_token}, format="json"
    )

    assert response.status_code == status.HTTP_200_OK
    user.refresh_from_db()
    assert user.email_verified is True


@pytest.mark.django_db
def test_invalid_verification_token_returns_400(api_client):
    response = api_client.post(
        reverse("accounts:verify-email"),
        {"token": "not-a-real-token-just-padding-to-pass-length"},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_used_verification_token_cannot_be_reused(api_client):
    User = get_user_model()
    user = User.objects.create_user(email="single@example.com", password="pass1234567")
    _, plain_token = EmailVerification.generate(user)

    # First use succeeds
    response1 = api_client.post(
        reverse("accounts:verify-email"), {"token": plain_token}, format="json"
    )
    assert response1.status_code == status.HTTP_200_OK

    # Second use fails
    response2 = api_client.post(
        reverse("accounts:verify-email"), {"token": plain_token}, format="json"
    )
    assert response2.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_expired_verification_token_returns_400(api_client):
    from datetime import timedelta

    from django.utils import timezone

    User = get_user_model()
    user = User.objects.create_user(email="expired@example.com", password="pass1234567")
    verification, plain_token = EmailVerification.generate(user)

    # Manually expire it
    verification.expires_at = timezone.now() - timedelta(hours=1)
    verification.save()

    response = api_client.post(
        reverse("accounts:verify-email"), {"token": plain_token}, format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_resend_verification_always_returns_success(api_client):
    """Resend never reveals whether the email exists or not."""
    response = api_client.post(
        reverse("accounts:resend-verification"),
        {"email": "nonexistent@example.com"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_resend_verification_queues_email_for_unverified_user(api_client):
    User = get_user_model()
    User.objects.create_user(email="needsverify@example.com", password="pass1234567")

    with patch("apps.accounts.views.send_verification_email.delay") as mock_task:
        response = api_client.post(
            reverse("accounts:resend-verification"),
            {"email": "needsverify@example.com"},
            format="json",
        )

    assert response.status_code == status.HTTP_200_OK
    mock_task.assert_called_once()


@pytest.mark.django_db
def test_resend_verification_does_not_queue_for_verified_user(api_client):
    User = get_user_model()
    user = User.objects.create_user(email="already@example.com", password="pass1234567")
    user.email_verified = True
    user.save()

    with patch("apps.accounts.views.send_verification_email.delay") as mock_task:
        api_client.post(
            reverse("accounts:resend-verification"),
            {"email": "already@example.com"},
            format="json",
        )

    mock_task.assert_not_called()
