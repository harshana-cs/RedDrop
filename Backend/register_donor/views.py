from urllib import request
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django.contrib.auth import get_user_model, login
from datetime import datetime
from .models import Donor
from django.contrib.auth import login

@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def register_donor(request):
    try:
        data = request.data
        files = request.FILES
        email = data.get("email")

        User = get_user_model()

        dob = data.get("date_of_birth")
        if dob:
            dob = datetime.strptime(dob, "%Y-%m-%d").date()

        weight = data.get("weight")
        if weight:
            weight = int(weight)

        # ✅ Get or create donor
        donor, created = Donor.objects.get_or_create(email=email)

        # ✅ ALWAYS update fields
        donor.first_name = data.get("first_name")
        donor.last_name = data.get("last_name")
        donor.phone_number = data.get("phone_number")
        donor.date_of_birth = dob
        donor.gender = data.get("gender")
        donor.blood_type = data.get("blood_type")

        donor.address = data.get("address")
        donor.city = data.get("city")
        donor.state = data.get("state")
        donor.zip_code = data.get("zip_code")

        donor.emergency_contact_name = data.get("emergency_contact_name")
        donor.emergency_contact_phone = data.get("emergency_contact_phone")

        donor.weight = weight
        donor.has_diabetes = data.get("has_diabetes") == "on"
        donor.has_hypertension = data.get("has_hypertension") == "on"
        donor.has_heart_disease = data.get("has_heart_disease") == "on"
        donor.no_medical_conditions = data.get("no_medical_conditions") == "on"

        donor.accepted_terms = data.get("accepted_terms") == "on"
        donor.consent_notifications = data.get("consent_notifications") == "on"

        # ✅ FILES (only overwrite if uploaded)
        if "citizenship_id" in files:
            donor.citizenship_id = files.get("citizenship_id")

        if "photo" in files:
            donor.photo = files.get("photo")

        donor.is_profile_completed = True
        donor.is_approved = False  # ✅ Set to False, waiting for admin approval
        donor.save()

        # 🔐 Login user (session-based)
        user, _ = User.objects.get_or_create(
            email=email,
            defaults={"username": email}
        )
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')

        return Response({
            "success": True,
            "message": "Donor registered successfully"
        }, status=201)

    except Exception as e:
        return Response({
            "success": False,
            "message": str(e)
        }, status=500)


# ✅ UPDATED: Changed to POST and AllowAny
@api_view(["POST"])
@permission_classes([AllowAny])
def check_donor_approval(request):
    email = request.data.get("email")
    
    if not email:
        return Response({
            "approved": False,
            "already_approved": False,
            "error": "Email required"
        })
    
    try:
        donor = Donor.objects.get(email=email)
        
        return Response({
            "approved": donor.is_approved,
            "already_approved": donor.is_approved
        })
    except Donor.DoesNotExist:
        return Response({
            "approved": False,
            "already_approved": False,
            "error": "Donor not found"
        })