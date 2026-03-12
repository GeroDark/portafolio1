from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    BuscarPropuestasForm,
    PropuestaCFForm,
    PropuestaDocumentoForm,
    PropuestaFDForm,
)
from .formsets import (
    PropuestaMovimientoPagoFormSet,
    PropuestaRelacionCartaFianzaFormSet,
    PropuestaRelacionFideicomisoFormSet,
)
from .models import Propuesta, PropuestaDocumento
from .permissions import propuestas_access_required, propuestas_manage_required
from .selectors import (
    buscar_cartas_fianza,
    buscar_empresas_para_propuestas,
    buscar_fideicomisos,
    propuestas_cf_por_empresa,
    propuestas_fd_por_empresa,
    propuestas_por_empresa,
    serialize_carta_fianza,
    serialize_empresa,
    serialize_fideicomiso,
)
from .services import (
    recalculate_propuesta_totals,
    reorder_movimientos,
    reorder_relaciones_cartas,
    reorder_relaciones_fideicomisos,
    soft_delete_propuesta,
)


def _get_propuesta_or_404(pk: int) -> Propuesta:
    return get_object_or_404(
        Propuesta.objects.activos()
        .select_related("empresa", "creado_por", "actualizado_por")
        .prefetch_related(
            "relaciones_cartas__carta_fianza",
            "relaciones_fideicomisos__fideicomiso",
            "movimientos__documentos",
            "documentos",
        ),
        pk=pk,
    )


def _base_context():
    return {
        "modulo_activo": "propuestas",
    }


@propuestas_access_required
def buscar_propuestas(request):
    form = BuscarPropuestasForm(request.GET or None)

    empresa = None
    empresas_resultado = []
    propuestas = Propuesta.objects.none()
    propuestas_cf = Propuesta.objects.none()
    propuestas_fd = Propuesta.objects.none()

    q = (request.GET.get("q") or "").strip()
    empresa_id = request.GET.get("empresa")

    if form.is_valid():
        empresa = form.cleaned_data.get("empresa")

        if empresa:
            propuestas = propuestas_por_empresa(empresa.id)
            propuestas_cf = propuestas_cf_por_empresa(empresa.id)
            propuestas_fd = propuestas_fd_por_empresa(empresa.id)
        elif q:
            empresas_resultado = buscar_empresas_para_propuestas(q, limit=20)

    context = {
        **_base_context(),
        "form": form,
        "empresa": empresa,
        "empresas_resultado": empresas_resultado,
        "propuestas": propuestas,
        "propuestas_cf": propuestas_cf,
        "propuestas_fd": propuestas_fd,
        "q": q,
        "empresa_id": empresa_id,
    }
    return render(request, "propuestas/buscar_propuestas.html", context)


def _build_create_forms(request, tipo_propuesta: str):
    if tipo_propuesta == Propuesta.TipoPropuesta.CARTA_FIANZA:
        propuesta_form_class = PropuestaCFForm
        relacion_formset_class = PropuestaRelacionCartaFianzaFormSet
        template_title = "Nueva propuesta de Carta Fianza"
    else:
        propuesta_form_class = PropuestaFDForm
        relacion_formset_class = PropuestaRelacionFideicomisoFormSet
        template_title = "Nueva propuesta de Fideicomiso"

    propuesta_seed = Propuesta(tipo_propuesta=tipo_propuesta)

    if request.method == "POST":
        propuesta_form = propuesta_form_class(
            request.POST,
            instance=propuesta_seed,
            request_user=request.user,
        )

        if propuesta_form.is_valid():
            propuesta_instance = propuesta_form.save(commit=False)

            relacion_formset = relacion_formset_class(
                request.POST,
                instance=propuesta_instance,
                prefix="rel",
            )
            movimientos_formset = PropuestaMovimientoPagoFormSet(
                request.POST,
                instance=propuesta_instance,
                prefix="mov",
            )
        else:
            relacion_formset = relacion_formset_class(
                request.POST,
                instance=propuesta_seed,
                prefix="rel",
            )
            movimientos_formset = PropuestaMovimientoPagoFormSet(
                request.POST,
                instance=propuesta_seed,
                prefix="mov",
            )
    else:
        propuesta_form = propuesta_form_class(
            instance=propuesta_seed,
            request_user=request.user,
        )
        relacion_formset = relacion_formset_class(
            instance=propuesta_seed,
            prefix="rel",
        )
        movimientos_formset = PropuestaMovimientoPagoFormSet(
            instance=propuesta_seed,
            prefix="mov",
        )

    return propuesta_form, relacion_formset, movimientos_formset, template_title


