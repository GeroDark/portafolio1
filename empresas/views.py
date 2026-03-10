import calendar
import datetime
import os, json
from decimal import Decimal
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.conf import settings
from pathlib import Path
from django.conf                import settings
from django.contrib             import messages

from django.contrib.auth.decorators import login_required, user_passes_test
from .permissions import role_required, get_role, can_all, can_cartas, can_fidei
from django.db.models           import Q, Sum, Prefetch
from django.http                import JsonResponse
from django.shortcuts           import get_object_or_404, redirect, render
from django.urls                import reverse
from django.utils               import timezone
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.static        import serve
from django.core.exceptions import ValidationError
from .emails import send_aviso_vencimiento
from django.utils.formats import date_format

import calendar
import datetime
import os, json
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, SuspiciousFileOperation
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Prefetch
from django.http import JsonResponse, FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils._os import safe_join   # ✔️ anti path-traversal

from .permissions import role_required, get_role, can_all, can_cartas, can_fidei
from .forms  import (
    EmpresaForm, CartaFianzaForm, FideicomisoForm, DesembolsoForm,
    PagoEmpresaForm, AdelantoPagoFormSet, DocumentoPagoFormSet, CorreoFidFormSet,
    AdelantoFidFormSet, DocumentoFidFormSet, LiquidacionFianzaForm
)
from .models import (
    Empresa, CartaFianza, Fideicomiso, ArchivoAdjunto, Desembolso,
    AdelantoPago, DocumentoPago, PagoEmpresa, CorreoFideicomiso, AdelantoFid,
    DocumentoFid, LiquidacionFianza
)


from .forms  import (EmpresaForm, CartaFianzaForm, FideicomisoForm,
                     DesembolsoForm, PagoEmpresaForm, AdelantoPagoFormSet, DocumentoPagoFormSet, CorreoFidFormSet,
                    AdelantoFidFormSet, DocumentoFidFormSet, LiquidacionFianzaForm)
from .models import (Empresa, CartaFianza, Fideicomiso,
                     ArchivoAdjunto, Desembolso, AdelantoPago, DocumentoPago, PagoEmpresa,CorreoFideicomiso, AdelantoFid, DocumentoFid, LiquidacionFianza)

# ════════════════════════════════════════════════════════════════
# Utilidades de fecha en español
# ════════════════════════════════════════════════════════════════
MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

def _mes_nombre_es(fecha: datetime.date) -> str:
    """Devuelve un nombre de mes en español: «Abril 2024»."""
    return f"{MESES_ES[fecha.month-1].capitalize()} {fecha.year}"

# ════════════════════════════════════════════════════════════════
# Serializador JSON para el modal de Carta Fianza
# ════════════════════════════════════════════════════════════════
def _json_fianza(f: CartaFianza) -> dict:
    emp_nombre = getattr(f.empresa, "nombre", "(sin empresa)")
    data= {
        # ── básicos ──────────────────────────────────────────
        "id":          f.id,
        "empresa":     emp_nombre,
        "numero":      f.numero_fianza,
        "aseguradora": f.aseguradora,
        "aseguradora_otro": f.aseguradora_otro or "",
        "tipo_carta":  f.tipo_completo(),          # «…ADICIONAL V»
        "moneda":      f.moneda,                   # S/  $  €
        "monto":       float(f.monto or 0),
        "plazo_meses": f.plazo_meses,
        "plazo_dias":  f.plazo_dias,
        "plazo":       f"{f.plazo_meses} m / {f.plazo_dias} d",
        "vencimiento": f.fecha_vencimiento.strftime("%d/%m/%Y"),
        "entidad":     f.entidad,
        "afianzado":   f.afianzado or "",
        "numero_adicional": f.numero_adicional or "",

        # ── consorcio ───────────────────────────────────────
        "tiene_consorcio":      f.tiene_consorcio,
        "nombre_consorcio":     f.nombre_consorcio,
        "empresas_consorciadas":f.empresas_consorciadas,
        "representante_legal":  f.representante_legal,
        "dni_representante":    f.dni_representante,
        "es_independiente":     f.es_independiente,
        "tributador":           f.tributador or "",
        "ruc_tributador":       f.ruc_tributador or "",
        "ruc_consorcio":        f.ruc_consorcio or "",

        # ── urls acción ─────────────────────────────────────
        "url_editar":   reverse("editar_carta_fianza",   args=[f.id]),
        "url_eliminar": reverse("eliminar_carta_fianza", args=[f.id]),
        "liquidada":    f.liquidada,
        "url_liquidar": reverse("liquidar_carta", args=[f.id]),
    }
    if f.liquidada and hasattr(f, "liquidacion"):
        liq = f.liquidacion
        from os import path
        data["liquidacion"] = {
            "monto_dev":    float(liq.monto_dev or 0),
            "aseguradora":  liq.aseguradora,
            "fecha_dev":    liq.fecha_dev.strftime("%d/%m/%Y"),
            "nro_fianza":   liq.nro_fianza,
            "documento":    liq.documentos.url if liq.documentos else "",
            "doc_nombre":   path.basename(liq.documentos.name) if liq.documentos else "",
        }

    return data

