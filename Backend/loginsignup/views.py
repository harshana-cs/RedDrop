import json
import random
import string
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from google.oauth2 import id_token
from google.auth.transport import requests
from .models import GoogleSignup, Patient, Donor
from register_donor.models import Donor
from django.core.mail import send_mail
from django.contrib.auth.hashers import make_password, check_password
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import User
from django.utils.crypto import get_random_string



GOOGLE_CLIENT_ID = "320231613519-n8ppnf9bof8r6js60el89rar1mvtl8lo.apps.googleusercontent.com"

# -----------------------------
# Utilities
# -----------------------------
def generate_code():
    return ''.join(random.choices(string.digits, k=6))

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }

def is_donor_profile_complete(donor):
    required_fields = [
        donor.first_name,
        donor.last_name,
        donor.phone_number,
        donor.date_of_birth,
        donor.gender,
        donor.blood_type,
        donor.address,
        donor.city,
        donor.state,
        donor.zip_code,
        donor.emergency_contact_name,
        donor.emergency_contact_phone,
        donor.weight,
        donor.accepted_terms,
    ]
    return all(required_fields)

# -----------------------------
# GOOGLE SIGNUP
# -----------------------------
@csrf_exempt
def google_signup(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request method"})

    data = json.loads(request.body)
    token = data.get("credential")
    user_type = data.get("user_type", "patient")

    try:
        idinfo = id_token.verify_oauth2_token(token, requests.Request(), GOOGLE_CLIENT_ID)
        email = idinfo["email"]
        fullname = idinfo.get("name", "")

        code = generate_code()

        user, created = GoogleSignup.objects.get_or_create(
            email=email,
            defaults={
                "fullname": fullname,
                "user_type": user_type,
                "verification_code": code,
                "is_verified": False
            }
        )

        if not created:
            user.verification_code = code
            user.is_verified = False
            user.save()

        send_mail(
            subject="RedDrop Verification Code",
            message=f"Your verification code is: {code}",
            from_email="harshanabhandari2@gmail.com",
            recipient_list=[email],
            fail_silently=False
        )

        return JsonResponse({"success": True, "email": email})

    except Exception as e:
        print("Google signup error:", e)
        return JsonResponse({"success": False, "message": "Invalid Google token"})

# -----------------------------
# GOOGLE LOGIN
# -----------------------------
@csrf_exempt
def google_login(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid method"})

    try:
        body = json.loads(request.body)
        credential = body.get("credential")

        idinfo = id_token.verify_oauth2_token(credential, requests.Request(), GOOGLE_CLIENT_ID)
        email = idinfo.get("email")
        fullname = idinfo.get("name")

        google_user = GoogleSignup.objects.get(email=email, is_verified=True)
        user_type = google_user.user_type

        tokens = RefreshToken.for_user(User.objects.get(username=email))

        # ================= PATIENT =================
        if user_type == "patient":
            patient, _ = Patient.objects.get_or_create(
                emailaddress=email,
                defaults={"fullname": fullname}
            )
            return JsonResponse({
                "success": True,
                "user_type": "patient",
                "fullname": patient.fullname,
                "emailaddress": patient.emailaddress,
                "tokens": {
                    "access": str(tokens.access_token),
                    "refresh": str(tokens),
                }
            })

        # ================= DONOR =================
        if user_type == "donor":
            donor, created = Donor.objects.get_or_create(
                email=email.lower(),
                defaults={
                    "first_name": fullname.split(" ", 1)[0],
                    "last_name": fullname.split(" ", 1)[1] if len(fullname.split(" ", 1)) > 1 else "",
                }
            )

            profile_complete = donor.is_profile_completed
            redirect_url = "donor.html" if profile_complete else "donor_register.html"


            return JsonResponse({
                "success": True,
                "user_type": "donor",
                "profile_complete": profile_complete,
                "redirect": redirect_url,
                "email": donor.email,
                "fullname": f"{donor.first_name} {donor.last_name}".strip(),
                "tokens": {
                    "access": str(tokens.access_token),
                    "refresh": str(tokens),
                }
            })

        return JsonResponse({"success": False, "message": "Invalid user type"})

    except GoogleSignup.DoesNotExist:
        return JsonResponse({"success": False, "message": "Account not registered"})
    except Exception as e:
        print("Google login error:", e)
        return JsonResponse({"success": False, "message": "Login failed"})

# -----------------------------
# VERIFY GOOGLE CODE
# -----------------------------
@csrf_exempt
def verify_code(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request method"}, status=405)

    data = json.loads(request.body)
    email = data.get("email")
    code = data.get("code")

    google_user = GoogleSignup.objects.filter(email=email, verification_code=code).first()
    if not google_user:
        return JsonResponse({"success": False, "message": "Invalid code"}, status=400)

    google_user.is_verified = True
    google_user.save()

    # Create Patient if user_type is patient
    Patient.objects.get_or_create(
        emailaddress=email,
        defaults={
            "fullname": google_user.fullname,
            "password": None,
            "confirm_password": None,
            "phonenumber": None
        }
    )

    # Create Django User for JWT
    user, created = User.objects.get_or_create(
        username=email,
        defaults={"email": email}
    )
    if created:
        random_password = get_random_string(12)
        user.set_password(random_password)
        user.save()

    # Create Donor minimal info if user_type is donor
    if google_user.user_type == "donor":
        name_parts = google_user.fullname.strip().split(" ", 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ""
        Donor.objects.get_or_create(
            email=email,
            defaults={
                "first_name": first_name,
                "last_name": last_name,
            }
        )

    return JsonResponse({"success": True})

# -----------------------------
# MANUAL SIGNUP
# -----------------------------
@csrf_exempt
def patient_signup_manually(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request"}, status=400)

    data = json.loads(request.body)
    fullname = data.get("fullname")
    email = data.get("emailaddress")
    phonenumber = data.get("phonenumber")
    password = data.get("password")
    confirmpassword = data.get("confirmpassword")

    if password != confirmpassword:
        return JsonResponse({"success": False, "message": "Passwords do not match"})

    if Patient.objects.filter(emailaddress=email).exists():
        return JsonResponse({"success": False, "message": "Email already registered"})

    if GoogleSignup.objects.filter(email=email).exists():
        return JsonResponse({"success": False, "message": "Email already used for Google Signup"})

    patient = Patient(
        fullname=fullname,
        emailaddress=email,
        phonenumber=phonenumber
    )
    patient.password = make_password(password)
    patient.confirm_password = make_password(confirmpassword)
    patient.save()

    User.objects.get_or_create(
        username=email,
        defaults={"email": email, "password": patient.password}
    )

    return JsonResponse({"success": True, "message": "Account created successfully!"})

# -----------------------------
# MANUAL LOGIN
# -----------------------------
@csrf_exempt
def patient_login(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request method"})

    data = json.loads(request.body)
    email = data.get("emailaddress")
    password = data.get("password")

    if not email or not password:
        return JsonResponse({"success": False, "message": "Email and password are required"})

    try:
        patient = Patient.objects.get(emailaddress=email)
        if not check_password(password, patient.password):
            return JsonResponse({"success": False, "message": "Incorrect password"})

        django_user, created = User.objects.get_or_create(
            username=email,
            defaults={"email": email}
        )
        if created:
            django_user.set_password(password)
            django_user.save()

        tokens = get_tokens_for_user(django_user)

        return JsonResponse({
            "success": True,
            "fullname": patient.fullname,
            "emailaddress": patient.emailaddress,
            "tokens": tokens
        })
    except Patient.DoesNotExist:
        return JsonResponse({"success": False, "message": "No account found with this email"})

# -----------------------------
# GET / UPDATE PATIENT PROFILE
# -----------------------------
@api_view(['GET'])
@permission_classes([AllowAny])
def get_patient_profile(request):
    email = request.GET.get('email')
    if not email:
        return Response({"success": False, "message": "Email parameter missing"})

    patient = Patient.objects.filter(emailaddress__iexact=email.strip()).first()
    if not patient:
        return Response({"success": False, "message": "Patient not found."})

    data = {
        "fullname": patient.fullname,
        "emailaddress": patient.emailaddress,
        "phonenumber": patient.phonenumber,
        "date_of_birth": patient.date_of_birth.strftime("%Y-%m-%d") if patient.date_of_birth else "",
        "gender": patient.gender,
        "blood_type": patient.blood_type,
        "street_address": patient.street_address,
        "city": patient.city,
        "state": patient.state,
        "zip_code": patient.zip_code,
        "weight": patient.weight,
        "height": patient.height,
        "allergies": patient.allergies,
        "medical_conditions": patient.medical_conditions,
        "emergency_name": patient.emergency_name,
        "emergency_relationship": patient.emergency_relationship,
        "emergency_phone": patient.emergency_phone,
        "emergency_email": patient.emergency_email
    }
    return Response({"success": True, "data": data})

@api_view(['POST'])
@permission_classes([AllowAny])
def update_patient_profile(request):
    email = request.data.get('emailaddress')
    try:
        patient = Patient.objects.get(emailaddress=email)
        fields = [
            "fullname", "phonenumber", "date_of_birth", "gender", "blood_type",
            "street_address", "city", "state", "zip_code",
            "weight", "height", "allergies", "medical_conditions",
            "emergency_name", "emergency_relationship", "emergency_phone", "emergency_email"
        ]
        for field in fields:
            if field in request.data:
                value = request.data[field]
                if field == "date_of_birth" and value:
                    from datetime import datetime
                    try:
                        value = datetime.strptime(value, "%Y-%m-%d").date()
                    except ValueError:
                        return Response({"success": False, "message": "Invalid date format. Use YYYY-MM-DD"})
                setattr(patient, field, value)
        patient.save()
        return Response({"success": True, "message": "Profile updated successfully."})
    except Patient.DoesNotExist:
        return Response({"success": False, "message": "Patient not found."})

# -----------------------------
# UPDATE DONOR PROFILE
# -----------------------------
@api_view(['POST'])
@permission_classes([AllowAny])
def update_donor_profile(request):
    email = request.data.get('email')
    try:
        donor = Donor.objects.get(email=email)
        fields = [
            "first_name", "last_name", "phone_number", "date_of_birth", "gender",
            "blood_type", "address", "city", "state", "zip_code",
            "emergency_contact_name", "emergency_contact_phone",
            "weight", "has_diabetes", "has_hypertension", "has_heart_disease",
            "no_medical_conditions", "accepted_terms", "consent_notifications"
        ]
        for field in fields:
            if field in request.data:
                setattr(donor, field, request.data[field])
        donor.save()
        return Response({"success": True, "message": "Donor profile updated successfully."})
    except Donor.DoesNotExist:
        return Response({"success": False, "message": "Donor not found."})
