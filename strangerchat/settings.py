import os
from pathlib import Path
from django.core.management.utils import get_random_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("SECRET_KEY") or get_random_secret_key()  # no sessions used, safe if it rotates
DEBUG = os.environ.get("DEBUG", "0") == "1"

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",") if h.strip()]
if os.environ.get("RENDER_EXTERNAL_HOSTNAME"):  # Render sets this automatically
    ALLOWED_HOSTS.append(os.environ["RENDER_EXTERNAL_HOSTNAME"])

INSTALLED_APPS = ["daphne", "chat"]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "strangerchat.urls"
ASGI_APPLICATION = "strangerchat.asgi.application"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": []},
}]
DATABASES = {}  # no database needed
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
