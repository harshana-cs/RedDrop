from django.db import models
from register_donor.models import Donor

# Create your models here.
class Donation(models.Model):
    donor = models.ForeignKey(Donor, on_delete=models.CASCADE)
    hospital = models.CharField(max_length=200)
    blood_type = models.CharField(max_length=5)
    date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=[("pending", "Pending"), ("verified", "Verified")]
    )
class DonationCamp(models.Model):
    title = models.CharField(max_length=200)
    hospital = models.CharField(max_length=200)
    date = models.DateField()
    location = models.CharField(max_length=200)
    is_urgent = models.BooleanField(default=False)
class CampRegistration(models.Model):
    donor = models.ForeignKey(Donor, on_delete=models.CASCADE)
    camp = models.ForeignKey(DonationCamp, on_delete=models.CASCADE)
    registered_on = models.DateTimeField(auto_now_add=True)
