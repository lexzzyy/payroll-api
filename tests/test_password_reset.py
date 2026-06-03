"""Tests for the password reset flow."""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import PasswordResetToken


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def active_user(db):
    User = get_user_model()
    user = User.objects.create_user(
        email="resetme@example.com",
        password="originalpass123",
        full_name="Reset User",
    )
    user.email_verified = True
    user.save()
    return user


# ----------------------------------------------------------------------
# Request reset
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_password_reset_request_always_returns_success(api_client):
    """Never reveals whether the email is registered."""
    response = api_client.post(
        reverse("accounts:password-reset"),
        {"email": "nonexistent@example.com"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_password_reset_request_queues_email_for_valid_user(api_client, active_user):
    with patch("apps.accounts.views.send_password_reset_email.delay") as mock_task:
        response = api_client.post(
            reverse("accounts:password-reset"),
            {"email": "resetme@example.com"},
            format="json",
        )
    assert response.status_code == status.HTTP_200_OK
    mock_task.assert_called_once()
    assert mock_task.call_args[0][0] == active_user.id


# ----------------------------------------------------------------------
# Confirm reset
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_password_reset_confirm_sets_new_password(api_client, active_user):
    _, plain_token = PasswordResetToken.generate(active_user)

    response = api_client.post(
        reverse("accounts:password-reset-confirm"),
        {"token": plain_token, "new_password": "brandnewpass123"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK

    active_user.refresh_from_db()
    assert active_user.check_password("brandnewpass123")
    assert not active_user.check_password("originalpass123")


@pytest.mark.django_db
def test_password_reset_confirm_with_invalid_token_returns_400(api_client):
    response = api_client.post(
        reverse("accounts:password-reset-confirm"),
        {
            "token": "invalid-token-padding-to-pass-length-check-here",
            "new_password": "newpassword123",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_password_reset_token_is_single_use(api_client, active_user):
    _, plain_token = PasswordResetToken.generate(active_user)

    # First use succeeds
    api_client.post(
        reverse("accounts:password-reset-confirm"),
        {"token": plain_token, "new_password": "firstnewpass123"},
        format="json",
    )

    # Second use fails
    response = api_client.post(
        reverse("accounts:password-reset-confirm"),
        {"token": plain_token, "new_password": "secondnewpass123"},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_password_reset_confirm_with_weak_password_returns_400(api_client, active_user):
    _, plain_token = PasswordResetToken.generate(active_user)

    response = api_client.post(
        reverse("accounts:password-reset-confirm"),
        {"token": plain_token, "new_password": "short"},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "new_password" in response.data


# ----------------------------------------------------------------------
# Validate token
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_validate_token_returns_true_for_valid_token(api_client, active_user):
    _, plain_token = PasswordResetToken.generate(active_user)

    response = api_client.post(
        reverse("accounts:password-reset-validate-token"),
        {"token": plain_token},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["valid"] is True


@pytest.mark.django_db
def test_validate_token_returns_false_for_invalid_token(api_client):
    response = api_client.post(
        reverse("accounts:password-reset-validate-token"),
        {"token": "invalid-token-padding-to-pass-length-check-here"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["valid"] is False
