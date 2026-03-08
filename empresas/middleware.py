# empresas/middleware.py
import threading
from django.utils import timezone
from empresas.tasks import procesar_avisos_fianzas

# Variables de proceso (cada worker tendrá las suyas; no pasa nada)
_LAST_RUN_DATE = None
_LOCK = threading.Lock()

TARGET_HOUR = 8  # 08:00 America/Lima (ya usas TIME_ZONE="America/Lima")

def _should_run(now):
    """Ejecutar solo si ya son >= 08:00 y aún no se ejecutó hoy en ESTE proceso."""
    global _LAST_RUN_DATE
    if now.hour < TARGET_HOUR:
        return False
    today = now.date()
    return _LAST_RUN_DATE != today

def _mark_ran(today):
    global _LAST_RUN_DATE
    _LAST_RUN_DATE = today

def _trigger_async():
    # Ejecutamos en segundo plano para no demorar el request
    t = threading.Thread(target=procesar_avisos_fianzas, kwargs={"dry_run": False}, daemon=True)
    t.start()

class AvisosDiarios8AMMiddleware:
    """
    Corre cada día, al primer request >= 08:00, en cada proceso.
    No genera correos duplicados porque la función valida AvisoVencimiento(carta, days_before).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        now = timezone.localtime()
        if _should_run(now):
            with _LOCK:
                # doble chequeo dentro del lock
                if _should_run(now):
                    _mark_ran(now.date())
                    _trigger_async()
        return self.get_response(request)
