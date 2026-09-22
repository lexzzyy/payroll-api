"""Tests for the Employee model."""

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.utils import timezone

from apps.employees.models import Employee, EmployeeStatus, EmploymentType
from apps.organisations.models import Organisation


@pytest.fixture
def org(db):
    User = get_user_model()
    creator = User.objects.create_user(email="creator@example.com", password="pass1234567")
    return Organisation.objects.create(
        legal_name="Employee Test Co",
        country_code="NG",
        default_currency="NGN",
        created_by=creator,
    )


@pytest.fixture
def other_org(db):
    User = get_user_model()
    creator = User.objects.create_user(email="creator2@example.com", password="pass1234567")
    return Organisation.objects.create(
        legal_name="Other Co",
        country_code="GB",
        default_currency="GBP",
        created_by=creator,
    )


@pytest.mark.django_db
def test_employee_creation(org):
    """An employee can be created with the minimum required fields."""
    emp = Employee.objects.create(
        organisation=org,
        employee_number="EMP001",
        full_name="Ada Obi",
        hire_date=timezone.now().date(),
    )
    assert emp.employee_number == "EMP001"
    assert emp.status == EmployeeStatus.ACTIVE
    assert emp.employment_type == EmploymentType.FULL_TIME
    assert emp.is_active is True
    assert emp.short_name == "Ada"
    assert str(emp) == "Ada Obi (EMP001)"


@pytest.mark.django_db
def test_employee_without_user_account(org):
    """An employee need not be linked to a login account."""
    emp = Employee.objects.create(
        organisation=org,
        employee_number="EMP002",
        full_name="No Login",
        hire_date=timezone.now().date(),
    )
    assert emp.user is None


@pytest.mark.django_db
def test_employee_can_link_to_user(org):
    """An employee may optionally be linked to a User."""
    User = get_user_model()
    user = User.objects.create_user(email="linked@example.com", password="pass1234567")
    emp = Employee.objects.create(
        organisation=org,
        user=user,
        employee_number="EMP003",
        full_name="Linked User",
        hire_date=timezone.now().date(),
    )
    assert emp.user == user
    assert user.employee_records.count() == 1


@pytest.mark.django_db
def test_employee_number_unique_within_org(org):
    """Two employees in the same org cannot share an employee number."""
    Employee.objects.create(
        organisation=org,
        employee_number="EMP001",
        full_name="First",
        hire_date=timezone.now().date(),
    )
    with pytest.raises(IntegrityError):
        Employee.objects.create(
            organisation=org,
            employee_number="EMP001",
            full_name="Duplicate",
            hire_date=timezone.now().date(),
        )


@pytest.mark.django_db
def test_same_employee_number_allowed_across_orgs(org, other_org):
    """Two different orgs can both have EMP001 — uniqueness is per-org."""
    emp_a = Employee.objects.create(
        organisation=org,
        employee_number="EMP001",
        full_name="Org A Employee",
        hire_date=timezone.now().date(),
    )
    emp_b = Employee.objects.create(
        organisation=other_org,
        employee_number="EMP001",
        full_name="Org B Employee",
        hire_date=timezone.now().date(),
    )
    assert emp_a.employee_number == emp_b.employee_number
    assert emp_a.organisation != emp_b.organisation


@pytest.mark.django_db
def test_tenant_scoped_manager_filters_by_organisation(org, other_org):
    """for_organisation returns only that org's employees."""
    Employee.objects.create(
        organisation=org,
        employee_number="A1",
        full_name="A One",
        hire_date=timezone.now().date(),
    )
    Employee.objects.create(
        organisation=other_org,
        employee_number="B1",
        full_name="B One",
        hire_date=timezone.now().date(),
    )
    org_a_employees = Employee.objects.for_organisation(org)
    assert org_a_employees.count() == 1
    assert org_a_employees.first().full_name == "A One"
