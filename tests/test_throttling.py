"""Tests for auth endpoint rate limiting."""

import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the throttle cache before and after each test."""
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_login_throttled_after_limit(api_client):
    """The 6th login attempt within the window is throttled."""
    url = reverse("accounts:login")
    payload = {"email": "attacker@example.com", "password": "wrongpass"}

    # First 5 attempts: 401 (bad credentials, but not throttled)
    for _ in range(5):
        response = api_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # 6th attempt: throttled
    response = api_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
def test_login_throttle_is_per_email(api_client):
    """Different emails have independent throttle counters."""
    url = reverse("accounts:login")

    # Exhaust the limit for email A
    for _ in range(5):
        api_client.post(url, {"email": "a@example.com", "password": "wrong"}, format="json")
    response_a = api_client.post(
        url, {"email": "a@example.com", "password": "wrong"}, format="json"
    )
    assert response_a.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    # A different email is still allowed
    response_b = api_client.post(
        url, {"email": "b@example.com", "password": "wrong"}, format="json"
    )
    assert response_b.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_signup_throttled_after_limit(api_client):
    """Signup is throttled after 10 attempts."""
    url = reverse("accounts:signup")

    def payload(i):
        return {
            "email": f"user{i}@example.com",
            "password": "strongpassword123",
            "full_name": "User",
            "organisation_name": "Org",
            "country_code": "NG",
            "default_currency": "NGN",
        }

    # 10 allowed (they'll succeed or fail on validation, but not throttle)
    for i in range(10):
        api_client.post(url, payload(i), format="json")

    # 11th is throttled
    response = api_client.post(url, payload(99), format="json")
    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
def test_password_reset_throttled_after_limit(api_client):
    """Password reset request is throttled after 3 attempts."""
    url = reverse("accounts:password-reset")
    payload = {"email": "someone@example.com"}

    for _ in range(3):
        response = api_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK

    response = api_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
