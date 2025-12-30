from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import Donor
from datetime import datetime

@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def register_donor(request):
    try:
        data = request.data
        files = request.FILES

        email = data.get("email")

        # If donor already exists → do not register again
        existing = Donor.objects.filter(email=email).first()
        if existing:
            existing.is_profile_completed = True
            existing.save()

            return Response({
                "success": True,
                "message": "Donor already registered"
            }, status=200)

        # convert date + weight
        dob = data.get("date_of_birth")
        if dob:
            dob = datetime.strptime(dob, "%Y-%m-%d").date()

        weight = data.get("weight")
        if weight:
            weight = int(weight)

        donor = Donor(
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            email=email,
            phone_number=data.get("phone_number"),
            date_of_birth=dob,
            gender=data.get("gender"),
            blood_type=data.get("blood_type"),

            address=data.get("address"),
            city=data.get("city"),
            state=data.get("state"),
            zip_code=data.get("zip_code"),

            emergency_contact_name=data.get("emergency_contact_name"),
            emergency_contact_phone=data.get("emergency_contact_phone"),

            weight=weight,

            has_diabetes=data.get("has_diabetes") == "on",
            has_hypertension=data.get("has_hypertension") == "on",
            has_heart_disease=data.get("has_heart_disease") == "on",
            no_medical_conditions=data.get("no_medical_conditions") == "on",

            citizenship_id=files.get("citizenship_id"),
            photo=files.get("photo"),

            accepted_terms=data.get("accepted_terms") == "on",
            consent_notifications=data.get("consent_notifications") == "on",
        )

        donor.is_profile_completed = True
        donor.save()

        return Response({
            "success": True,
            "message": "Donor registered successfully"
        }, status=201)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({
            "success": False,
            "message": str(e)
        }, status=500)
from django.shortcuts import redirect
from .models import Donor   # ensure this exists

def login_success(request):
    user = request.user
    donor = Donor.objects.filter(email=user.email).first()

    if donor and donor.is_profile_completed:
        return redirect("/donor.html")          # Already completed profile
    else:
        return redirect("/donor/register-page/")  # Needs registration
