from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q

from empresas.models import CartaFianza, Empresa, Fideicomiso

from .models import Propuesta, PropuestaMovimientoPago


def _existing_model_fields(model) -> set[str]:
    return {field.name for field in model._meta.get_fields() if hasattr(field, "attname")}


def _build_or_query(model, query: str, candidate_fields: list[str]) -> Q:
    model_fields = _existing_model_fields(model)
    q_obj = Q()

    for field_name in candidate_fields:
        if field_name in model_fields:
            q_obj |= Q(**{f"{field_name}__icontains": query})

    return q_obj


def buscar_empresas_para_propuestas(query: str, limit: int = 20):
    qs = Empresa.objects.all()

    if query:
        filtros = _build_or_query(
            Empresa,
            query,
            [
                "nombre",
                "ruc",
                "gerente_general",
                "nombre_consorcio",
                "representante_legal",
                "dni_representante",
                "correo",
                "telefono",
            ],
        )
        qs = qs.filter(filtros)

    return qs.order_by("nombre", "nombre_consorcio")[:limit]

def cartas_fianza_para_empresa(empresa_id: int | None):
    if not empresa_id:
        return CartaFianza.objects.none()

    return (
        CartaFianza.objects.select_related("empresa")
        .filter(
            Q(empresa_id=empresa_id) |
            Q(empresas_relacionadas__id=empresa_id)
        )
        .distinct()
    )

def fideicomisos_para_empresa(empresa_id: int | None):
    if not empresa_id:
        return Fideicomiso.objects.none()

    return (
        Fideicomiso.objects.select_related("empresa")
        .filter(
            Q(empresa_id=empresa_id) |
            Q(empresas_relacionadas__id=empresa_id)
        )
        .distinct()
    )


def buscar_cartas_fianza(query: str, limit: int = 20, empresa_id: int | None = None):
    qs = cartas_fianza_para_empresa(empresa_id)

    if query:
        filtros_propios = _build_or_query(
            CartaFianza,
            query,
            [
                "numero_fianza",
                "aseguradora",
                "aseguradora_otro",
                "entidad",
                "tipo_carta",
            ],
        )
        filtros_empresa = Q()
        empresa_fields = _existing_model_fields(Empresa)
        for field_name in ["nombre", "nombre_consorcio", "ruc"]:
            if field_name in empresa_fields:
                filtros_empresa |= Q(**{f"empresa__{field_name}__icontains": query})

        qs = qs.filter(filtros_propios | filtros_empresa)

    return qs.order_by("-id").distinct()[:limit]

def buscar_fideicomisos(query: str, limit: int = 20, empresa_id: int | None = None):
    qs = fideicomisos_para_empresa(empresa_id)

    if query:
        filtros_propios = _build_or_query(
            Fideicomiso,
            query,
            [
                "fiduciaria",
                "ejecutora",
                "representante",
                "residente",
                "estado",
            ],
        )

        filtros_empresa = Q()
        empresa_fields = _existing_model_fields(Empresa)
        for field_name in ["nombre", "nombre_consorcio", "ruc"]:
            if field_name in empresa_fields:
                filtros_empresa |= Q(**{f"empresa__{field_name}__icontains": query})

        qs = qs.filter(filtros_propios | filtros_empresa)

    return qs.order_by("-id").distinct()[:limit]


def propuestas_por_empresa(empresa_id: int):
    return (
        Propuesta.objects.activos()
        .filter(empresa_id=empresa_id)
        .select_related("empresa", "creado_por", "actualizado_por")
        .prefetch_related(
            "relaciones_cartas",
            "relaciones_fideicomisos",
            "movimientos",
            "documentos",
        )
        .order_by("-created_at")
    )


def propuestas_cf_por_empresa(empresa_id: int):
    return propuestas_por_empresa(empresa_id).filter(
        tipo_propuesta=Propuesta.TipoPropuesta.CARTA_FIANZA
    )


def propuestas_fd_por_empresa(empresa_id: int):
    return propuestas_por_empresa(empresa_id).filter(
        tipo_propuesta=Propuesta.TipoPropuesta.FIDEICOMISO
    )


def metricas_mensuales_propuestas():
    """
    Placeholder para el panel futuro.
    Déjalo así por ahora; luego lo llenamos con agregaciones reales.
    """
    return {
        "ingreso_mensual": 0,
        "pendiente_total": 0,
        "propuestas_con_saldo": 0,
    }


