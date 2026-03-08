# empresas/tasks.py
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from empresas.models import CartaFianza, AvisoVencimiento
from empresas.emails import send_aviso_vencimiento

RANGO = {15, 16, 17, 18, 19, 20}

def _parse_recipients(raw: str):
    if not raw:
        return []
    raw = raw.replace(";", ",")
    return [e.strip() for e in raw.split(",") if e.strip()]

def procesar_avisos_fianzas(dry_run: bool = False, stdout=None):
    """
    Ejecuta la misma lógica del management command:
    - Busca cartas no liquidadas que vencen entre 15 y 20 días.
    - Evita duplicados con AvisoVencimiento(carta, days_before).
    - Envía correos a empresa.correo_envio (coma/; separadas).
    """
    today = timezone.localdate()
    ini = today + timedelta(days=min(RANGO))
    fin = today + timedelta(days=max(RANGO))
    qs = CartaFianza.objects.filter(liquidada=False,
                                    fecha_vencimiento__range=(ini, fin))
    total_candidatos = 0
    total_enviados = 0

    for carta in qs.select_related("empresa"):
        days_before = (carta.fecha_vencimiento - today).days
        if days_before not in RANGO:
            continue

        # Evita duplicados por carta+días
        if AvisoVencimiento.objects.filter(carta=carta, days_before=days_before).exists():
            continue

        recipients = _parse_recipients(getattr(carta.empresa, "correo_envio", ""))
        if not recipients:
            if stdout:
                stdout.write(f"Sin correos en empresa {carta.empresa} - {carta.numero_fianza}")
            continue

        total_candidatos += 1
        if dry_run:
            continue

        with transaction.atomic():
            sent = send_aviso_vencimiento(carta, recipients, days_before)
            AvisoVencimiento.objects.create(
                carta=carta,
                days_before=days_before,
                recipients=",".join(recipients),
            )
            total_enviados += sent

    if stdout:
        stdout.write(f"Candidatos: {total_candidatos} | Enviados: {total_enviados}")

    return total_candidatos, total_enviados
