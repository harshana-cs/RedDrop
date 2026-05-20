from pathlib import Path
import os
from corsheaders.defaults import default_headers
from celery.schedules import crontab

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']

# Application definition
INSTALLED_APPS = [
    # Default Django apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party apps
    'rest_framework',
    'rest_framework.authtoken',
    'dj_rest_auth',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'dj_rest_auth.registration',
    

    # Your custom apps
    'loginsignup',
    'corsheaders',
    'blood_requests',
    'register_donor',
    'adminpanel',
    'donor',
    'hospital',
    'blood_stock',

    
]

MIDDLEWARE = [
     'corsheaders.middleware.CorsMiddleware',   
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'allauth.account.middleware.AccountMiddleware',  
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'backend_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],   # 👈 only once
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]


WSGI_APPLICATION = 'backend_project.wsgi.application'


# =====================
# DATABASE (PostgreSQL)
# =====================
DATABASES = {
    "default": {
        'ENGINE': 'django.db.backends.postgresql',
        "NAME": "postgres",
        "USER": "postgres.doxlbyqfjigwwdwwosto",
        "PASSWORD": "Harshana.123",
        "HOST": "aws-1-ap-northeast-2.pooler.supabase.com",
        "PORT": "6543",
        "OPTIONS": {
            "sslmode": "require",
        },
        "CONN_MAX_AGE": 60,
    }
}



# =====================
# REST FRAMEWORK CONFIG
# =====================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        # 'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}


# =====================
# AUTHENTICATION CONFIG
# =====================
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

SITE_ID = 1

# =====================
# SOCIAL AUTH (Google)
# =====================
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
    }
}

# =====================
# EMAIL (For Dev Only)
# =====================
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# =====================
# PASSWORD VALIDATION
# =====================
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# =====================
# LANGUAGE & TIMEZONE
# =====================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kathmandu'
USE_I18N = True
USE_TZ = True

# =====================
# STATIC & MEDIA FILES
# =====================
STATIC_URL = '/static/'

# settings.py
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Create subdirectory for certificates
CERTIFICATE_STORAGE_PATH = os.path.join(MEDIA_ROOT, 'certificates')


# =====================
# DEFAULT AUTO FIELD
# =====================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
SECRET_KEY = '@w@3^rb^nags)z83aizm830i!_c(%4i+8bd14pfw9k259ah+(j'

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = False

CORS_ALLOW_HEADERS = list(default_headers) + [
    "authorization",
]

CORS_ALLOW_METHODS = [
    "GET",
    "POST",
    "PUT",
    "DELETE",
    "OPTIONS",
    "PATCH",
]
# Allow credentials (cookies)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://localhost:5501",
    "http://127.0.0.1:5501",
    
]

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'rdrop7214@gmail.com'
EMAIL_HOST_PASSWORD = 'knpg pwzb vzji aqkc' 
LOGIN_REDIRECT_URL = '/login-success/'
from dotenv import load_dotenv
import os
load_dotenv(BASE_DIR / ".env")

ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY")

# Sparrow SMS
SMS_TOKEN = os.getenv("SMS_TOKEN")
SMS_FROM = os.getenv("SMS_FROM", "Demo")
# =======================================================================
# LOCATION 7: settings.py — ADD THIS ENTIRE BLOCK at the bottom
# =======================================================================

# ================= CELERY CONFIGURATION =================
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Kathmandu'
CELERY_ENABLE_UTC = True

# Task time limits
CELERY_TASK_TIME_LIMIT = 30 * 60      # 30 minutes hard limit
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25 minutes soft limit

# For development/testing — run tasks synchronously without Redis/Celery:
# CELERY_ALWAYS_EAGER = True
# CELERY_EAGER_PROPAGATES_EXCEPTIONS = True

# ================= BLOOD BANK CONFIG =================
BLOOD_BANK_CONTACT = "+977-1-4428888"
BLOOD_BANK_EMAIL = "bloodbank@hospital.com"

# ================= LOGGING =================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'adminpanel': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'celery': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'celery_tasks': {
            'handlers': ['console'],
            'level': 'INFO',
        },
    },
}

# Daily donor eligibility reminder (5 days before next_donation_date)
CELERY_BEAT_SCHEDULE = {
    'send-donation-eligibility-reminders-daily': {
        'task': 'donor.tasks.send_donation_eligibility_reminders',
        'schedule': crontab(hour=9, minute=0),  # 9:00 AM Asia/Kathmandu
    },
}
# settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',  # hides broken pipe (it's a WARNING level)
            'propagate': False,
        },
    },
}
