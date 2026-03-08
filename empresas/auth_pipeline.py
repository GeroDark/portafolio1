
from django.conf import settings
from social_core.exceptions import AuthForbidden   

def user_allowed(backend, details, response, *args, **kwargs):
    email = (details.get('email') or '').strip().lower()
    # Solo los correos mapeados en EMAIL_ROLES pueden pasar
    if email not in settings.EMAIL_ROLES.keys():
        raise AuthForbidden(backend)