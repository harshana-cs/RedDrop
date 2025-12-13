from django.db import models
from django.contrib.auth.models import User

BLOOD_TYPES = [
    ('A+', 'A+'), ('A-', 'A-'), ('B+', 'B+'), ('B-', 'B-'),
    ('AB+', 'AB+'), ('AB-', 'AB-'), ('O+', 'O+'), ('O-', 'O-'),
]

URGENCY_LEVELS = [
    ('Critical', 'Critical'), ('High', 'High'), ('Medium', 'Medium'), ('Low', 'Low')
]

class BloodRequest(models.Model):
    patient = models.ForeignKey(User, on_delete=models.CASCADE)
    blood_type = models.CharField(max_length=3, choices=BLOOD_TYPES)
    units_required = models.PositiveIntegerField()
    urgency = models.CharField(max_length=10, choices=URGENCY_LEVELS)
    district = models.CharField(max_length=50)
    hospital = models.CharField(max_length=100)
    required_date = models.DateField()
    reason = models.TextField()
    contact_name = models.CharField(max_length=100)
    contact_phone = models.CharField(max_length=20)
    hospital_doc = models.FileField(upload_to='hospital_docs/')
    doctor_note = models.FileField(upload_to='doctor_notes/')
    created_at = models.DateTimeField(auto_now_add=True)
    fulfilled = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.patient.username} - {self.blood_type} ({self.units_required} units)"
