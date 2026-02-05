from django.db import models
from hospital.models import Hospital

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
    minimum_required = models.PositiveIntegerField(default=10)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("hospital", "blood_type")

    def is_blood_bank_stock(self):
        return self.hospital is None

    def __str__(self):
        owner = "Blood Bank (Admin)" if self.hospital is None else self.hospital.name
        return f"{owner} - {self.blood_type}"
class BloodStockHistory(models.Model):
    TRANSACTION_TYPES = [
        ("add", "Add"),
        ("remove", "Remove"),
    ]

    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE)
    blood_type = models.CharField(max_length=3)
    transaction_type = models.CharField(max_length=6, choices=TRANSACTION_TYPES)
    units = models.PositiveIntegerField()
    source = models.CharField(max_length=100, blank=True, null=True)
    reason = models.CharField(max_length=100, blank=True, null=True)
    performed_by = models.CharField(max_length=100, default="Hospital")
    new_balance = models.PositiveIntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.blood_type} {self.transaction_type} {self.units}"
