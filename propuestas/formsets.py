from django.forms import BaseInlineFormSet, inlineformset_factory
from django import forms
from .forms import (
    PropuestaMovimientoPagoForm,
    PropuestaRelacionCartaFianzaForm,
    PropuestaRelacionFideicomisoForm,
)
from .models import (
    Propuesta,
    PropuestaMovimientoPago,
    PropuestaRelacionCartaFianza,
    PropuestaRelacionFideicomiso,
)


class BasePropuestaRelacionCartaFianzaFormSet(BaseInlineFormSet):
    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["propuesta"] = self.instance
        return kwargs

    def clean(self):
        super().clean()

        if not self.instance:
            return

        if self.instance.tipo_propuesta != Propuesta.TipoPropuesta.CARTA_FIANZA:
            return

        activos = 0
        repetidos = set()

        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if form.cleaned_data.get("DELETE"):
                continue
            carta = form.cleaned_data.get("carta_fianza")
            if not carta:
                continue

            activos += 1

            if carta.pk in repetidos:
                form.add_error("carta_fianza", "Esta carta fianza está repetida en la propuesta.")
            repetidos.add(carta.pk)

        # Solo exigimos al menos una relación cuando la propuesta ya está siendo guardada como CF
        if self.instance.tipo_propuesta == Propuesta.TipoPropuesta.CARTA_FIANZA and activos == 0:
            raise forms.ValidationError("Debes agregar al menos una carta fianza a la propuesta.")


class BasePropuestaRelacionFideicomisoFormSet(BaseInlineFormSet):
    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["propuesta"] = self.instance
        return kwargs

    def clean(self):
        super().clean()

        if not self.instance:
            return

        if self.instance.tipo_propuesta != Propuesta.TipoPropuesta.FIDEICOMISO:
            return

        activos = 0
        repetidos = set()

        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if form.cleaned_data.get("DELETE"):
                continue
            fideicomiso = form.cleaned_data.get("fideicomiso")
            if not fideicomiso:
                continue

            activos += 1

            if fideicomiso.pk in repetidos:
                form.add_error("fideicomiso", "Este fideicomiso está repetido en la propuesta.")
            repetidos.add(fideicomiso.pk)

        if self.instance.tipo_propuesta == Propuesta.TipoPropuesta.FIDEICOMISO and activos == 0:
            raise forms.ValidationError("Debes agregar al menos un fideicomiso a la propuesta.")


class BasePropuestaMovimientoPagoFormSet(BaseInlineFormSet):
    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["propuesta"] = self.instance
        return kwargs

    def clean(self):
        super().clean()

        if not self.instance:
            return

        total = 0
        cancelaciones = 0

        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if form.cleaned_data.get("DELETE"):
                continue

            monto = form.cleaned_data.get("monto") or 0
            tipo_movimiento = form.cleaned_data.get("tipo_movimiento")

            total += monto

            if tipo_movimiento == PropuestaMovimientoPago.TipoMovimiento.CANCELACION:
                cancelaciones += 1

        if total > self.instance.monto_total:
            raise forms.ValidationError("La suma de movimientos no puede superar el monto total de la propuesta.")

        if cancelaciones > 1:
            raise forms.ValidationError("Solo puede existir una cancelación por propuesta.")


PropuestaRelacionCartaFianzaFormSet = inlineformset_factory(
    Propuesta,
    PropuestaRelacionCartaFianza,
    form=PropuestaRelacionCartaFianzaForm,
    formset=BasePropuestaRelacionCartaFianzaFormSet,
    extra=1,
    can_delete=True,
)

PropuestaRelacionFideicomisoFormSet = inlineformset_factory(
    Propuesta,
    PropuestaRelacionFideicomiso,
    form=PropuestaRelacionFideicomisoForm,
    formset=BasePropuestaRelacionFideicomisoFormSet,
    extra=1,
    can_delete=True,
)

PropuestaMovimientoPagoFormSet = inlineformset_factory(
    Propuesta,
    PropuestaMovimientoPago,
    form=PropuestaMovimientoPagoForm,
    formset=BasePropuestaMovimientoPagoFormSet,
    extra=1,
    can_delete=True,
)