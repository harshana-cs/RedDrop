from django.db import models
from hospital.models import Hospital
from django.utils import timezone

class BloodStock(models.Model):
    BLOOD_TYPES = [
        ("A+", "A+"), ("A-", "A-"),
        ("B+", "B+"), ("B-", "B-"),
        ("AB+", "AB+"), ("AB-", "AB-"),
        ("O+", "O+"), ("O-", "O-"),
    ]

    # NULL = Central Blood Bank (Admin)
    hospital = models.ForeignKey(
        Hospital,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="blood_stock"
    )

    blood_type = models.CharField(max_length=3, choices=BLOOD_TYPES)
    units = models.PositiveIntegerField(default=0)
    expiry_date = models.DateField(blank=True, null=True)
    minimum_required = models.PositiveIntegerField(default=10)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("hospital", "blood_type")

    def is_blood_bank_stock(self):
        return self.hospital is None

    def is_expired(self):
        return bool(self.expiry_date and self.expiry_date < timezone.now().date())

    def __str__(self):
        owner = "Blood Bank (Admin)" if self.hospital is None else self.hospital.name
        return f"{owner} - {self.blood_type}"
class BloodStockHistory(models.Model):

    TRANSACTION_TYPES = [
        ("add", "Add"),
        ("remove", "Remove"),
    ]

    hospital = models.ForeignKey(
        Hospital,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    blood_type = models.CharField(max_length=3)

    transaction_type = models.CharField(
        max_length=6,
        choices=TRANSACTION_TYPES
    )

    units = models.PositiveIntegerField()

    # where blood came from
    source = models.CharField(max_length=100, blank=True, null=True)

    # why removed or adjusted
    reason = models.CharField(max_length=100, blank=True, null=True)

    performed_by = models.CharField(max_length=100, default="Admin")

    new_balance = models.PositiveIntegerField()

    # expiry tracking
    expiry_date = models.DateField(blank=True, null=True)

    timestamp = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        
        if self.expiry_date:
            return self.expiry_date < timezone.now().date()
        return False

    def __str__(self):
        owner = "Admin Blood Bank" if self.hospital is None else self.hospital.name
        return f"{owner} - {self.blood_type} {self.transaction_type} {self.units}"