# ════════════════════════════════════════════════════════════════
# Páginas principales
# ════════════════════════════════════════════════════════════════
def home(request):
    return redirect("buscar_empresa")

def google_login(request):
    if request.user.is_authenticated:
        return redirect("buscar_empresa")  # ajusta si quieres otro destino
    return render(request, "login.html")


@login_required
@role_required("master", "notifier", "cartas", "fidei")
def buscar_empresa(request):
    q = request.GET.get("q", "").strip()
    if not q:
        return render(request, "buscar.html", {"resultado": None})
    resultado = resultado = (
        Empresa.objects
        .prefetch_related(
            # documentos (PDF), correos y desembolsos en una sola ida al DB
            Prefetch("fideicomisos__documentos"),
            Prefetch("fideicomisos__correos"),
            Prefetch("fideicomisos__desembolsos"),
            Prefetch("fideicomisos__adelantos"),
        )
        .filter(
            Q(ruc__iexact=q) |
            Q(nombre__iexact=q) |
            Q(nombre_gerente__iexact=q)|
            Q(nombre_consorcio__iexact=q)         |  
            Q(representante_legal__iexact=q)
        )
        .first()
    )
    return render(request, "buscar.html", {"resultado": resultado})

@login_required
@role_required("master", "notifier", "cartas", "fidei")
def empresa_autocomplete(request):
    term = request.GET.get("term", "").strip()
    qs = (Empresa.objects
            .filter(
                Q(ruc__icontains=term) |
                Q(nombre__icontains=term) |
                Q(nombre_gerente__icontains=term) |
                Q(nombre_consorcio__icontains=term) |
                Q(representante_legal__icontains=term)
            )
            .order_by("nombre")[:10]
         )

    results = []
    for e in qs:
        if e.es_consorcio:
            # para consorcios, devolvemos nombre_consorcio y representante
            results.append({
                "value": e.nombre_consorcio,
                "label": f"{e.nombre_consorcio} – {e.representante_legal}"
            })
        else:
            # para empresas normales, devolvemos RUC y nombre
            results.append({
                "value": e.ruc,
                "label": f"{e.nombre} – {e.ruc}"
            })

    return JsonResponse(results, safe=False)

# ════════════════════════════════════════════════════════════════
# Calendario
# ════════════════════════════════════════════════════════════════
@login_required
@role_required("master", "notifier", "cartas")
def calendario_fianzas(request):
    hoy = timezone.localdate()

    # mes base (parámetro m=YYYY-MM)
    try:
        a, m = map(int, request.GET.get("m", "").split("-"))
        base = datetime.date(a, m, 1)
    except Exception:
        base = hoy.replace(day=1)

    rango_i = base
    rango_f = (base.replace(day=28) + datetime.timedelta(days=4)
               ).replace(day=1) - datetime.timedelta(days=1)

    vencen_mes = CartaFianza.objects.filter(
        fecha_vencimiento__range=[rango_i, rango_f]
    )
    vencidas = CartaFianza.objects.filter(
        fecha_vencimiento__lt=hoy
    ).order_by("-fecha_vencimiento")[:50]
    proximas = CartaFianza.objects.filter(
        fecha_vencimiento__range=[hoy, hoy + datetime.timedelta(days=30)]
    ).order_by("fecha_vencimiento")

    cal = calendar.Calendar(firstweekday=0)
    semanas = []
    for semana in cal.monthdatescalendar(base.year, base.month):
        fila = []
        for d in semana:
            fila.append({
                "fecha": d,
                "hoy": d == hoy,
                "pert": d.month == base.month,
                "fianzas": [f for f in vencen_mes if f.fecha_vencimiento == d],
            })
        semanas.append(fila)

    context = {
        "semanas": semanas,
        "dias_semana": [
            "Lunes", "Martes", "Miércoles", "Jueves",
            "Viernes", "Sábado", "Domingo"
        ],
        "mes_titulo": _mes_nombre_es(base),
        "mes_anterior":  (base - datetime.timedelta(days=1)).strftime("%Y-%m"),
        "mes_siguiente": (base + datetime.timedelta(days=32)
                          ).replace(day=1).strftime("%Y-%m"),
        "mes_actual": base.strftime("%Y-%m"),
        "vencidas": vencidas,
        "proximas": proximas,
    }
    return render(request, "calendario.html", context)

