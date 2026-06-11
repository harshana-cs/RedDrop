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
    donor = models.ForeignKey(
        Donor,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    request = models.ForeignKey(BloodRequest, on_delete=models.CASCADE)

    confirmation_code = models.CharField(max_length=4, null=True, blank=True)
    patient_confirmed = models.BooleanField(default=False)
    donor_confirmed = models.BooleanField(default=False)

    donation_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

# models.py
from django.db import models

class DonationCertificate(models.Model):
    donation = models.OneToOneField(Donation, on_delete=models.CASCADE, related_name='certificate')
    pdf_file = models.FileField(upload_to='certificates/')  # Auto-stores in MEDIA_ROOT
    serial_number = models.CharField(max_length=100, unique=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    downloaded_count = models.IntegerField(default=0)
    
    def __str__(self):
        return f"Certificate for Donation #{self.donation.id}"