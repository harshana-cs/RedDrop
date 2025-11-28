from django.db import models

class GoogleSignup(models.Model):

    USER_TYPES = [
        ("patient", "Patient"),
        ("doctor", "Doctor"),
        ("donor", "Donor"),
        ("admin", "Admin"),
    ]

    fullname = models.CharField(max_length=150)  # Added fullname field
    email = models.EmailField(unique=True)
    credential = models.TextField()
    verification_code = models.CharField(max_length=6)
    is_verified = models.BooleanField(default=False)
    user_type = models.CharField(max_length=20, choices=USER_TYPES, default="patient")
    created_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email
class Patient(models.Model):
    fullname = models.CharField(max_length=100)
    emailaddress = models.EmailField(unique=True)
    phonenumber = models.CharField(max_length=20)
    # address = models.CharField(max_length=255)
    password = models.CharField(max_length=255)
    confirm_password = models.CharField(max_length=255)

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password)