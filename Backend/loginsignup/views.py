import json
import random
import string
from django.utils import timezone 
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from google.oauth2 import id_token
from google.auth.transport import requests
from .models import GoogleSignup
from blood_requests.models import Patient
from register_donor.models import Donor
from django.core.mail import send_mail
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.models import User
from django.utils.crypto import get_random_string
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from blood_requests.models import BloodRequest
from donor.models import Donation

GOOGLE_CLIENT_ID = "320231613519-n8ppnf9bof8r6js60el89rar1mvtl8lo.apps.googleusercontent.com"


def generate_code():
    return ''.join(random.choices(string.digits, k=6))


def get_tokens(user):
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


@csrf_exempt
def google_signup(request):
    if request.method != "POST":
        return JsonResponse({"success": False})

    data = json.loads(request.body)
    token = data.get("credential")

    try:
        idinfo = id_token.verify_oauth2_token(token, requests.Request(), GOOGLE_CLIENT_ID)
        email = idinfo["email"]
        fullname = idinfo.get("name", "")

        code = generate_code()

        GoogleSignup.objects.update_or_create(
            email=email,
            defaults={
                "fullname": fullname,
                "verification_code": code,
                "is_verified": False
            }
        )

        send_mail(
            "RedDrop Verification Code",
            f"Your verification code is: {code}",
            "noreply@reddrop.com",
            [email],
        )

        return JsonResponse({"success": True, "email": email})

    except Exception:
        return JsonResponse({"success": False, "message": "Invalid Google token"})


@csrf_exempt
def verify_code(request):
    if request.method != "POST":
        return JsonResponse({"success": False})

    data = json.loads(request.body)
    email = data.get("email")
    code  = data.get("code")

    google_user = GoogleSignup.objects.filter(
        email=email, verification_code=code
    ).first()

    if not google_user:
        return JsonResponse({"success": False, "message": "Invalid or expired code"})

    google_user.is_verified = True
    google_user.save()

    # ── Create or get Patient account ────────────────────────
    patient, _ = Patient.objects.get_or_create(
        emailaddress=email,
        defaults={"fullname": google_user.fullname}
    )

    if not patient.is_active:
        return JsonResponse({
            "success": False,
            "message": "Your account has been deactivated by admin"
        })

    # ── FIX: Save password to Patient model ──────────────────
    if google_user.pending_password:
        patient.password = google_user.pending_password
        patient.save()

    # ── Create Django User ───────────────────────────────────
    user, created = User.objects.get_or_create(
        username=email,
        defaults={"email": email}
    )

    if created:
        if google_user.pending_password:
            # Manual signup — use the stored hashed password
            user.password = google_user.pending_password
        else:
            # Google signup — random password
            user.set_password(get_random_string(12))
        user.save()

    # ── Clear pending password ───────────────────────────────
    if google_user.pending_password:
        google_user.pending_password = None
        google_user.save()

    # ── Generate JWT ─────────────────────────────────────────
    refresh = RefreshToken.for_user(user)

    return JsonResponse({
        "success": True,
        "fullname": patient.fullname,
        "email":    patient.emailaddress,
        "tokens": {
            "access":  str(refresh.access_token),
            "refresh": str(refresh),
        }
    })