def _month_bounds(base_date: date):
    month_start = base_date.replace(day=1)

    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1, day=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1, day=1)

    month_end = next_month - timedelta(days=1)
    return month_start, month_end


def _empresa_nombre_propuesta(propuesta: Propuesta) -> str:
    empresa = getattr(propuesta, "empresa", None)
    return (
        propuesta.empresa_nombre_snapshot
        or getattr(empresa, "nombre_consorcio", "")
        or getattr(empresa, "nombre", "")
        or ""
    )


def _base_evento_propuesta(
    propuesta: Propuesta,
    *,
    tipo_evento: str,
    tipo_label: str,
    monto_evento=None,
):
    return {
        "tipo_evento": tipo_evento,  # propuesta | pago | vencimiento
        "tipo_label": tipo_label,
        "propuesta_id": propuesta.id,
        "codigo": propuesta.codigo,
        "empresa_nombre": _empresa_nombre_propuesta(propuesta),
        "moneda": propuesta.moneda,
        "monto_total": propuesta.monto_total,
        "estado_pago": propuesta.estado_pago_actual,
        "estado_pago_label": propuesta.get_estado_pago_actual_display(),
        "monto_evento": monto_evento,
    }


def calendario_propuestas_mes(base_date: date):
    month_start, month_end = _month_bounds(base_date)

    propuestas = list(
        Propuesta.objects.activos()
        .select_related("empresa")
        .filter(fecha_propuesta__range=(month_start, month_end))
        .order_by("fecha_propuesta", "-created_at", "-id")
    )

    pagos = list(
        PropuestaMovimientoPago.objects.select_related("propuesta", "propuesta__empresa")
        .filter(
            propuesta__is_deleted=False,
            fecha__range=(month_start, month_end),
        )
        .order_by("fecha", "orden", "id")
    )

    vencimientos = list(
        PropuestaMovimientoPago.objects.select_related("propuesta", "propuesta__empresa")
        .filter(
            propuesta__is_deleted=False,
            tipo_comprobante=PropuestaMovimientoPago.TipoComprobante.FACTURA,
            factura_modalidad=PropuestaMovimientoPago.FacturaModalidad.CREDITO,
            factura_credito_cancelado=False,
            factura_fecha_vencimiento__range=(month_start, month_end),
        )
        .order_by("factura_fecha_vencimiento", "fecha", "orden", "id")
    )

    eventos_por_fecha = defaultdict(list)

    for propuesta in propuestas:
        eventos_por_fecha[propuesta.fecha_propuesta].append(
            {
                **_base_evento_propuesta(
                    propuesta,
                    tipo_evento="propuesta",
                    tipo_label="Propuesta registrada",
                ),
                "_sort": 0,
            }
        )

    for movimiento in pagos:
        propuesta = movimiento.propuesta
        eventos_por_fecha[movimiento.fecha].append(
            {
                **_base_evento_propuesta(
                    propuesta,
                    tipo_evento="pago",
                    tipo_label="Pago realizado",
                    monto_evento=movimiento.monto,
                ),
                "_sort": 1,
            }
        )

    for movimiento in vencimientos:
        propuesta = movimiento.propuesta
        eventos_por_fecha[movimiento.factura_fecha_vencimiento].append(
            {
                **_base_evento_propuesta(
                    propuesta,
                    tipo_evento="vencimiento",
                    tipo_label="Vence crédito",
                    monto_evento=movimiento.monto,
                ),
                "_sort": 2,
            }
        )

    for fecha, eventos in eventos_por_fecha.items():
        eventos.sort(
            key=lambda item: (
                item["_sort"],
                item["empresa_nombre"].lower(),
                item["propuesta_id"],
            )
        )
        for evento in eventos:
            evento.pop("_sort", None)

    ingresos_mes = sum((mov.monto or Decimal("0.00") for mov in pagos), Decimal("0.00"))
    deuda_mes = sum((mov.monto or Decimal("0.00") for mov in vencimientos), Decimal("0.00"))

    pagos_cf = [
        mov for mov in pagos
        if mov.propuesta.tipo_propuesta == Propuesta.TipoPropuesta.CARTA_FIANZA
    ]
    pagos_fd = [
        mov for mov in pagos
        if mov.propuesta.tipo_propuesta == Propuesta.TipoPropuesta.FIDEICOMISO
    ]

    vencimientos_cf = [
        mov for mov in vencimientos
        if mov.propuesta.tipo_propuesta == Propuesta.TipoPropuesta.CARTA_FIANZA
    ]
    vencimientos_fd = [
        mov for mov in vencimientos
        if mov.propuesta.tipo_propuesta == Propuesta.TipoPropuesta.FIDEICOMISO
    ]

    ingresos_cf_mes = sum((mov.monto or Decimal("0.00") for mov in pagos_cf), Decimal("0.00"))
    ingresos_fd_mes = sum((mov.monto or Decimal("0.00") for mov in pagos_fd), Decimal("0.00"))

    deuda_cf_mes = sum((mov.monto or Decimal("0.00") for mov in vencimientos_cf), Decimal("0.00"))
    deuda_fd_mes = sum((mov.monto or Decimal("0.00") for mov in vencimientos_fd), Decimal("0.00"))

    return {
        "month_start": month_start,
        "month_end": month_end,
        "eventos_por_fecha": eventos_por_fecha,
        "ingresos_mes": ingresos_mes,
        "deuda_mes": deuda_mes,
        "ingresos_cf_mes": ingresos_cf_mes,
        "deuda_cf_mes": deuda_cf_mes,
        "ingresos_fd_mes": ingresos_fd_mes,
        "deuda_fd_mes": deuda_fd_mes,
        "cantidad_propuestas": len(propuestas),
        "cantidad_pagos": len(pagos),
        "cantidad_vencimientos": len(vencimientos),
    }

