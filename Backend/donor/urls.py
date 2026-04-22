from django.urls import path
from .views import (
    api_donor_accept_request,
    api_donor_notifications,
    api_donor_notification_mark_read,
    api_donor_notifications_mark_all_read,
    donor_profile,
    donation_history,
    donation_camps,
    api_pending_confirmations,
    api_donor_confirm,
    api_donor_eligibility,
    api_donor_dashboard_stats,
    approved_donors_basic_view,   
    all_donors,
    api_donor_decline_request,
    
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
    path("notifications/mark-all-read/", api_donor_notifications_mark_all_read),
    path("accept-request/", api_donor_accept_request),
    path(
    "notifications/<int:notification_id>/read/",
    api_donor_notification_mark_read

),
    path("approved-donors-basic/", approved_donors_basic_view),
    path("api/all-donors/",  all_donors),
    path("decline-request/", api_donor_decline_request),

]
