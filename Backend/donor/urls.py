from django.urls import path
from .views import (
    api_donor_profile,
    donor_profile,
    donation_history,
    donation_camps,
    api_pending_confirmations,
    api_donor_confirm,
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
]
