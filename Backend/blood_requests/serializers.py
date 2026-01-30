from rest_framework import serializers
from .models import BloodRequest

class BloodRequestSerializer(serializers.ModelSerializer):
    hospital_doc = serializers.FileField(required=True)
    doctor_note = serializers.FileField(required=True)

    class Meta:
        model = BloodRequest
        fields = [
            "id",
            "blood_type",
            "units_required",
            "urgency",
            "district",
            "hospital",
            "required_date",

            # 🔥 THESE WERE MISSING
            "reason",
            "contact_name",
            "contact_phone",

            # 🔥 FILES
            "hospital_doc",
            "doctor_note",

            # system fields
            "status",
            "created_at",
            "donation_date",
        ]
