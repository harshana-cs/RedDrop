from django.db import models
from django.contrib.auth.hashers import make_password, check_password as django_check_password


class Donor(models.Model):
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(unique=True, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=20, blank=True, null=True)
    blood_type = models.CharField(max_length=5, blank=True, null=True)

    address = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    zip_code = models.CharField(max_length=20, blank=True, null=True)

    # 🔴 ADD THESE FOR GPS LOCATION
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    location_updated_at = models.DateTimeField(null=True, blank=True)

    emergency_contact_name = models.CharField(max_length=100, blank=True, null=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True, null=True)

    weight = models.PositiveIntegerField(blank=True, null=True)
    has_diabetes = models.BooleanField(default=False)
    has_hypertension = models.BooleanField(default=False)
    has_heart_disease = models.BooleanField(default=False)
    no_medical_conditions = models.BooleanField(default=False)

    citizenship_id = models.FileField(upload_to='citizenships/', blank=True, null=True)
    photo = models.ImageField(upload_to='donor_photos/', blank=True, null=True)

    accepted_terms = models.BooleanField(default=False)
    consent_notifications = models.BooleanField(default=False)

    created_on = models.DateTimeField(auto_now_add=True)

    is_profile_completed = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.first_name} {self.last_name or ''}"