@csrf_exempt
def google_login(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid method"})

    try:
        body = json.loads(request.body)
        credential = body.get("credential")

        idinfo = id_token.verify_oauth2_token(
            credential,
            requests.Request(),
            GOOGLE_CLIENT_ID
        )

        email = idinfo["email"].strip().lower()
        fullname = idinfo.get("name", "")

        # 1️⃣ Must exist & verified
        google_user = GoogleSignup.objects.filter(
            email__iexact=email,
            is_verified=True
        ).first()

        if not google_user:
            return JsonResponse({
                "success": False,
                "message": "Google account not verified"
            })

        # 2️⃣ Ensure Patient exists
        patient, _ = Patient.objects.get_or_create(
            emailaddress=email,
            defaults={"fullname": fullname}
        )
        if not patient.is_active:
            return JsonResponse({
                "success": False,
                "message": "Your account has been deactivated by admin"
            })

        # 3️⃣ Ensure Django auth user exists
        user, created = User.objects.get_or_create(
            username=email,
            defaults={"email": email}
        )

        if created or not user.has_usable_password():
            user.set_password(get_random_string(12))
            user.save()

        # 4️⃣ Generate JWT tokens
        refresh = RefreshToken.for_user(user)

        return JsonResponse({
            "success": True,
            "fullname": patient.fullname,
            "email": patient.emailaddress,
            "tokens": {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            }
        })

    except Exception as e:
        print("GOOGLE LOGIN ERROR:", e)
        return JsonResponse({
            "success": False,
            "message": "Login failed"
        })


@csrf_exempt
def patient_signup_manually(request):
    if request.method != "POST":
        return JsonResponse({"success": False})

    data = json.loads(request.body)

    if data["password"] != data["confirmpassword"]:
        return JsonResponse({"success": False, "message": "Passwords do not match"})

    if Patient.objects.filter(emailaddress=data["emailaddress"]).exists():
        return JsonResponse({"success": False, "message": "Email already exists"})

    code = ''.join(random.choices(string.digits, k=6))

    from django.contrib.auth.hashers import make_password as hash_pw
    GoogleSignup.objects.update_or_create(
        email=data["emailaddress"],
        defaults={
            "fullname":          data["fullname"],
            "verification_code": code,
            "is_verified":       False,
            "pending_password":  hash_pw(data["password"]),
        }
    )

    try:
        send_mail(
            "RedDrop — Verify Your Email",
            f"Hi {data['fullname']},\n\nYour RedDrop verification code is:\n\n{code}\n\nDo not share this code with anyone.\n\n— RedDrop Team",
            "noreply@reddrop.com",
            [data["emailaddress"]],
        )
    except Exception as e:
        print("Email error:", e)

    return JsonResponse({
        "success": True,
        "verify": True,
        "email": data["emailaddress"],
        "message": "Verification code sent to your email"
    })


@csrf_exempt
def patient_login(request):
    if request.method != "POST":
        return JsonResponse({"success": False})

    data = json.loads(request.body)

    try:
        patient = Patient.objects.get(emailaddress=data["emailaddress"])

        if not patient.is_active:
            return JsonResponse({
                "success": False,
                "message": "Your account has been deactivated by admin"
            })

        # ── FIX: Guard against None password (e.g. Google-only accounts) ──
        if not patient.password:
            return JsonResponse({
                "success": False,
                "message": "No password set for this account. Please use Google login or reset your password."
            })

        if not patient.check_password(data["password"]):
            return JsonResponse({"success": False, "message": "Wrong password"})

        user = User.objects.get(username=patient.emailaddress)
        tokens = get_tokens(user)

        return JsonResponse({
            "success": True,
            "emailaddress": patient.emailaddress,
            "fullname": patient.fullname,
            "is_donor": Donor.objects.filter(email=patient.emailaddress).exists(),
            "tokens": tokens
        })

    except Patient.DoesNotExist:
        return JsonResponse({"success": False, "message": "Account not found"})

    except User.DoesNotExist:
        return JsonResponse({"success": False, "message": "Auth account missing. Please re-register."})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_user_capabilities(request):
    email = request.user.email or request.user.username

    # ---------------- USER OBJECTS ----------------
    patient = Patient.objects.filter(emailaddress=email).first()
    donor = Donor.objects.filter(email=email).first()

    # ---------------- REQUESTS ----------------
    requests_qs = (
        BloodRequest.objects.filter(patient=patient)
        if patient else BloodRequest.objects.none()
    )

    # ---------------- DONATIONS ----------------
    donations_qs = (
        Donation.objects.filter(donor=donor)
        if donor else Donation.objects.none()
    )

    last_donation = donations_qs.order_by("-date").first()

    # ---------------- DAYS SINCE LAST DONATION ----------------
    days_since_last = None
    if last_donation and last_donation.date:
        days_since_last = (
            timezone.now().date() - last_donation.date
        ).days

    # ---------------- BLOOD TYPE ----------------
    blood_type = ""

    if donor and donor.blood_type:
        blood_type = donor.blood_type
    elif patient:
        latest_request = (
            BloodRequest.objects
            .filter(patient=patient)
            .order_by("-created_at")
            .first()
        )
        if latest_request:
            blood_type = latest_request.blood_type

    # ---------------- MEMBER SINCE ----------------
    member_since = None
    if patient and hasattr(patient, "created_at"):
        member_since = patient.created_at

    # ---------------- RESPONSE ----------------
    return Response({
        "name": patient.fullname if patient else "",
        "email": email,
        "blood_type": blood_type,
        "patient_id": patient.id if patient else None,
        "member_since": member_since,

        "is_patient": bool(patient),
        "is_donor": bool(donor),
        "donor_rejected": bool(donor and donor.rejected_at and not donor.is_approved),
        "donor_rejection_reason": donor.rejection_reason if donor else "",
        "donor_rejected_at": donor.rejected_at.isoformat() if donor and donor.rejected_at else None,

        "requests": {
            "total": requests_qs.count(),
            "completed": requests_qs.filter(status="completed").count(),
            "pending": requests_qs.filter(status="pending").count(),
        },

        "donations": {
            "total": donations_qs.count(),
            "last_date": last_donation.date if last_donation else None,
            "days_since_last": days_since_last,
        },

        "donor_approved": donor.is_approved if donor else False,
        "donor_available": donor.is_approved if donor else False,
        "donor_score": donations_qs.count() * 10 if donor else 0,
    })


@api_view(["PATCH", "PUT"])
@permission_classes([IsAuthenticated])
def update_profile(request):
    email = request.user.email or request.user.username

    patient = Patient.objects.filter(emailaddress=email).first()
    if not patient:
        return Response({"success": False, "message": "Patient not found"}, status=404)

    data = request.data

    if "name" in data:
        patient.fullname = data["name"]
    if "blood_type" in data:
        patient.blood_type = data.get("blood_type", "")
    if "phone" in data:
        patient.phone = data.get("phone", "")
    if "district" in data:
        patient.district = data.get("district", "")
    if "address" in data:
        patient.address = data.get("address", "")

    patient.save()

    # Also update donor profile if exists
    donor = Donor.objects.filter(email=email).first()
    if donor:
        if "blood_type" in data:
            donor.blood_type = data["blood_type"]
        if "phone" in data:
            donor.phone = data["phone"]
        if "district" in data:
            donor.district = data["district"]
        donor.save()

    return Response({
        "success": True,
        "message": "Profile updated successfully",
        "name": patient.fullname,
        "blood_type": getattr(patient, "blood_type", ""),
    })
