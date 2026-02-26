from django.db import models
from django.contrib.auth.hashers import make_password, check_password

class Hospital(models.Model):
    name = models.CharField(max_length=255)
    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=255)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    def __str__(self):
        return self.name

class HospitalProfile(models.Model):
    hospital = models.OneToOneField(
        Hospital,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    district = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    contact_number = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True, null=True)  # MUST BE NULLABLE

    registration_number = models.CharField(max_length=100, blank=True)
    hospital_type = models.CharField(max_length=50, blank=True)
    bed_capacity = models.PositiveIntegerField(null=True, blank=True)
    blood_bank_type = models.CharField(max_length=50, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)


class HospitalApplication(models.Model):

    # ---------- CHOICES ----------
    HOSPITAL_TYPE_CHOICES = [
        ("government", "Government"),
        ("private", "Private"),
        ("teaching", "Teaching"),
        ("community", "Community"),
        ("specialty", "Specialty"),
        ("clinic", "Clinic"),
    ]

    BLOOD_BANK_TYPE_CHOICES = [
        ("storage_only", "Storage Only"),
        ("collection_storage", "Collection & Storage"),
        ("full_service", "Full Service Blood Bank"),
        ("none", "No Blood Bank Facility"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    # ---------- HOSPITAL INFO ----------
    hospital_name = models.CharField(max_length=255)
    registration_number = models.CharField(max_length=100, unique=True)
    hospital_type = models.CharField(
        max_length=20, choices=HOSPITAL_TYPE_CHOICES, null=True, blank=True
    )
    bed_capacity = models.PositiveIntegerField(null=True, blank=True)
    year_established = models.PositiveIntegerField(null=True, blank=True)
    blood_bank_type = models.CharField(
        max_length=30,
        choices=BLOOD_BANK_TYPE_CHOICES,
        blank=True
    )

    # ---------- CONTACT INFO ----------
    contact_person = models.CharField(max_length=255)
    designation = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.TextField()
    website = models.URLField(blank=True, null=True)

    # ---------- MEDICAL FACILITIES ----------
    has_emergency = models.BooleanField(default=False)
    has_icu = models.BooleanField(default=False)
    has_operation_theater = models.BooleanField(default=False)
    has_blood_storage = models.BooleanField(default=False)
    has_blood_testing = models.BooleanField(default=False)
    hosts_donation_camp = models.BooleanField(default=False)

    # ---------- DOCUMENTS ----------
    registration_certificate = models.FileField(
        upload_to="hospital_docs/registration/"
    )
    medical_license = models.FileField(
        upload_to="hospital_docs/medical_license/"
    )
    blood_bank_license = models.FileField(
        upload_to="hospital_docs/blood_bank/",
        null=True,
        blank=True
    )
    id_proof = models.FileField(
        upload_to="hospital_docs/id_proof/"
    )
    authority_letter = models.FileField(
        upload_to="hospital_docs/authority_letter/",
        null=True,
        blank=True
    )

    # ---------- ADMIN ----------
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )
    admin_remark = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.hospital_name} ({self.status})"


