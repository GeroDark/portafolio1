from functools import wraps
from django.conf import settings
from django.http import HttpResponseForbidden

def _email(u):
    return (u.email or "").strip().lower() if u and getattr(u, "email", None) else ""

def get_role(user):
    """Devuelve: 'master' | 'notifier' | 'cartas' | 'fidei' | None"""
    if not user or not user.is_authenticated:
        return None
    # superuser siempre tiene todo
    if getattr(user, "is_superuser", False):
        return "master"
    return settings.EMAIL_ROLES.get(_email(user))

# Helpers de permisos (por si los usas en vistas)
def can_all(role):       return role in {"master", "notifier"}
def can_cartas(role):    return role in {"master", "notifier", "cartas"}
def can_fidei(role):     return role in {"master", "notifier", "fidei"}
def can_pagos(role):     return role in {"master", "notifier"}
def can_calend(role):    return role in {"master", "notifier", "cartas"}  # 'fidei' no ve calendario

def role_required(*allowed_roles):
    """
    Uso:
    @login_required
    @role_required('master','notifier','cartas')
    def mi_vista(...):
        ...
    """
    def deco(view):
        @wraps(view)
        def _wrap(request, *args, **kwargs):
            role = get_role(request.user)
            if role in allowed_roles:
                return view(request, *args, **kwargs)
            return HttpResponseForbidden("No tienes permisos para esta acción.")
        return _wrap
    return deco
