from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/profile/", views.api_donor_profile),
    path("dashboard/stats/", views.api_donor_dashboard_stats),
    path("profile/", views.donor_profile),
    path("donation-history/", views.donation_history),
    path("donation-camps/", views.donation_camps),
    path("donation-camps/", views.donation_camps),
]