def _save_create_flow(
    request,
    propuesta_form,
    relacion_formset,
    movimientos_formset,
    tipo_propuesta: str,
):
    if not propuesta_form.is_valid():
        return None

    propuesta = propuesta_form.save(commit=False)

    relacion_formset = relacion_formset.__class__(
        request.POST,
        instance=propuesta,
        prefix=relacion_formset.prefix,
    )
    movimientos_formset = movimientos_formset.__class__(
        request.POST,
        instance=propuesta,
        prefix=movimientos_formset.prefix,
    )

    if not (relacion_formset.is_valid() and movimientos_formset.is_valid()):
        return propuesta, relacion_formset, movimientos_formset

    with transaction.atomic():
        propuesta.save()

        relacion_formset.instance = propuesta
        movimientos_formset.instance = propuesta

        relacion_formset.save()
        movimientos_formset.save()

        if tipo_propuesta == Propuesta.TipoPropuesta.CARTA_FIANZA:
            reorder_relaciones_cartas(propuesta)
        else:
            reorder_relaciones_fideicomisos(propuesta)

        reorder_movimientos(propuesta)
        recalculate_propuesta_totals(propuesta, save=True)

    messages.success(request, "La propuesta fue creada correctamente.")
    return redirect("propuestas:detalle", pk=propuesta.pk)


@propuestas_manage_required
def crear_propuesta_cf(request):
    propuesta_form, relacion_formset, movimientos_formset, template_title = _build_create_forms(
        request,
        Propuesta.TipoPropuesta.CARTA_FIANZA,
    )

    if request.method == "POST":
        result = _save_create_flow(
            request,
            propuesta_form,
            relacion_formset,
            movimientos_formset,
            Propuesta.TipoPropuesta.CARTA_FIANZA,
        )
        if hasattr(result, "status_code"):
            return result
        if result is not None:
            _, relacion_formset, movimientos_formset = result

    context = {
        **_base_context(),
        "form": propuesta_form,
        "relacion_formset": relacion_formset,
        "movimientos_formset": movimientos_formset,
        "modo": "crear",
        "tipo_propuesta": Propuesta.TipoPropuesta.CARTA_FIANZA,
        "titulo": template_title,
    }
    return render(request, "propuestas/propuesta_form.html", context)


@propuestas_manage_required
def crear_propuesta_fd(request):
    propuesta_form, relacion_formset, movimientos_formset, template_title = _build_create_forms(
        request,
        Propuesta.TipoPropuesta.FIDEICOMISO,
    )

    if request.method == "POST":
        result = _save_create_flow(
            request,
            propuesta_form,
            relacion_formset,
            movimientos_formset,
            Propuesta.TipoPropuesta.FIDEICOMISO,
        )
        if hasattr(result, "status_code"):
            return result
        if result is not None:
            _, relacion_formset, movimientos_formset = result

    context = {
        **_base_context(),
        "form": propuesta_form,
        "relacion_formset": relacion_formset,
        "movimientos_formset": movimientos_formset,
        "modo": "crear",
        "tipo_propuesta": Propuesta.TipoPropuesta.FIDEICOMISO,
        "titulo": template_title,
    }
    return render(request, "propuestas/propuesta_form.html", context)


@propuestas_access_required
def detalle_propuesta(request, pk):
    propuesta = _get_propuesta_or_404(pk)

    documentos_generales = propuesta.documentos.filter(
        categoria=PropuestaDocumento.Categoria.PROPUESTA_GENERAL
    ).order_by("-uploaded_at")
    movimientos = propuesta.movimientos.all().order_by("fecha", "orden", "id")

    context = {
        **_base_context(),
        "propuesta": propuesta,
        "documentos_generales": documentos_generales,
        "movimientos": movimientos,
        "upload_form": PropuestaDocumentoForm(propuesta=propuesta),
    }
    return render(request, "propuestas/propuesta_detail.html", context)


