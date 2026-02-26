from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from loginsignup.models import Patient
from register_donor.models import Donor
class HospitalLocation(models.Model):
    name = models.CharField(max_length=255)
    district = models.CharField(max_length=100)

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('name', 'district')

    def __str__(self):
        return f"{self.name} - {self.district}"

class BloodRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
    ]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    blood_type = models.CharField(max_length=3)
    units_required = models.PositiveIntegerField()
    urgency = models.CharField(max_length=10)
    district = models.CharField(max_length=50)
    hospital = models.ForeignKey(
    HospitalLocation,
    on_delete=models.CASCADE
)

    required_date = models.DateField()
    reason = models.TextField()
    contact_name = models.CharField(max_length=100)
    contact_phone = models.CharField(max_length=20)
    hospital_doc = models.FileField(upload_to='hospital_docs/')
    doctor_note = models.FileField(upload_to='doctor_notes/')
    created_at = models.DateTimeField(auto_now_add=True)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    fulfilled = models.BooleanField(default=False)

#     assigned_donor = models.ForeignKey(
#     Donor, on_delete=models.SET_NULL, null=True, blank=True
# )
    otp = models.CharField(max_length=6, null=True, blank=True)
    otp_expires_at = models.DateTimeField(null=True, blank=True)

    # ✅ NEW FIELD (VERY IMPORTANT)
    patient_confirmed = models.BooleanField(default=False)
    donation_date = models.DateTimeField(null=True, blank=True)


    def __str__(self):
        return f"{self.patient.username} - {self.blood_type}"


