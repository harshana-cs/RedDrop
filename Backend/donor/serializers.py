from rest_framework import serializers
from .models import Donor, Donation
from adminpanel.models import DonationCamp


class DonorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Donor
        fields = "__all__"

class DonorProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Donor
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "date_of_birth",
            "gender",
            "blood_type",
            "address",
            "city",
            "state",
            "zip_code",
            "weight",
            "is_approved",
            "created_on",
            
        ]
class DonationSerializer(serializers.ModelSerializer):
    donation_date = serializers.DateField(source="date", read_only=True)

    class Meta:
        model = Donation
        fields = [
            "id",
            "blood_type",
            "donation_date",
            "hospital",
            "status",
        ]

class DonationCampSerializer(serializers.ModelSerializer):
    class Meta:
        model = DonationCamp
        fields = "__all__"