@propuestas_manage_required
def editar_propuesta(request, pk):
    propuesta = _get_propuesta_or_404(pk)

    if propuesta.tipo_propuesta == Propuesta.TipoPropuesta.CARTA_FIANZA:
        propuesta_form_class = PropuestaCFForm
        relacion_formset_class = PropuestaRelacionCartaFianzaFormSet
    else:
        propuesta_form_class = PropuestaFDForm
        relacion_formset_class = PropuestaRelacionFideicomisoFormSet

    if request.method == "POST":
        propuesta_form = propuesta_form_class(
            request.POST,
            instance=propuesta,
            request_user=request.user,
        )
        relacion_formset = relacion_formset_class(
            request.POST,
            instance=propuesta,
            prefix="rel",
        )
        movimientos_formset = PropuestaMovimientoPagoFormSet(
            request.POST,
            instance=propuesta,
            prefix="mov",
        )

        if (
            propuesta_form.is_valid()
            and relacion_formset.is_valid()
            and movimientos_formset.is_valid()
        ):
            with transaction.atomic():
                propuesta = propuesta_form.save(commit=True)

                relacion_formset.instance = propuesta
                movimientos_formset.instance = propuesta

                relacion_formset.save()
                movimientos_formset.save()

                if propuesta.tipo_propuesta == Propuesta.TipoPropuesta.CARTA_FIANZA:
                    reorder_relaciones_cartas(propuesta)
                else:
                    reorder_relaciones_fideicomisos(propuesta)

                reorder_movimientos(propuesta)
                recalculate_propuesta_totals(propuesta, save=True)

            messages.success(request, "La propuesta fue actualizada correctamente.")
            return redirect("propuestas:detalle", pk=propuesta.pk)
    else:
        propuesta_form = propuesta_form_class(
            instance=propuesta,
            request_user=request.user,
        )
        relacion_formset = relacion_formset_class(
            instance=propuesta,
            prefix="rel",
        )
        movimientos_formset = PropuestaMovimientoPagoFormSet(
            instance=propuesta,
            prefix="mov",
        )

    context = {
        **_base_context(),
        "form": propuesta_form,
        "relacion_formset": relacion_formset,
        "movimientos_formset": movimientos_formset,
        "propuesta": propuesta,
        "modo": "editar",
        "tipo_propuesta": propuesta.tipo_propuesta,
        "titulo": f"Editar {propuesta.codigo}",
    }
    return render(request, "propuestas/propuesta_form.html", context)


@propuestas_manage_required
def eliminar_propuesta(request, pk):
    propuesta = _get_propuesta_or_404(pk)

    if request.method == "POST":
        soft_delete_propuesta(propuesta, user=request.user)
        messages.success(request, "La propuesta fue eliminada correctamente.")
        return redirect("propuestas:buscar")

    context = {
        **_base_context(),
        "propuesta": propuesta,
    }
    return render(request, "propuestas/propuesta_confirm_delete.html", context)


@propuestas_access_required
def ajax_buscar_empresas(request):
    q = (request.GET.get("q") or request.GET.get("term") or "").strip()
    resultados = buscar_empresas_para_propuestas(q, limit=20)
    return JsonResponse(
        {
            "results": [serialize_empresa(item) for item in resultados],
        }
    )


@propuestas_access_required
def ajax_buscar_cartas_fianza(request):
    q = (request.GET.get("q") or request.GET.get("term") or "").strip()
    resultados = buscar_cartas_fianza(q, limit=20)
    return JsonResponse(
        {
            "results": [serialize_carta_fianza(item) for item in resultados],
        }
    )


@propuestas_access_required
def ajax_buscar_fideicomisos(request):
    q = (request.GET.get("q") or request.GET.get("term") or "").strip()
    resultados = buscar_fideicomisos(q, limit=20)
    return JsonResponse(
        {
            "results": [serialize_fideicomiso(item) for item in resultados],
        }
    )


@propuestas_manage_required
def subir_documento_propuesta(request, pk):
    propuesta = _get_propuesta_or_404(pk)

    if request.method != "POST":
        raise Http404()

    movimiento = None
    movimiento_id = request.POST.get("movimiento_id")
    if movimiento_id:
        movimiento = propuesta.movimientos.filter(pk=movimiento_id).first()

    form = PropuestaDocumentoForm(
        request.POST,
        request.FILES,
        propuesta=propuesta,
        movimiento=movimiento,
    )

    if form.is_valid():
        form.save(user=request.user)
        messages.success(request, "Documento subido correctamente.")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field}: {error}")

    return redirect("propuestas:detalle", pk=propuesta.pk)


@propuestas_manage_required
def eliminar_documento_propuesta(request, pk, doc_id):
    propuesta = _get_propuesta_or_404(pk)
    documento = get_object_or_404(PropuestaDocumento, pk=doc_id, propuesta=propuesta)

    if request.method == "POST":
        if documento.archivo:
            documento.archivo.delete(save=False)
        documento.delete()
        messages.success(request, "Documento eliminado correctamente.")
        return redirect("propuestas:detalle", pk=propuesta.pk)

    return redirect("propuestas:detalle", pk=propuesta.pk)