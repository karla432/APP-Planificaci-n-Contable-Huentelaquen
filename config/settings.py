"""Configuración de Planificación Contable Huentelauquén.

Mismas convenciones que el Arqueo de Caja: por defecto PRODUCCIÓN; un equipo de desarrollo se declara con
`PLANIFICACION_ENTORNO=desarrollo` o con el archivo local `.entorno_desarrollo` (no versionado).
Ningún secreto vive en el repositorio (ver `.env.example`).
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key

from config.entorno import resolver_entorno

BASE_DIR = Path(__file__).resolve().parent.parent

ENTORNO = resolver_entorno(os.environ.get("PLANIFICACION_ENTORNO"), BASE_DIR)
if ENTORNO not in ("desarrollo", "produccion"):
    raise ImproperlyConfigured("PLANIFICACION_ENTORNO debe ser «desarrollo» o «produccion».")
PRODUCCION = ENTORNO == "produccion"


def _lista_de_entorno(nombre: str) -> list[str]:
    return [x.strip() for x in os.environ.get(nombre, "").split(",") if x.strip()]


def _clave_secreta() -> str:
    clave = os.environ.get("DJANGO_SECRET_KEY", "").strip()
    if clave:
        return clave
    if PRODUCCION:
        raise ImproperlyConfigured("En producción hay que definir la variable de entorno DJANGO_SECRET_KEY.")
    archivo = BASE_DIR / ".clave_secreta_local"
    if archivo.exists():
        return archivo.read_text(encoding="utf-8").strip()
    clave = get_random_secret_key()
    archivo.write_text(clave, encoding="utf-8")
    return clave


SECRET_KEY = _clave_secreta()
DEBUG = not PRODUCCION

ALLOWED_HOSTS = _lista_de_entorno("DJANGO_ALLOWED_HOSTS") if PRODUCCION else ["localhost", "127.0.0.1", "[::1]", "testserver"]
if PRODUCCION and not ALLOWED_HOSTS:
    raise ImproperlyConfigured("En producción hay que definir DJANGO_ALLOWED_HOSTS (servidores permitidos, separados por coma).")
CSRF_TRUSTED_ORIGINS = _lista_de_entorno("DJANGO_CSRF_TRUSTED_ORIGINS")

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

if PRODUCCION:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SESSION_COOKIE_AGE = 60 * 60  # 60 min sin actividad
    SESSION_SAVE_EVERY_REQUEST = True
    SESSION_EXPIRE_AT_BROWSER_CLOSE = True
    if os.environ.get("DJANGO_PROXY_SSL") == "1":
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "nucleo.apps.NucleoConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

AUTHENTICATION_BACKENDS = ["nucleo.autenticacion.RespaldoConBloqueo"]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# SQLite con WAL (ADR-001): permite leer mientras se escribe. Ruta fuera del código en el servidor.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(os.environ.get("PLANIFICACION_DB_PATH") or (BASE_DIR / "db.sqlite3")),
        "OPTIONS": {
            "timeout": 20,
            "transaction_mode": "IMMEDIATE",
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;",
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "/"

LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"  # zona de negocio
USE_I18N = True
USE_TZ = True  # los instantes se guardan en UTC; los días de negocio se calculan en America/Santiago

STATIC_URL = "static/"
STATIC_ROOT = Path(os.environ.get("PLANIFICACION_STATIC_ROOT") or (BASE_DIR / "staticfiles"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