# ════════════════════════════════════════════════════════════════
# Endpoints JSON para el modal
# ════════════════════════════════════════════════════════════════
@login_required
@role_required("master", "notifier", "cartas")
def carta_detalle(request, fianza_id):
    return JsonResponse(_json_fianza(get_object_or_404(CartaFianza, id=fianza_id)))

@login_required
@role_required("master", "notifier", "cartas")

def liquidar_carta(request, fianza_id):
    carta = get_object_or_404(CartaFianza, id=fianza_id)
    try:
        liquid = carta.liquidacion
    except LiquidacionFianza.DoesNotExist:
        liquid = None

    if request.method == 'POST':
        form = LiquidacionFianzaForm(request.POST, request.FILES, instance=liquid)
        if form.is_valid():
            liq = form.save(commit=False)
            liq.carta = carta
            liq.save()
            # marcar la carta como liquidada
            carta.liquidada = True
            carta.save(update_fields=['liquidada'])
            messages.success(request, "Carta Fianza liquidada correctamente.")
            return redirect('buscar_empresa')
    else:
        form = LiquidacionFianzaForm(instance=liquid)

    return render(request, 'liquidar_carta.html', {
        'form': form,
        'carta': carta,
    })

@login_required
@role_required("master", "notifier", "cartas")
def carta_archivos(request, fianza_id):
    f = get_object_or_404(CartaFianza, id=fianza_id)
    archivos = [
        {"id": a.id, "nombre": os.path.basename(a.archivo.name), "url": a.archivo.url}
        for a in f.archivos.all()
    ]
    return JsonResponse({"archivos": archivos})

# ════════════════════════════════════════════════════════════════
# CRUD de Empresas
# ════════════════════════════════════════════════════════════════

@login_required
@role_required("master", "notifier", "cartas", "fidei")
def registrar_empresa(request):
    form = EmpresaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Empresa registrada correctamente.")
        return redirect("buscar_empresa")
    return render(request, "registrar.html", {"form": form})


