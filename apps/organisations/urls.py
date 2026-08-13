"""URL routing for the organisations app."""

from django.urls import path

from .views import HRManagerOnlyView, MemberOnlyView, OwnerOnlyView

app_name = "organisations"

urlpatterns = [
    path("member-area/", MemberOnlyView.as_view(), name="member-area"),
    path("hr-area/", HRManagerOnlyView.as_view(), name="hr-area"),
    path("owner-area/", OwnerOnlyView.as_view(), name="owner-area"),
]
