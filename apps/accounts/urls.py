"""URL routing for the accounts app."""

from django.urls import path

from .views import (
    CurrentUserView,
    LoginView,
    LogoutView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PasswordResetValidateTokenView,
    RefreshView,
    ResendVerificationView,
    SignupView,
    VerifyEmailView,
)

app_name = "accounts"

urlpatterns = [
    path("signup/", SignupView.as_view(), name="signup"),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", RefreshView.as_view(), name="refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", CurrentUserView.as_view(), name="me"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path(
        "resend-verification/",
        ResendVerificationView.as_view(),
        name="resend-verification",
    ),
    path("password-reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path(
        "password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path(
        "password-reset/validate-token/",
        PasswordResetValidateTokenView.as_view(),
        name="password-reset-validate-token",
    ),
]
