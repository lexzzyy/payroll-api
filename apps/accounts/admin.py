"""Django admin registration for the User model."""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Custom UserAdmin tailored to the email-based User model."""

    list_display = (
        "email",
        "full_name",
        "is_staff",
        "is_active",
        "email_verified",
        "created_at",
    )
    list_filter = ("is_staff", "is_active", "email_verified", "country_code")
    search_fields = ("email", "full_name", "phone_number")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at", "last_login", "last_login_ip")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            _("Personal info"),
            {"fields": ("full_name", "phone_number")},
        ),
        (
            _("Localisation"),
            {"fields": ("preferred_language", "country_code", "timezone_name")},
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "email_verified",
                    "email_verified_at",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            _("Audit"),
            {"fields": ("last_login", "last_login_ip", "created_at", "updated_at")},
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )
