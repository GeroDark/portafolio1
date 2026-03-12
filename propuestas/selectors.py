from __future__ import annotations

from django.db.models import Q

from empresas.models import CartaFianza, Empresa, Fideicomiso

from .models import Propuesta


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


def buscar_cartas_fianza(query: str, limit: int = 20):
    qs = CartaFianza.objects.select_related("empresa").all()

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

    return qs.order_by("-id")[:limit]


def buscar_fideicomisos(query: str, limit: int = 20):
    qs = Fideicomiso.objects.select_related("empresa").all()

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

    return qs.order_by("-id")[:limit]


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