@login_required
@role_required("master", "notifier", "cartas", "fidei")
def listar_empresas(request):
    q = request.GET.get('q', '').strip()
    ep = request.GET.get("ep", 1)  # página empresas
    cp = request.GET.get("cp", 1)  # página consorcios

    # --- Flags por rol (coherentes con tu context processor) ---
    role = get_role(getattr(request, "user", None))
    SHOW_CARTA_PAGOS = can_all(role) or can_cartas(role)
    SHOW_FIDEI_PAGOS = can_all(role) or can_fidei(role)
    CAN_DELETE_ANY   = can_all(role)

    # 1) Prefetch de pagos (evita N+1)
    base_qs = (
        Empresa.objects
        .prefetch_related(
            Prefetch(
                "pagos",
                queryset=PagoEmpresa.objects.select_related("carta", "fideicomiso").order_by("-created_at"),
                to_attr="pagos_list"
            )
        )
    )

    empresas_qs = base_qs.filter(es_consorcio=False).order_by("nombre", "id")
    consorcios_qs = base_qs.filter(es_consorcio=True).order_by("nombre_consorcio", "id")

    empresas = Paginator(empresas_qs, 5).get_page(ep)
    consorcios = Paginator(consorcios_qs, 5).get_page(cp)

    # 2) Empresa seleccionada (buscador superior)
    seleccionada = None
    if q:
        try:
            seleccionada = Empresa.objects.get(ruc=q)
        except Empresa.DoesNotExist:
            qs = Empresa.objects.filter(
                Q(nombre__iexact=q) |
                Q(nombre_gerente__iexact=q) |
                Q(nombre_consorcio__iexact=q) |
                Q(representante_legal__iexact=q)
            )
            seleccionada = qs.first() if qs.count() == 1 else None

    # 3) Si hay seleccionada: separar pagos por origen y respetar visibilidad por rol
    pagos_cartas = pagos_fidei = None
    if seleccionada:
        seleccionada = base_qs.get(pk=seleccionada.pk)
        pagos_cartas = [p for p in seleccionada.pagos_list if p.origen == "CARTA"] if SHOW_CARTA_PAGOS else []
        pagos_fidei  = [p for p in seleccionada.pagos_list if p.origen == "FIDEI"] if SHOW_FIDEI_PAGOS else []

    # 4) Adjuntar PAGOS VISIBLES a cada empresa/consorcio (y contar solo lo visible)
    def _filtra(lista):
        if SHOW_CARTA_PAGOS and SHOW_FIDEI_PAGOS:
            return lista
        if SHOW_CARTA_PAGOS:
            return [p for p in lista if p.origen == "CARTA"]
        if SHOW_FIDEI_PAGOS:
            return [p for p in lista if p.origen == "FIDEI"]
        return []

    def _page_numbers(page_obj, window=2):
        total = page_obj.paginator.num_pages
        current = page_obj.number

        raw = {1, total}
        raw.update(range(max(1, current - window), min(total, current + window) + 1))
        ordered = sorted(raw)

        result = []
        prev = None
        for num in ordered:
            if prev is not None and num - prev > 1:
                result.append(None)  # muestra "..."
            result.append(num)
            prev = num
        return result

    for e in empresas.object_list:
        lista = getattr(e, "pagos_list", [])
        e.pagos_visibles = _filtra(lista)
        e.pagos_count = len(e.pagos_visibles)

    for c in consorcios.object_list:
        lista = getattr(c, "pagos_list", [])
        c.pagos_visibles = _filtra(lista)
        c.pagos_count = len(c.pagos_visibles)

    return render(request, "listar_empresas.html", {
        "empresas": empresas,
        "consorcios": consorcios,
        "empresas_page_numbers": _page_numbers(empresas),
        "consorcios_page_numbers": _page_numbers(consorcios),
        "busqueda": q,
        "seleccionada": seleccionada,
        "pagos_cartas": pagos_cartas,
        "pagos_fidei": pagos_fidei,
        "SHOW_CARTA_PAGOS": SHOW_CARTA_PAGOS,
        "SHOW_FIDEI_PAGOS": SHOW_FIDEI_PAGOS,
        "CAN_DELETE_ANY": CAN_DELETE_ANY,
    })

@login_required
@role_required("master", "notifier", "cartas", "fidei")
def editar_empresa(request, empresa_id):
    empresa = get_object_or_404(Empresa, id=empresa_id)
    form = EmpresaForm(request.POST or None, instance=empresa)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Empresa actualizada correctamente.")
        return redirect("listar_empresas")
    return render(request, "editar_empresa.html",
                  {"form": form, "empresa": empresa})


@login_required
@role_required("master", "notifier")
def eliminar_empresa(request, empresa_id):
    empresa = get_object_or_404(Empresa, id=empresa_id)
    if request.method == "POST":
        empresa.delete()
        messages.success(request, "Empresa eliminada correctamente.")
        return redirect("listar_empresas")
    return render(request, "eliminar_empresa.html", {"empresa": empresa})

# ════════════════════════════════════════════════════════════════
# CRUD de Carta Fianza
# ════════════════════════════════════════════════════════════════

@login_required
@role_required("master", "notifier", "cartas")
def agregar_carta_fianza(request, empresa_id):
    empresa = get_object_or_404(Empresa, id=empresa_id)
    form = CartaFianzaForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        carta = form.save(commit=False)
        carta.empresa = empresa
        carta.save()
        for f in request.FILES.getlist("nuevos_archivos"):
            ArchivoAdjunto.objects.create(carta=carta, archivo=f)
        messages.success(request, "Carta fianza registrada correctamente.")
        return redirect("buscar_empresa")
    return render(request, "agregar_carta.html",
                  {"form": form, "empresa": empresa})


