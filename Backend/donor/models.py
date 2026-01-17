from django.db import models
from blood_requests.models import BloodRequest
from register_donor.models import Donor


class Donation(models.Model):
    donor = models.ForeignKey(Donor, on_delete=models.CASCADE)
    hospital = models.CharField(max_length=200)
    blood_type = models.CharField(max_length=5)
    date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=[("pending", "Pending"), ("verified", "Verified")]
    )
    next_donation_date = models.DateField(null=True, blank=True)
class DonationConfirmation(models.Model):
    donor = models.ForeignKey(Donor, on_delete=models.CASCADE)
    request = models.ForeignKey(BloodRequest, on_delete=models.CASCADE)

    patient_confirmed = models.BooleanField(default=False)
    donor_confirmed = models.BooleanField(default=False)

    donation_date = models.DateTimeField(null=True, blank=True)  # 🔥 ADD THIS
    created_at = models.DateTimeField(auto_now_add=True)

