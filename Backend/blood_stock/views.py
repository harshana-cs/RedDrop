from hospital.models import Hospital
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import BloodStock, BloodStockHistory
from hospital.auth import get_hospital_from_token
from django.db import transaction
from rest_framework.decorators import authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from adminpanel.models import HospitalAuditLog   # ✅ ADD


# ================= BLOOD STOCK =================
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def hospital_blood_stock(request):

    hospital = get_hospital_from_token(request)

    if not hospital:
        return Response({"detail": "Unauthorized"}, status=401)

    BLOOD_TYPES = ["A+","A-","B+","B-","AB+","AB-","O+","O-"]

    data = []

    for bt in BLOOD_TYPES:

        stock = BloodStock.objects.filter(
            hospital=hospital,
            blood_type=bt
        ).first()

        data.append({
            "blood_type": bt,
            "units": stock.units if stock else 0,
            "minimum_required": stock.minimum_required if stock else 10,
            "last_updated": stock.last_updated if stock else None,
        })

    return Response(data, status=200)


# ================= ADD STOCK =================
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def add_blood_stock(request):

    hospital = get_hospital_from_token(request)

    if not hospital:
        return Response({"detail": "Unauthorized"}, status=401)

    blood_type = request.data.get("blood_type")
    units = int(request.data.get("units", 0))
    source = request.data.get("source")

    if not blood_type or units <= 0:
        return Response({"error": "Invalid input"}, status=400)

    with transaction.atomic():

        stock, _ = BloodStock.objects.get_or_create(
            hospital=hospital,
            blood_type=blood_type,
            defaults={"units": 0}
        )

        stock.units += units
        stock.save()

        # create stock history
        BloodStockHistory.objects.create(
            hospital=hospital,
            blood_type=blood_type,
            transaction_type="add",
            units=units,
            source=source,
            performed_by="Hospital",
            new_balance=stock.units
        )

        # 🔴 CREATE AUDIT LOG
        HospitalAuditLog.objects.create(
            hospital=hospital,
            action="stock_add",
            description=f"{hospital.name} added {units} units of {blood_type}",
            metadata={
                "blood_type": blood_type,
                "units": units,
                "source": source
            }
        )

    return Response({"success": True}, status=200)


# ================= REMOVE STOCK =================
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def remove_blood_stock(request):

    hospital = get_hospital_from_token(request)

    if not hospital:
        return Response({"detail": "Unauthorized"}, status=401)

    blood_type = request.data.get("blood_type")
    units = int(request.data.get("units", 0))
    reason = request.data.get("reason")

    with transaction.atomic():

        try:
            stock = BloodStock.objects.select_for_update().get(
                hospital=hospital,
                blood_type=blood_type
            )

        except BloodStock.DoesNotExist:
            return Response({"error": "Stock not found"}, status=404)

        if units <= 0 or units > stock.units:
            return Response({"error": "Insufficient stock"}, status=400)

        stock.units -= units
        stock.save()

        # create stock history
        BloodStockHistory.objects.create(
            hospital=hospital,
            blood_type=blood_type,
            transaction_type="remove",
            units=units,
            reason=reason,
            performed_by="Hospital",
            new_balance=stock.units
        )

        # 🔴 CREATE AUDIT LOG
        HospitalAuditLog.objects.create(
            hospital=hospital,
            action="stock_remove",
            description=f"{hospital.name} removed {units} units of {blood_type}",
            metadata={
                "blood_type": blood_type,
                "units": units,
                "reason": reason
            }
        )

    return Response({"success": True}, status=200)


# ================= STOCK HISTORY =================
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def stock_history(request):

    hospital = get_hospital_from_token(request)

    if not hospital:
        return Response({"detail": "Unauthorized"}, status=401)

    history = BloodStockHistory.objects.filter(
        hospital=hospital
    ).order_by("-timestamp")

    data = []

    for h in history:

        data.append({
            "blood_type": h.blood_type,
            "transaction_type": h.transaction_type,
            "units": h.units,
            "source": h.source,
            "reason": h.reason,
            "performed_by": h.performed_by,
            "new_balance": h.new_balance,
            "timestamp": h.timestamp,
        })

    return Response(data, status=200)

@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def blood_bank_stock(request):

    hospital = get_hospital_from_token(request)

    if not hospital:
        return Response({"detail": "Unauthorized"}, status=401)

    stocks = BloodStock.objects.filter(hospital__isnull=True)

    data = [
        {
            "blood_type": s.blood_type,
            "units": s.units,
            "minimum_required": s.minimum_required,
            "last_updated": s.last_updated
        }
        for s in stocks
    ]

    return Response(data)