@login_required
@role_required("master", "notifier", "cartas")
def editar_carta_fianza(request, fianza_id):
    fianza = get_object_or_404(CartaFianza, id=fianza_id)
    form = CartaFianzaForm(request.POST or None, request.FILES or None,
                           instance=fianza)
    archivos = fianza.archivos.exclude(archivo__isnull=True)\
                              .exclude(archivo__exact='')
    if request.method == "POST" and form.is_valid():
        carta = form.save()
        for archivo in archivos:
            if str(archivo.id) in request.POST.getlist("eliminar_archivo"):
                archivo.archivo.delete(save=False)
                archivo.delete()
        for f in request.FILES.getlist("nuevos_archivos"):
            ArchivoAdjunto.objects.create(carta=carta, archivo=f)
        messages.success(request, "Carta fianza actualizada correctamente.")
        return redirect("buscar_empresa")
    return render(request, "editar_carta.html",
                  {"form": form, "fianza": fianza, "archivos": archivos})


@login_required
@role_required("master", "notifier")
def eliminar_carta_fianza(request, fianza_id):
    fianza = get_object_or_404(CartaFianza, id=fianza_id)
    if request.method == "POST":
        fianza.delete()
        messages.success(request, "Carta fianza eliminada.")
        return redirect("buscar_empresa")
    return render(request, "eliminar_carta.html", {"fianza": fianza})

# ════════════════════════════════════════════════════════════════
# CRUD de Fideicomiso y Desembolsos
# ════════════════════════════════════════════════════════════════

@login_required
@role_required("master", "notifier", "fidei")
def agregar_fideicomiso(request, empresa_id):
    empresa = get_object_or_404(Empresa, id=empresa_id)

    if request.method == "POST":
        form        = FideicomisoForm(request.POST, request.FILES)
        adelanto_fs = AdelantoFidFormSet(request.POST, prefix="adels")
        docs_fs     = DocumentoFidFormSet(request.POST, request.FILES, prefix="docs")

        adel_ok = adelanto_fs.is_valid()
        docs_ok = docs_fs.is_valid()

        total_adel = Decimal("0")
        if adel_ok:
            for a in adelanto_fs.cleaned_data:
                if a and not a.get("DELETE", False):
                    total_adel += Decimal(a["monto"])
        form._suma_adel = total_adel

        if form.is_valid() and adel_ok and docs_ok:
            fidei = form.save(commit=False)
            fidei.empresa = empresa
            fidei.save()

            adelanto_fs.instance = fidei
            adelanto_fs.save()
            docs_fs.instance = fidei
            docs_fs.save()

            messages.success(request, "Fideicomiso registrado correctamente.")
            return redirect("buscar_empresa")
    else:
        form        = FideicomisoForm()
        adelanto_fs = AdelantoFidFormSet(prefix="adels", queryset=AdelantoFid.objects.none())
        docs_fs     = DocumentoFidFormSet(prefix="docs", queryset=DocumentoFid.objects.none())

    return render(request, "agregar_fideicomiso.html", {
        "empresa": empresa,
        "form": form,
        "adelanto_fs": adelanto_fs,
        "docs_fs": docs_fs,
    })


# ───────────────────────────────────────────────

@login_required
@role_required("master", "notifier", "fidei")
def editar_fideicomiso(request, fideicomiso_id):
    fidei = get_object_or_404(Fideicomiso, id=fideicomiso_id)

    if request.method == "POST":
        form        = FideicomisoForm(request.POST, request.FILES, instance=fidei)
        adelanto_fs = AdelantoFidFormSet(request.POST, instance=fidei, prefix="adels")
        docs_fs     = DocumentoFidFormSet(request.POST, request.FILES, instance=fidei, prefix="docs")

        adel_ok = adelanto_fs.is_valid()
        docs_ok = docs_fs.is_valid()

        total_adel = Decimal("0")
        if adel_ok:
            for a in adelanto_fs.cleaned_data:
                if a and not a.get("DELETE", False):
                    total_adel += Decimal(a["monto"])
        form._suma_adel = total_adel

        if form.is_valid() and adel_ok and docs_ok:
            form.save()
            adelanto_fs.save()
            docs_fs.save()
            messages.success(request, "Fideicomiso actualizado correctamente.")
            return redirect("buscar_empresa")
    else:
        form        = FideicomisoForm(instance=fidei)
        adelanto_fs = AdelantoFidFormSet(instance=fidei, prefix="adels")
        docs_fs     = DocumentoFidFormSet(instance=fidei, prefix="docs")

    return render(request, "editar_fideicomiso.html", {
        "fideicomiso": fidei,
        "form": form,
        "adelanto_fs": adelanto_fs,
        "docs_fs": docs_fs,
    })

