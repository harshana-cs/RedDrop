from django.http import JsonResponse
from .models import Patient
from django.views.decorators.csrf import csrf_exempt
import json

@csrf_exempt
def signup(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)

            # Use .get() with default empty string to avoid None
            fullname = data.get('fullname', '').strip()
            email = data.get('emailaddress', '').strip()
            phone = data.get('phonenumber', '').strip()
            address = data.get('address', '').strip()
            password = data.get('password', '').strip()
            confirm_password = data.get('confirm_password', '').strip()

            if not password or not confirm_password:
                return JsonResponse({'error': 'Password fields are required'}, status=400)

            if password != confirm_password:
                return JsonResponse({'error': 'Passwords do not match'}, status=400)

            patient = Patient.objects.create(
                fullname=fullname,
                emailaddress=email,
                phonenumber=phone,
                address=address,
                password=password,
                confirm_password=confirm_password
            )
            return JsonResponse({'message': 'Signup successful', 'id': patient.id}, status=201)

        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)
