"""
Tests for the OrganisationScopeMiddleware.

We test the full request → middleware → response cycle using the Django
test client to ensure tenant resolution and rejection behave correctly.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import path

from apps.organisations.models import Membership, Organisation, Role

# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


@pytest.fixture
def user(db):
    User = get_user_model()
    return User.objects.create_user(
        email="alice@example.com",
        password="strongpass123",
    )


@pytest.fixture
def other_user(db):
    User = get_user_model()
    return User.objects.create_user(
        email="bob@example.com",
        password="strongpass123",
    )


@pytest.fixture
def organisation(db, user):
    return Organisation.objects.create(
        legal_name="Test Org",
        country_code="NG",
        default_currency="NGN",
        timezone_name="Africa/Lagos",
        created_by=user,
    )


@pytest.fixture
def accepted_membership(db, user, organisation):
    from django.utils import timezone

    return Membership.objects.create(
        user=user,
        organisation=organisation,
        role=Role.OWNER,
        accepted_at=timezone.now(),
    )


# ----------------------------------------------------------------------
# Middleware-level tests using a simple test view
# ----------------------------------------------------------------------


@pytest.fixture
def client_with_test_url(settings):
    """
    Inject a test URL `/test-tenant/` that returns whatever the middleware
    attached to the request. This lets us assert on middleware behaviour
    without needing real API endpoints yet.
    """
    from django.http import JsonResponse

    def view(request):
        return JsonResponse(
            {
                "has_organisation": request.organisation is not None,
                "organisation_slug": (request.organisation.slug if request.organisation else None),
                "role": request.role,
            }
        )

    # Override URLconf for this test only

    # We need to inject our test URL into the urlconf
    import config.urls as urlconf

    urlconf.urlpatterns = list(urlconf.urlpatterns) + [
        path("test-tenant/", view, name="test-tenant"),
    ]

    return Client()


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_anonymous_request_has_no_tenant_context(client_with_test_url):
    """Unauthenticated requests pass through without tenant context."""
    response = client_with_test_url.get("/test-tenant/")
    assert response.status_code == 200
    data = response.json()
    assert data["has_organisation"] is False
    assert data["role"] is None


@pytest.mark.django_db
def test_authenticated_request_without_org_header_has_no_tenant(client_with_test_url, user):
    """
    Authenticated request without X-Organisation-Id header succeeds but
    has no tenant attached. Views that require a tenant will reject it.
    """
    client_with_test_url.force_login(user)
    response = client_with_test_url.get("/test-tenant/")
    assert response.status_code == 200
    data = response.json()
    assert data["has_organisation"] is False


@pytest.mark.django_db
def test_authenticated_request_with_valid_org_header_attaches_tenant(
    client_with_test_url, user, organisation, accepted_membership
):
    """A request with a valid organisation header gets tenant context."""
    client_with_test_url.force_login(user)
    response = client_with_test_url.get(
        "/test-tenant/",
        HTTP_X_ORGANISATION_ID=str(organisation.public_id),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["has_organisation"] is True
    assert data["organisation_slug"] == "test-org"
    assert data["role"] == Role.OWNER


@pytest.mark.django_db
def test_request_with_invalid_org_id_returns_404(client_with_test_url, user):
    """A request with a non-existent organisation ID returns 404."""
    client_with_test_url.force_login(user)
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response = client_with_test_url.get(
        "/test-tenant/",
        HTTP_X_ORGANISATION_ID=fake_uuid,
    )
    assert response.status_code == 404
    assert response.json()["code"] == "TenantNotFound"


@pytest.mark.django_db
def test_request_with_malformed_org_id_returns_404(client_with_test_url, user):
    """A request with a malformed (non-UUID) organisation ID returns 404."""
    client_with_test_url.force_login(user)
    response = client_with_test_url.get(
        "/test-tenant/",
        HTTP_X_ORGANISATION_ID="not-a-uuid",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_user_without_membership_is_denied_access(
    client_with_test_url, other_user, organisation, accepted_membership
):
    """A user without a membership in the requested org gets 403."""
    # accepted_membership belongs to `user`, not `other_user`
    client_with_test_url.force_login(other_user)
    response = client_with_test_url.get(
        "/test-tenant/",
        HTTP_X_ORGANISATION_ID=str(organisation.public_id),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "TenantAccessDenied"


@pytest.mark.django_db
def test_pending_membership_is_denied_access(client_with_test_url, user, organisation):
    """A user whose membership hasn't been accepted yet gets 403."""
    # Create a membership but don't accept it (accepted_at is None)
    Membership.objects.create(
        user=user,
        organisation=organisation,
        role=Role.HR_MANAGER,
    )
    client_with_test_url.force_login(user)
    response = client_with_test_url.get(
        "/test-tenant/",
        HTTP_X_ORGANISATION_ID=str(organisation.public_id),
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_inactive_membership_is_denied_access(
    client_with_test_url, user, organisation, accepted_membership
):
    """A user whose membership has been deactivated gets 403."""
    accepted_membership.is_active = False
    accepted_membership.save()
    client_with_test_url.force_login(user)
    response = client_with_test_url.get(
        "/test-tenant/",
        HTTP_X_ORGANISATION_ID=str(organisation.public_id),
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_inactive_organisation_returns_404(
    client_with_test_url, user, organisation, accepted_membership
):
    """An inactive organisation behaves as if it doesn't exist."""
    organisation.is_active = False
    organisation.save()
    client_with_test_url.force_login(user)
    response = client_with_test_url.get(
        "/test-tenant/",
        HTTP_X_ORGANISATION_ID=str(organisation.public_id),
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_admin_path_is_exempt_from_tenant_resolution(client_with_test_url, user):
    """The /admin/ path bypasses tenant middleware."""
    user.is_staff = True
    user.save()
    client_with_test_url.force_login(user)
    # Admin URL doesn't require tenant context even though we pass a bogus header
    response = client_with_test_url.get(
        "/admin/",
        HTTP_X_ORGANISATION_ID="not-a-uuid",
    )
    # Should not return 404 from middleware; admin handles the request
    assert response.status_code in (200, 302)  # 302 if redirecting to login
