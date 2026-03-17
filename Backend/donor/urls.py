from django.urls import path
from .views import (
    # api_compatible_donors,
    # api_donor_profile,
    api_donor_accept_request,
    api_donor_notifications,
    donor_profile,
    donation_history,
    donation_camps,
    api_pending_confirmations,
    api_donor_confirm,
    api_donor_eligibility,
    api_donor_dashboard_stats,
)

urlpatterns = [
    # Donor profile
    path("profile/", donor_profile),

    # Donation history
    path("donation-history/", donation_history),

    # Donation camps
    path("donation-camps/", donation_camps),

    # Pending confirmations (patient → donor)
    path("pending-confirmations/", api_pending_confirmations),

    # Donor confirms OTP
    path("confirm/", api_donor_confirm),
    path("donor-eligibility/", api_donor_eligibility),
    path("dashboard-stats/", api_donor_dashboard_stats),
    path("notifications/", api_donor_notifications),
    path("accept-request/", api_donor_accept_request),
    
]
