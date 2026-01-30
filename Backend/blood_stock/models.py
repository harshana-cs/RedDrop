from django.db import models
from hospital.models import Hospital

class BloodStock(models.Model):
    BLOOD_TYPES = [
        ("A+", "A+"), ("A-", "A-"),
        ("B+", "B+"), ("B-", "B-"),
        ("AB+", "AB+"), ("AB-", "AB-"),
        ("O+", "O+"), ("O-", "O-"),
    ]

    hospital = models.ForeignKey(
        Hospital,
        on_delete=models.CASCADE,
        related_name="blood_stock"
    )

    blood_type = models.CharField(max_length=3, choices=BLOOD_TYPES)
    units = models.PositiveIntegerField(default=0)
    minimum_required = models.PositiveIntegerField(default=10)

    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("hospital", "blood_type")

    def __str__(self):
        return f"{self.hospital.name} - {self.blood_type}"
