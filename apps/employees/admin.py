"""Django admin for the Employee model."""

from __future__ import annotations

from django.contrib import admin

from .models import Employee


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "employee_number",
        "full_name",
        "organisation",
        "job_title",
        "employment_type",
        "status",
        "hire_date",
    )
    list_filter = ("status", "employment_type", "organisation", "department")
    search_fields = (
        "employee_number",
        "full_name",
        "email",
        "job_title",
    )
    ordering = ("organisation", "full_name")
    readonly_fields = ("public_id", "created_at", "updated_at")
    autocomplete_fields = ("organisation", "user")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "public_id",
                    "organisation",
                    "user",
                    "employee_number",
                )
            },
        ),
        (
            "Identity",
            {"fields": ("full_name", "email", "phone_number")},
        ),
        (
            "Employment",
            {
                "fields": (
                    "job_title",
                    "department",
                    "employment_type",
                    "status",
                    "hire_date",
                    "termination_date",
                )
            },
        ),
        (
            "Payment details",
            {
                "fields": (
                    "bank_name",
                    "bank_account_number",
                    "bank_account_name",
                )
            },
        ),
        (
            "Statutory",
            {"fields": ("tax_id", "pension_pin")},
        ),
        (
            "Audit",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )
