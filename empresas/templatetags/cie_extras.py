# empresas/templatetags/cie_extras.py
import re
from django import template

register = template.Library()


@register.filter
def replace(value, args="_"):
    """
    Reemplaza substrings dentro de los templates.

    Uso simple  (un argumento) ─────────────────────────────
        {{ texto|replace:"_" }}
        Reemplaza todos los guiones bajos por un espacio.

    Uso avanzado (dos argumentos) ─────────────────────────
        {{ texto|replace:"x>y" }}
        Reemplaza todas las “x” por “y”.
        Solo el primer “>” se toma como separador.

    Si *value* no es una cadena, se convierte a str() para evitar errores.
    """
    if not isinstance(value, str):
        value = str(value)

    if ">" in args:
        old, new = args.split(">", 1)
    else:
        old, new = args, " "

    return value.replace(old, new)

@register.filter
def consorcio_en_lineas(value):
    if not value:
        return "—"

    if not isinstance(value, str):
        value = str(value)

    partes = [p.strip() for p in re.split(r"\s*(?:,|;|\n)\s*", value) if p.strip()]
    return "\n".join(partes) if partes else "—"