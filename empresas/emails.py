from django.conf import settings
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.utils.formats import date_format
from django.utils import timezone
from django.contrib.staticfiles import finders
from email.mime.image import MIMEImage

def _parse_recipients(raw):
    if not raw:
        return []
    raw = raw.replace(";", ",")
    return [e.strip() for e in raw.split(",") if e.strip()]

def _banner_cid_attachment():
    # busca la imagen en staticfiles
    path = finders.find("img/imagen_vencimiento.png")
    if not path:
        return None
    with open(path, "rb") as f:
        img = MIMEImage(f.read())
    img.add_header("Content-ID", "<banner_vencimiento>")  # usar cid:banner_vencimiento
    img.add_header("Content-Disposition", "inline", filename="imagen_vencimiento.png")
    return img

def send_aviso_vencimiento(carta, recipients, days_before):
    if not recipients:
        return 0

    # Construimos contexto
    empresa = carta.empresa
    empresa_nombre = getattr(empresa, "nombre", None) or getattr(empresa, "nombre_consorcio", "") or "—"
    cobertura = getattr(carta, "tipo_completo", None)
    if callable(cobertura):
        cobertura = carta.tipo_completo()

    ctx = {
        "empresa_nombre": empresa_nombre,
        "numero_fianza": carta.numero_fianza,
        "entidad": carta.entidad,
        "aseguradora": carta.aseguradora,
        "cobertura": cobertura,
        "monto_asegurado": f"{carta.moneda} {float(carta.monto):,.2f}",
        "fecha_vencimiento": date_format(carta.fecha_vencimiento, "j \d\e F \d\e Y"),
        "anio": timezone.localdate().year,
    }

    subject = "¡TU FIANZA ESTA A PUNTO DE VENCER!"
    from_email = getattr(settings, "NOTIFY_FROM", None) or getattr(settings, "DEFAULT_FROM_EMAIL", None)
    cc = getattr(settings, "NOTIFY_CC", [])

    html_body = render_to_string("emails/aviso_fianza.html", ctx)
    text_body = (
        f"CIE informa que tu Carta Fianza va a vencer.\n\n"
        f"Empresa/Consorcio: {ctx['empresa_nombre']}\n"
        f"Número de Fianza: {ctx['numero_fianza']}\n"
        f"Entidad: {ctx['entidad']}\n"
        f"Aseguradora: {ctx['aseguradora']}\n"
        f"Cobertura: {ctx['cobertura']}\n"
        f"Monto Asegurado: {ctx['monto_asegurado']}\n"
        f"Fecha de Vencimiento: {ctx['fecha_vencimiento']}\n"
    )

    msg = EmailMultiAlternatives(subject, text_body, from_email, recipients, cc=cc)
    msg.attach_alternative(html_body, "text/html")

    banner = _banner_cid_attachment()
    if banner:
        msg.attach(banner)  # activa <img src="cid:banner_vencimiento">

    return msg.send()