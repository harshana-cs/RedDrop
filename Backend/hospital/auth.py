import jwt
from django.conf import settings
from .models import Hospital

def get_hospital_from_token(request):
    # 🔥 MOST IMPORTANT LINE
    auth_header = request.META.get("HTTP_AUTHORIZATION")

    if not auth_header:
        print("❌ No Authorization header found")
        return None

    try:
        prefix, token = auth_header.split(" ")

        if prefix.lower() != "bearer":
            print("❌ Invalid auth prefix:", prefix)
            return None

        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"]
        )

        hospital_id = payload.get("hospital_id")
        print("✅ JWT decoded, hospital_id =", hospital_id)

        return Hospital.objects.filter(
            id=hospital_id,
            is_active=True
        ).first()

    except jwt.ExpiredSignatureError:
        print("❌ Token expired")
        return None
    except jwt.InvalidTokenError as e:
        print("❌ Invalid token:", str(e))
        return None
    except Exception as e:
        print("❌ Unexpected error:", str(e))
        return None
