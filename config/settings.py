"""
Django settings for the project.
"""

from pathlib import Path
import os                                  
from dotenv import load_dotenv
import dj_database_url



# ──────────────────── Paths ────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env") 

# ─────────────────── Seguridad ─────────────────
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not set")
DEBUG = os.getenv("DEBUG", "0") == "1"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")

CSRF_TRUSTED_ORIGINS = [
    f"https://{h}" for h in ALLOWED_HOSTS
    if h not in ("127.0.0.1","localhost") and not h.startswith("http")
]

if DEBUG:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False
else:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

CSRF_COOKIE_HTTPONLY = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

AUTHENTICATION_BACKENDS = (
    "social_core.backends.google.GoogleOAuth2",
    "django.contrib.auth.backends.ModelBackend",
)

# ──────────────── Aplicaciones INSTALLED_APPS ───────────────
INSTALLED_APPS = [
    "social_django",         #api_login_google
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    

    "empresas",                  # nuestra app
]

# ─────────────────── Middleware ─────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "social_django.middleware.SocialAuthExceptionMiddleware",
    "empresas.middleware.AvisosDiarios8AMMiddleware",
    # IMPORTANTE: dejar el click-jacking al final
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

X_FRAME_OPTIONS = 'SAMEORIGIN'


# ─────────────────── Templates ──────────────────────────────
ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],                     # templates de cada app
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "social_django.context_processors.backends",        
                "social_django.context_processors.login_redirect", 
                "empresas.context_processors.role_flags",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# ─────────────────── Base de datos ──────────────────────────
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{(BASE_DIR / 'db.sqlite3')}",
        conn_max_age=60,      # mantiene conexiones (mejora rendimiento)
        ssl_require=False,    # estamos dentro de la misma VM; no necesitamos SSL hacia localhost
    )
}

# Recomendable cuando hay formularios que escriben a BD
# Evita lecturas/escrituras parciales si una vista lanza excepción.
DATABASES["default"]["ATOMIC_REQUESTS"] = True  # <-- OPCIONAL, pero útil en apps sencillas


# ─────────── Validadores de contraseña ──────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ──────────────── Internacionalización ──────────────────────
LANGUAGE_CODE = 'es'
TIME_ZONE = 'America/Lima'
USE_I18N = True
USE_TZ = True


# ─────────────────── Archivos STATIC / MEDIA ────────────────
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"      # para collectstatic

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / "media"             # /…/media/archivos_adjunto/…

# ─────────────────── Login / Logout ─────────────────────────
LOGIN_URL          = "login"
LOGIN_REDIRECT_URL = "buscar_empresa"
LOGOUT_REDIRECT_URL = "login"

# ─────────────────── Clave primaria por defecto ─────────────
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


SOCIAL_AUTH_GOOGLE_OAUTH2_KEY    = os.getenv("GOOGLE_OAUTH_CLIENT_ID")     
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET") 
SOCIAL_AUTH_LOGIN_ERROR_URL = '/login/'

EMAIL_ROLES = {
    os.getenv("EMAIL_MASTER",       "gerencia.comercial@cieconsultora.com").lower():      "master",
    os.getenv("EMAIL_NOTIF",        "notificaciones@cieconsultora.com").lower(): "notifier",
    os.getenv("EMAIL_CARTAS",       "catherine.gonzales@cieconsultora.com").lower():      "cartas",
    os.getenv("EMAIL_FIDEICOMISO",  "gustavo.gonzales@cieconsultora.com").lower(): "fidei",
}

SOCIAL_AUTH_PIPELINE = (
    'social_core.pipeline.social_auth.social_details',
    'social_core.pipeline.social_auth.social_uid',
    'social_core.pipeline.social_auth.auth_allowed',   # respeta settings de social-auth
    'social_core.pipeline.social_auth.social_user',
    'social_core.pipeline.user.get_username',
    'social_core.pipeline.user.create_user',
    'empresas.auth_pipeline.user_allowed',             # <-- NUEVO paso de bloqueo
    'social_core.pipeline.social_auth.associate_user',
    'social_core.pipeline.social_auth.load_extra_data',
    'social_core.pipeline.user.user_details',
)
NOTIFY_FROM = os.getenv("NOTIFY_FROM", os.getenv("DEFAULT_FROM_EMAIL", "notificaciones@cieconsultora.com"))
NOTIFY_CC = [e.strip() for e in os.getenv("NOTIFY_CC", "").replace(";", ",").split(",") if e.strip()]

# Recomendado (si tu servidor corre en Perú):
TIME_ZONE = 'America/Lima'
USE_TZ = True

EMAIL_BACKEND      = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST         = os.getenv("EMAIL_HOST", "")
EMAIL_PORT         = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER    = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD= os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS      = os.getenv("EMAIL_USE_TLS","1") == "1"
EMAIL_USE_SSL      = os.getenv("EMAIL_USE_SSL","0") == "1"
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "notificaciones@cieconsultora.com")
SERVER_EMAIL       = os.getenv("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
EMAIL_TIMEOUT      = int(os.getenv("EMAIL_TIMEOUT","30"))
USE_I18N = True
USE_TZ = True
DATE_FORMAT = "j \\d\\e F \\d\\e Y"
