"""
Authentication views: login, refresh, logout, and current-user.

We use djangorestframework-simplejwt for the heavy lifting (token signing,
validation, refresh rotation, blacklisting) and add thin custom views
around it where we need extra behaviour (capturing last_login_ip,
shaping the response, returning the current user).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from .models import EmailVerification, PasswordResetToken
from .serializers import (
    CurrentUserSerializer,
    LoginSerializer,
    LogoutSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PasswordResetValidateTokenSerializer,
    ResendVerificationSerializer,
    SignupSerializer,
    VerifyEmailSerializer,
)
from .tasks import send_password_reset_email, send_verification_email

User = get_user_model()


def _client_ip(request) -> str | None:
    """Extract the client's IP from the request, respecting X-Forwarded-For."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        # First IP in the list is the original client
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class LoginView(TokenObtainPairView):
    """
    POST /api/v1/auth/login/
    Exchange email + password for an access/refresh token pair.

    Inherits the JWT issuance logic from simplejwt; overrides the
    serializer to use email instead of username and adds last_login_ip
    tracking on successful login.
    """

    permission_classes = [AllowAny]
    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        # On successful login, record the IP. This survives password
        # changes and is useful for security investigations.
        if response.status_code == status.HTTP_200_OK:
            user = request._user_for_ip_tracking  # set by the serializer
            user.last_login_ip = _client_ip(request)
            user.save(update_fields=["last_login_ip"])

        return response


class RefreshView(TokenRefreshView):
    """
    POST /api/v1/auth/refresh/
    Exchange a valid refresh token for a new access token (and a new
    refresh token, because we rotate).

    All logic is inherited from simplejwt — we just expose it under our
    URL namespace for consistency.
    """

    permission_classes = [AllowAny]


class LogoutView(APIView):
    """
    POST /api/v1/auth/logout/
    Blacklist the supplied refresh token so it can never be used again.

    The access token continues to work until it expires (max 15 minutes)
    because blacklisting access tokens would require a database lookup on
    every authenticated request, defeating the point of stateless JWT.
    For sensitive operations, the application should require fresh auth.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = LogoutSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            token = RefreshToken(serializer.validated_data["refresh"])
            token.blacklist()
        except TokenError:
            # Token is already invalid (expired, malformed, or blacklisted).
            # Logout should be idempotent — return success either way.
            pass

        return Response(
            {"detail": "Successfully logged out."},
            status=status.HTTP_205_RESET_CONTENT,
        )


class CurrentUserView(APIView):
    """
    GET /api/v1/auth/me/
    Return the currently authenticated user.

    Useful for the frontend to bootstrap user data after login or page
    refresh without storing it client-side.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = CurrentUserSerializer(request.user)
        return Response(serializer.data)


class SignupView(APIView):
    """
    POST /api/v1/auth/signup/
    Create a User, their first Organisation, and the Owner Membership.
    Sends a verification email asynchronously.
    """

    permission_classes = [AllowAny]
    serializer_class = SignupSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Generate verification token and queue the email task
        _, plain_token = EmailVerification.generate(user)
        send_verification_email.delay(user.id, plain_token)

        return Response(
            {
                "detail": (
                    "Account created. Please check your email to verify "
                    "your address before logging in."
                ),
                "user": {
                    "public_id": str(user.public_id),
                    "email": user.email,
                    "full_name": user.full_name,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyEmailView(APIView):
    """
    POST /api/v1/auth/verify-email/
    Consume a verification token and mark the user's email as verified.
    """

    permission_classes = [AllowAny]
    serializer_class = VerifyEmailSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        verification = EmailVerification.find_valid(serializer.validated_data["token"])
        if verification is None:
            return Response(
                {"detail": "Invalid or expired verification token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        verification.consume()
        verification.user.mark_email_verified()

        return Response(
            {"detail": "Email verified successfully. You can now log in."},
            status=status.HTTP_200_OK,
        )


class ResendVerificationView(APIView):
    """
    POST /api/v1/auth/resend-verification/
    Issue a new verification email. Idempotent and information-leak-safe.
    """

    permission_classes = [AllowAny]
    serializer_class = ResendVerificationSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Always return success — never reveal whether the email exists
        try:
            user = User.objects.get(email=serializer.validated_data["email"])
            if not user.email_verified and user.is_active:
                _, plain_token = EmailVerification.generate(user)
                send_verification_email.delay(user.id, plain_token)
        except User.DoesNotExist:
            pass  # don't leak whether the email is registered

        return Response(
            {
                "detail": (
                    "If an unverified account with this email exists, "
                    "a new verification link has been sent."
                )
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetRequestView(APIView):
    """
    POST /api/v1/auth/password-reset/
    Send a password reset email. Always returns success to prevent
    email enumeration — never reveals whether an account exists.
    """

    permission_classes = [AllowAny]
    serializer_class = PasswordResetRequestSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = User.objects.get(
                email=serializer.validated_data["email"],
                is_active=True,
            )
            _, plain_token = PasswordResetToken.generate(user)
            send_password_reset_email.delay(user.id, plain_token)
        except User.DoesNotExist:
            pass  # never leak whether the email is registered

        return Response(
            {
                "detail": (
                    "If an account with this email exists, " "a password reset link has been sent."
                )
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    """
    POST /api/v1/auth/password-reset/confirm/
    Validate the token and set the new password.
    Invalidates all existing JWT refresh tokens on success.
    """

    permission_classes = [AllowAny]
    serializer_class = PasswordResetConfirmSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        reset_token = PasswordResetToken.find_valid(serializer.validated_data["token"])
        if reset_token is None:
            return Response(
                {"detail": "Invalid or expired reset token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = reset_token.user

        # Set the new password
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])

        # Consume the token — can't be reused
        reset_token.consume()

        # Blacklist all outstanding refresh tokens for this user
        # so any stolen sessions are immediately invalidated
        try:
            from rest_framework_simplejwt.token_blacklist.models import (
                OutstandingToken,
            )
            from rest_framework_simplejwt.tokens import RefreshToken

            for token in OutstandingToken.objects.filter(user=user):
                try:
                    RefreshToken(token.token).blacklist()
                except Exception:
                    pass
        except Exception:
            pass  # blacklisting is best-effort; don't fail the reset

        return Response(
            {"detail": "Password reset successfully. You can now log in."},
            status=status.HTTP_200_OK,
        )


class PasswordResetValidateTokenView(APIView):
    """
    POST /api/v1/auth/password-reset/validate-token/
    Check if a token is valid without consuming it.
    Used by the frontend to show/hide the reset form before submission.
    """

    permission_classes = [AllowAny]
    serializer_class = PasswordResetValidateTokenSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = PasswordResetToken.find_valid(serializer.validated_data["token"])

        return Response(
            {"valid": token is not None},
            status=status.HTTP_200_OK,
        )
