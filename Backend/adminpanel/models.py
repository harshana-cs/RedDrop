from django.db import models
class DonationCamp(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    hospital_name = models.CharField(max_length=200)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    location = models.CharField(max_length=200)
    total_slots = models.IntegerField(default=0)
    filled_slots = models.IntegerField(default=0)
    is_urgent = models.BooleanField(default=False)

    def __str__(self):
        return self.title

from django.db import models
from hospital.models import Hospital


class Notification(models.Model):

    TYPE_CHOICES = [
        ("blood_request", "Blood Request"),
        ("donor_registration", "Donor Registration"),
        ("hospital_registration", "Hospital Registration"),
        ("blood_request_approved", "Blood Request Approved"),
    ]

    title = models.CharField(max_length=255)
    message = models.TextField()

    type = models.CharField(max_length=50, choices=TYPE_CHOICES)

    # who receives the notification
    hospital = models.ForeignKey(
        Hospital,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
class HospitalAuditLog(models.Model):

    ACTION_TYPES = [
        ("login", "Hospital Login"),
        ("blood_request_create", "Blood Request Created"),
        ("stock_add", "Blood Stock Added"),
        ("stock_remove", "Blood Stock Removed"),
        ("inventory_update", "Inventory Updated"),
        ("document_upload", "Document Uploaded"),
    ]

    hospital = models.ForeignKey(
        "hospital.Hospital",
        on_delete=models.CASCADE
    )

    action = models.CharField(max_length=50, choices=ACTION_TYPES)

    description = models.TextField()

    ip_address = models.GenericIPAddressField(null=True, blank=True)

    metadata = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.hospital.name} - {self.action}"