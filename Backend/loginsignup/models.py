from django.db import models
from django.contrib.auth.hashers import make_password, check_password as django_check_password


# -------------------------------------------------
# GOOGLE SIGNUP (ONLY FOR VERIFICATION)
# -------------------------------------------------
class GoogleSignup(models.Model):
    fullname = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    credential = models.TextField(default="")
    verification_code = models.CharField(max_length=6)
    is_verified = models.BooleanField(default=False)
    created_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email


# -------------------------------------------------
# PATIENT = BASE USER (LOGIN IDENTITY)
# -------------------------------------------------
class Patient(models.Model):
    fullname = models.CharField(max_length=100)
    emailaddress = models.EmailField(unique=True)

    password = models.CharField(max_length=255, blank=True, null=True)

    created_on = models.DateTimeField(auto_now_add=True)

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return django_check_password(raw_password, self.password)

    def __str__(self):
        return self.emailaddress


# -------------------------------------------------
# DONOR = OPTIONAL FEATURE (LINKED TO PATIENT)
# -------------------------------------------------
class Donor(models.Model):
    patient = models.OneToOneField(
        Patient,
        on_delete=models.CASCADE,
        related_name="donor_profile"
    )

    created_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.patient.emailaddress
