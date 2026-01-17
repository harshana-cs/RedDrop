from rest_framework import serializers
from .models import BloodRequest

class BloodRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = BloodRequest
        fields = [
            "id",
            "blood_type",
            "units_required",
            "urgency",
            "hospital",
            "district",
            "status",
            "created_at",
            "donation_date",   # ✅ THIS WAS MISSING IN RESPONSE
        ]