@login_required
@role_required("master", "notifier")
def eliminar_fideicomiso(request, fideicomiso_id):
    fideicomiso = get_object_or_404(Fideicomiso, id=fideicomiso_id)
    if request.method == "POST":
        fideicomiso.delete()
        messages.success(request, "Fideicomiso eliminado.")
        return redirect("buscar_empresa")
    return render(request, "eliminar_fideicomiso.html",
                  {"fideicomiso": fideicomiso})

@login_required
@role_required("master", "notifier", "fidei")
def agregar_desembolso(request, fideicomiso_id):
    fidei = get_object_or_404(Fideicomiso, id=fideicomiso_id)
    form = DesembolsoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.save(commit=False)
        d.fideicomiso = fidei
        if d.tipo == "DIRECTO":
            tope    = fidei.directo_con_retencion or Decimal("0")
            gastado = fidei.desembolsos.filter(tipo="DIRECTO"
                       ).aggregate(t=Sum("monto"))["t"] or Decimal("0")
        else:
            tope    = fidei.materiales_con_retencion or Decimal("0")
            gastado = fidei.desembolsos.filter(tipo="MATERIALES"
                       ).aggregate(t=Sum("monto"))["t"] or Decimal("0")
        if gastado + d.monto > tope:
            form.add_error("monto",
                "La suma de desembolsos supera el adelanto con retención")
        else:
            d.save()
            messages.success(request, "Desembolso registrado.")
            return redirect("buscar_empresa")
    return render(request, "agregar_desembolso.html",
                  {"form": form, "fideicomiso": fidei})




# ════════════════════════════════════════════════════════════════
# Servir /media/ en desarrollo permitiendo iframes
# ════════════════════════════════════════════════════════════════
ALLOWED_MEDIA_EXTS = {".pdf", ".jpg", ".jpeg", ".png"}  # ajusta si hace falta

@login_required
def media_protegida(request, path: str):
    try:
        abs_path = safe_join(settings.MEDIA_ROOT, path)  # evita ../../
    except SuspiciousFileOperation:
        raise Http404

    p = Path(abs_path)
    if not p.exists() or not p.is_file():
        raise Http404
    if p.suffix.lower() not in ALLOWED_MEDIA_EXTS:
        raise Http404

    # (opcional) chequeos por rol/propiedad del recurso
    return FileResponse(open(abs_path, "rb"))

@login_required

def nuevo_pago_empresa(request,empresa_id):
    
    empresa = get_object_or_404(Empresa, id=empresa_id)

    if request.method == "POST":
        form = PagoEmpresaForm(request.POST, request.FILES, empresa=empresa)
        if form.is_valid():
            pago = form.save(commit=False)
            pago.empresa = empresa
            pago.full_clean()  # asegura validación del modelo
            pago.save()
            ...
    else:
        form = PagoEmpresaForm(empresa=empresa)

    return render(request, "registrar_pago.html", {"form": form, "empresa": empresa})

@login_required

def editar_pago_empresa(request, pago_id):
    pago = get_object_or_404(PagoEmpresa, id=pago_id)

    # ---------- POST ----------
    if request.method == "POST":
        form = PagoEmpresaForm(request.POST, request.FILES, instance=pago, empresa=pago.empresa)

        # Adelantos en el cuerpo del POST (los necesitamos incluso si el form es inválido)
        adelantos_data = json.loads(request.POST.get("adelantos", "[]"))
        adelantos_json = json.dumps(adelantos_data)   # para recargar la página si hay errores

        # Documentos adjuntos actuales (para volver a listarlos si el form es inválido)
        documentos = pago.documentos.all()

        if form.is_valid():
            pago = form.save(commit=False)
            pago.full_clean()
            pago.save()
            # 1. Sustituir los adelantos existentes
            pago.adelantos.all().delete()
            for a in adelantos_data:
                AdelantoPago.objects.create(
                    pago=pago,
                    fecha=a["fecha"],
                    monto=a["monto"]
                )

            # 2. Eliminar documentos marcados
            for pk in request.POST.getlist("delete_doc"):
                pago.documentos.filter(id=pk).delete()

            # 3. Añadir nuevos documentos
            for f in request.FILES.getlist("adjuntos"):
                DocumentoPago.objects.create(pago=pago, archivo=f)

            messages.success(request, "Pago actualizado correctamente.")
            return redirect("listar_empresas")

        # Si el formulario NO es válido, volvemos a renderizar con los errores
        messages.error(request, "Corrige los errores del formulario.")

    # ---------- GET ----------
    else:
        form = PagoEmpresaForm(instance=pago, empresa=pago.empresa)
        adelantos_json = json.dumps([
            {"fecha": a.fecha.isoformat(), "monto": float(a.monto)}
            for a in pago.adelantos.all()
        ])
        documentos = pago.documentos.all()

    # ********** usa la NUEVA plantilla **********
    return render(request, "editar_pago.html", {
        "form":           form,
        "pago":           pago,
        "adelantos_json": adelantos_json,
        "documentos":     documentos,
    })

