"""
Custom manager for the User model.

The default Django UserManager assumes a `username` field. Since we use
`email` as the unique identifier instead, we need a manager that knows
how to create users without a username.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Manager for User model. Email is the unique identifier."""

    use_in_migrations = True

    def _create_user(
        self,
        email: str,
        password: str | None,
        **extra_fields: Any,
    ):
        """Create and save a User with the given email and password."""
        if not email:
            raise ValueError("Users must have an email address.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: Any,
    ):
        """Create a regular user (non-staff, non-superuser)."""
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: Any,
    ):
        """Create a superuser (full Django admin access)."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("email_verified", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)
