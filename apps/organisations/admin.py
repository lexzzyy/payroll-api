"""Django admin registration for Organisation and Membership."""

from __future__ import annotations

from django.contrib import admin

from .models import Membership, Organisation


class MembershipInline(admin.TabularInline):
    """Show memberships inline on the Organisation detail page."""

    model = Membership
    fk_name = "organisation"
    extra = 0
    fields = ("user", "role", "is_active", "invited_at", "accepted_at")
    readonly_fields = ("invited_at", "accepted_at")
    autocomplete_fields = ("user",)


@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    list_display = (
        "legal_name",
        "trading_name",
        "country_code",
        "default_currency",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "country_code", "default_currency")
    search_fields = ("legal_name", "trading_name", "slug", "tax_id")
    ordering = ("legal_name",)
    readonly_fields = (
        "public_id",
        "slug",
        "created_at",
        "updated_at",
        "created_by",
    )
    fieldsets = (
        (None, {"fields": ("legal_name", "trading_name", "slug", "public_id")}),
        (
            "Localisation",
            {"fields": ("country_code", "default_currency", "timezone_name")},
        ),
        ("Tax & regulatory", {"fields": ("tax_id",)}),
        ("State", {"fields": ("is_active",)}),
        (
            "Audit",
            {
                "fields": ("created_at", "updated_at", "created_by"),
                "classes": ("collapse",),
            },
        ),
    )
    inlines = [MembershipInline]

    def save_model(self, request, obj, form, change):
        """Auto-populate created_by with the logged-in admin user on first save."""
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "organisation",
        "role",
        "is_active",
        "is_pending",
        "created_at",
    )
    list_filter = ("role", "is_active", "organisation")
    search_fields = (
        "user__email",
        "user__full_name",
        "organisation__legal_name",
    )
    ordering = ("-created_at",)
    autocomplete_fields = ("user", "organisation", "invited_by")
    readonly_fields = (
        "public_id",
        "invited_at",
        "accepted_at",
        "created_at",
        "updated_at",
    )