@login_required

def agregar_pago_empresa(request, empresa_id):
    empresa = get_object_or_404(Empresa, id=empresa_id)

    if request.method == "POST":
        form = PagoEmpresaForm(request.POST, request.FILES, empresa=empresa)
        if form.is_valid():
            pago = form.save(commit=False)
            pago.empresa = empresa
            pago.save()

            # Adelantos
            raw = request.POST.get('adelantos','')
            if raw:
                try:
                    for item in json.loads(raw):
                        AdelantoPago.objects.create(
                            pago=pago,
                            monto=item['monto'],
                            fecha=item['fecha']
                        )
                except ValueError:
                    messages.warning(request, "No se pudieron procesar los adelantos.")

            # Documentos
            for f in request.FILES.getlist('adjuntos'):
                DocumentoPago.objects.create(pago=pago, archivo=f)

            messages.success(request, "Pago registrado correctamente.")
            return redirect('listar_empresas')
        else:
            # form.errors ya contiene todos los mensajes de campo
            messages.error(request, "Corrige los errores en el formulario.")
    else:
        form = PagoEmpresaForm(empresa=empresa)

    return render(request, "registrar_pago.html", {"empresa": empresa, "form": form})
@login_required

def eliminar_pago_empresa(request, pago_id):
    pago = get_object_or_404(PagoEmpresa, id=pago_id)

    if request.method == "POST":
        pago.delete()
        messages.success(request, "Pago eliminado correctamente.")
        return redirect("listar_empresas")          # ← adónde vuelves después

    # GET → página de confirmación
    return render(request, "eliminar_pago.html", {
        "pago": pago,
    })
@login_required
@role_required("master", "notifier")
def probar_aviso(request):
    """
    Formulario simple:
    - Ingresa ID de CartaFianza y correo destino.
    - Envía el correo usando la misma plantilla/función.
    - NO crea AvisoVencimiento (es solo prueba).
    """
    if request.method == "POST":
        to = (request.POST.get("to") or "").strip()
        fianza_id = (request.POST.get("fianza_id") or "").strip()

        if not to or not fianza_id.isdigit():
            messages.error(request, "Completa los campos correctamente.")
            return redirect("probar_aviso")

        carta = get_object_or_404(CartaFianza, id=int(fianza_id))
        today = timezone.localdate()
        days_before = (carta.fecha_vencimiento - today).days
        # Si ya venció o está fuera de rango, igual enviamos el formato usando 15 como valor por defecto
        if days_before <= 0:
            days_before = 15

        sent = send_aviso_vencimiento(carta, [to], days_before)
        if sent:
            messages.success(request, f"Correo de prueba enviado a {to}.")
        else:
            messages.error(request, "No se pudo enviar el correo (revisa SMTP).")

        return redirect("probar_aviso")

    # GET: mostrar formulario con el correo por defecto que pediste
    return render(request, "probar_aviso.html", {
        "default_to": "72807968@continental.edu.pe"
    })

@login_required
@role_required("master", "notifier")
def preview_aviso(request, fianza_id: int):
    """
    Muestra el HTML del correo en el navegador para revisión visual.
    No envía nada.
    """
    carta = get_object_or_404(CartaFianza, id=fianza_id)
    ctx = {
        "empresa_nombre": getattr(carta.empresa, "nombre", "") or getattr(carta.empresa, "nombre_consorcio", ""),
        "numero_fianza": carta.numero_fianza,
        "entidad": carta.entidad,
        "aseguradora": carta.aseguradora,
        "cobertura": carta.cobertura,
        "monto_asegurado": carta.monto_asegurado,
        "fecha_vencimiento": date_format(carta.fecha_vencimiento, "DATE_FORMAT"),
        "anio": timezone.localdate().year,
    }
    return render(request, "emails/aviso_fianza.html", ctx)