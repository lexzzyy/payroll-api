from django.apps import AppConfig


class EmployeesConfig(AppConfig):
    """
    Employee records — the people who get paid.

    An Employee belongs to exactly one Organisation and may optionally be
    linked to a User account (many employees never log in; HR manages
    their records on their behalf).
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.employees"
    label = "employees"
    verbose_name = "Employees"
