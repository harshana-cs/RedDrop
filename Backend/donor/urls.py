from django.urls import path
from adminpanel.views import mark_notification_read
from .views import (
    api_donor_accept_request,
    api_donor_notifications,
    donor_profile,
    donation_history,
    donation_camps,
    api_pending_confirmations,
    api_donor_confirm,
    api_donor_eligibility,
    api_donor_dashboard_stats,
    # mark_notification_read,
    
)

urlpatterns = [
    path("profile/", donor_profile),
    path("donation-history/", donation_history),
    path("donation-camps/", donation_camps),
    path("pending-confirmations/", api_pending_confirmations),
    path("confirm/", api_donor_confirm),
    path("donor-eligibility/", api_donor_eligibility),
    path("dashboard-stats/", api_donor_dashboard_stats),
    path("notifications/", api_donor_notifications),
    path("accept-request/", api_donor_accept_request),
    path(
    "notifications/<int:notification_id>/read/",
    mark_notification_read
),
]