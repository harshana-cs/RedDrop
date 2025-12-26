from django.db import models
from django.contrib.auth.hashers import make_password, check_password   as django_check_password

class GoogleSignup(models.Model):

    USER_TYPES = [
        ("patient", "Patient"),
        ("doctor", "Doctor"),
        ("donor", "Donor"),
        ("admin", "Admin"),
    ]

    fullname = models.CharField(max_length=150)  # Added fullname field
    email = models.EmailField(unique=True)
    credential = models.TextField(default="")
    verification_code = models.CharField(max_length=6)
    is_verified = models.BooleanField(default=False)
    user_type = models.CharField(max_length=20, choices=USER_TYPES, default="patient")
    created_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email
class Patient(models.Model):
    # Basic Info
    fullname = models.CharField(max_length=100)
    emailaddress = models.EmailField(unique=True)

    # Manual signup only; Google users leave this empty
    phonenumber = models.CharField(max_length=20, blank=True, null=True)

    password = models.CharField(max_length=255, blank=True, null=True)
    confirm_password = models.CharField(max_length=255, blank=True, null=True)

    # Additional profile fields (all optional, filled later)
    date_of_birth = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=20, blank=True, null=True)
    blood_type = models.CharField(max_length=15, blank=True, null=True)

    # Contact Information
    street_address = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    zip_code = models.CharField(max_length=20, blank=True, null=True)

    # Medical Information
    weight = models.CharField(max_length=20, blank=True, null=True)
    height = models.CharField(max_length=20, blank=True, null=True)
    allergies = models.TextField(blank=True, null=True)
    medical_conditions = models.TextField(blank=True, null=True)

    # Emergency Contact
    emergency_name = models.CharField(max_length=100, blank=True, null=True)
    emergency_relationship = models.CharField(max_length=100, blank=True, null=True)
    emergency_phone = models.CharField(max_length=20, blank=True, null=True)
    emergency_email = models.EmailField(blank=True, null=True)

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        # Pass the stored hashed password as the second argument
        return django_check_password(raw_password, self.password)


class Donor(models.Model):
    # -------------------- Personal Information
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=20, blank=True, null=True)
    blood_type = models.CharField(max_length=5, blank=True, null=True)

    # -------------------- Address Information
    address = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    zip_code = models.CharField(max_length=20, blank=True, null=True)

    # -------------------- Emergency Contact
    emergency_contact_name = models.CharField(max_length=100, blank=True, null=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True, null=True)

    # -------------------- Medical Information
    weight = models.PositiveIntegerField(blank=True, null=True, help_text="Weight in kg")
    has_diabetes = models.BooleanField(default=False)
    has_hypertension = models.BooleanField(default=False)
    has_heart_disease = models.BooleanField(default=False)
    no_medical_conditions = models.BooleanField(default=False)

    # -------------------- File Uploads
    citizenship_id = models.FileField(upload_to='citizenships/', blank=True, null=True)
    photo = models.ImageField(upload_to='donor_photos/', blank=True, null=True)

    # -------------------- Consents
    accepted_terms = models.BooleanField(default=False)
    consent_notifications = models.BooleanField(default=False)

    # -------------------- Auth (manual signup only)
    password = models.CharField(max_length=255, blank=True, null=True)
    confirm_password = models.CharField(max_length=255, blank=True, null=True)

    created_on = models.DateTimeField(auto_now_add=True)

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return django_check_password(raw_password, self.password)

    def __str__(self):
        return f"{self.first_name} {self.last_name or ''}"
