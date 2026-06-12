import os

from django.conf import settings
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .chatbot_kb import answer_from_excel


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def chatbot_ask(request):
    question = (request.data.get("question") or "").strip()
    if not question:
        return Response({"ok": False, "message": "Question is required."}, status=400)

    default_path = os.path.join(settings.BASE_DIR, "chatbot_data", "blood_donation_kb.xlsx")
    kb_path = os.getenv("CHATBOT_KB_PATH", default_path)

    result = answer_from_excel(question, kb_path)
    return Response(result)
