from urllib import request
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django.contrib.auth import get_user_model, login
from datetime import datetime
from .models import Donor, TestModel
from django.contrib.auth import login
from blood_requests.models import Patient
from adminpanel.models import Notification
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from common.upload_screening import screen_uploaded_files, notify_suspicious_upload
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def register_donor(request):
    try:
        user = request.user
        data = request.data
        files = request.FILES

        screening = screen_uploaded_files(
            {
                "citizenship_id": files.get("citizenship_id"),
                "photo": files.get("photo"),
            },
            upload_type="donor_registration",
        )

        if screening["verdict"] == "BLOCK":
            notify_suspicious_upload(
                title="Blocked Donor Document",
                message=(
                    f"Blocked donor upload for {data.get('first_name', '').strip()} {data.get('last_name', '').strip()} "
                    f"due to suspicious or AI-generated documents. Risk score: {screening['risk_score']}. "
                    f"Flags: {', '.join(screening['flags']) or 'None'}."
                ),
                upload_result=screening,
                metadata={"email": user.email or user.username},
            )
            return Response({
                "success": False,
                "message": "Your uploaded document looks suspicious or AI-generated. Please upload a clear original document.",
                "screening": screening,
            }, status=400)

        email = user.email or user.username

        # ✅ Ensure patient exists
        patient = Patient.objects.filter(emailaddress=email).first()
        if not patient:
            return Response({
                "success": False,
                "message": "Patient profile not found"
            }, status=404)

        # 🚫 Prevent re-registration
        existing = Donor.objects.filter(email=email).first()
        if existing and existing.is_profile_completed:
            return Response({
                "success": False,
                "message": "You have already registered as a donor"
            }, status=400)

        donor, _ = Donor.objects.get_or_create(email=email)

        # ================= BASIC DETAILS =================
        donor.first_name = data.get("first_name")
        donor.last_name = data.get("last_name")
        donor.phone_number = data.get("phone_number")
        donor.gender = data.get("gender")
        donor.blood_type = data.get("blood_type")
        donor.weight = int(data.get("weight")) if data.get("weight") else None

        dob = data.get("date_of_birth")
        if dob:
            donor.date_of_birth = datetime.strptime(dob, "%Y-%m-%d").date()

        # ================= ADDRESS =================
        donor.address = data.get("address")
        donor.city = data.get("city")
        donor.state = data.get("state")
        donor.zip_code = data.get("zip_code")
        
        
       # ================= LOCATION =================
        latitude = data.get("latitude")
        longitude = data.get("longitude")

        if latitude and longitude:
            donor.latitude = float(latitude)
            donor.longitude = float(longitude)
            donor.location_updated_at = timezone.now()

        # ================= EMERGENCY CONTACT =================
        donor.emergency_contact_name = data.get("emergency_contact_name")
        donor.emergency_contact_phone = data.get("emergency_contact_phone")

        # ================= MEDICAL =================
        donor.has_diabetes = data.get("has_diabetes") == "true"
        donor.has_hypertension = data.get("has_hypertension") == "true"
        donor.has_heart_disease = data.get("has_heart_disease") == "true"
        donor.no_medical_conditions = data.get("no_medical_conditions") == "true"

        # ================= CONSENT =================
        donor.accepted_terms = data.get("accepted_terms") == "true"
        donor.consent_notifications = data.get("consent_notifications") == "true"

        # ================= FILES =================
        if "citizenship_id" in files:
            donor.citizenship_id = files["citizenship_id"]

        if "photo" in files:
            donor.photo = files["photo"]

        # ================= FINAL =================
        donor.is_profile_completed = True
        donor.is_approved = False
        donor.save()

        # Create notification for admin
        Notification.objects.create(
            title="New Donor Registration",
            message=f"A new donor has registered: {donor.first_name} {donor.last_name}",
            type="donor_registration",
            is_read=False
        )

        if screening["verdict"] == "REVIEW":
            notify_suspicious_upload(
                title="Suspicious Donor Document",
                message=(
                    f"Donor registration for {donor.first_name} {donor.last_name} needs document review. "
                    f"Risk score: {screening['risk_score']}. Flags: {', '.join(screening['flags']) or 'None'}."
                ),
                upload_result=screening,
                metadata={"email": donor.email},
            )

        return Response({
            "success": True,
            "message": "Donor registered successfully. Await admin approval."
        }, status=201)

    except Exception as e:
        print("REGISTER DONOR ERROR:", e)
        return Response({
            "success": False,
            "message": "Server error"
        }, status=500)
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
    

@api_view(["POST"])
@permission_classes([AllowAny])
@csrf_exempt
def test_api(request):
    full_name = request.data.get("name")
    TestModel.objects.create(name=full_name)
    return Response({ "name": full_name })
