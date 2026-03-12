from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


ALLOWED_PROPUESTAS_ROLES = {"master", "notifier"}


def _user_email(user) -> str:
    return (getattr(user, "email", "") or "").strip().lower()


def _email_roles_map() -> dict:
    return getattr(settings, "EMAIL_ROLES", {}) or {}


def get_roles_for_user(user) -> set[str]:
    if not getattr(user, "is_authenticated", False):
        return set()

    email = _user_email(user)
    if not email:
        return set()

    roles_map = _email_roles_map()
    raw_roles = roles_map.get(email)

    if not raw_roles:
        return set()

    if isinstance(raw_roles, str):
        return {raw_roles.strip().lower()}

    if isinstance(raw_roles, (list, tuple, set)):
        return {str(role).strip().lower() for role in raw_roles if str(role).strip()}

    return {str(raw_roles).strip().lower()}


def can_access_propuestas(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False

    if getattr(user, "is_superuser", False):
        return True

    roles = get_roles_for_user(user)
    return bool(ALLOWED_PROPUESTAS_ROLES & roles)


def can_manage_propuestas(user) -> bool:
    return can_access_propuestas(user)


def propuestas_access_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not can_access_propuestas(request.user):
            raise PermissionDenied("No tienes permisos para acceder al módulo de propuestas.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def propuestas_manage_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not can_manage_propuestas(request.user):
            raise PermissionDenied("No tienes permisos para gestionar propuestas.")
        return view_func(request, *args, **kwargs)

    return _wrapped