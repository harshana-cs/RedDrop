from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/profile/", views.api_donor_profile),
    path("dashboard/stats/", views.api_donor_dashboard_stats),
]