def serialize_empresa(empresa: Empresa) -> dict:
    nombre = getattr(empresa, "nombre_consorcio", "") or getattr(empresa, "nombre", "") or ""
    return {
        "id": empresa.id,
        "label": f"{nombre} - {getattr(empresa, 'ruc', '')}".strip(" -"),
        "nombre": nombre,
        "ruc": getattr(empresa, "ruc", "") or "",
        "es_consorcio": bool(getattr(empresa, "es_consorcio", False)),
        "representante_legal": getattr(empresa, "representante_legal", "") or "",
        "dni_representante": getattr(empresa, "dni_representante", "") or "",
    }


def serialize_carta_fianza(carta: CartaFianza) -> dict:
    aseguradora = getattr(carta, "aseguradora", "") or ""
    if aseguradora == "OTROS" and getattr(carta, "aseguradora_otro", ""):
        aseguradora = carta.aseguradora_otro

    empresa_nombre = ""
    empresa = getattr(carta, "empresa", None)
    if empresa:
        empresa_nombre = getattr(empresa, "nombre_consorcio", "") or getattr(empresa, "nombre", "") or ""

    return {
        "id": carta.id,
        "label": f"{getattr(carta, 'numero_fianza', '')} - {aseguradora} - {getattr(carta, 'entidad', '')}".strip(" -"),
        "numero_fianza": getattr(carta, "numero_fianza", "") or "",
        "aseguradora": aseguradora,
        "tipo_carta": getattr(carta, "tipo_carta", "") or "",
        "monto": str(getattr(carta, "monto", "") or ""),
        "entidad": getattr(carta, "entidad", "") or "",
        "empresa": empresa_nombre,
    }


def serialize_fideicomiso(fideicomiso: Fideicomiso) -> dict:
    empresa_nombre = ""
    empresa = getattr(fideicomiso, "empresa", None)
    if empresa:
        empresa_nombre = getattr(empresa, "nombre_consorcio", "") or getattr(empresa, "nombre", "") or ""

    return {
        "id": fideicomiso.id,
        "label": " - ".join(
            [
                x
                for x in [
                    getattr(fideicomiso, "fiduciaria", "") or "",
                    getattr(fideicomiso, "ejecutora", "") or "",
                    getattr(fideicomiso, "representante", "") or "",
                ]
                if x
            ]
        ),
        "fiduciaria": getattr(fideicomiso, "fiduciaria", "") or "",
        "ejecutora": getattr(fideicomiso, "ejecutora", "") or "",
        "representante": getattr(fideicomiso, "representante", "") or "",
        "residente": getattr(fideicomiso, "residente", "") or "",
        "estado": getattr(fideicomiso, "estado", "") or "",
        "empresa": empresa_nombre,
    }