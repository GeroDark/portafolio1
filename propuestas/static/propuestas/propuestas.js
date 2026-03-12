document.addEventListener("DOMContentLoaded", function () {
    function q(selector, root = document) {
        return root.querySelector(selector);
    }

    function qa(selector, root = document) {
        return Array.from(root.querySelectorAll(selector));
    }

    function getFieldBySuffix(suffix, root = document) {
        return q(`[name$="${suffix}"]`, root);
    }

    function getAllFieldsBySuffix(suffix, root = document) {
        return qa(`[name$="${suffix}"]`, root);
    }

    function parseDecimal(value) {
        if (value === null || value === undefined) return 0;
        const normalized = String(value).replace(",", ".").trim();
        const parsed = parseFloat(normalized);
        return isNaN(parsed) ? 0 : parsed;
    }

    function formatMoney(value) {
        return Number(value || 0).toFixed(2);
    }

    function setText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    }

    function toggleElement(el, show) {
        if (!el) return;
        el.classList.toggle("is-hidden", !show);
    }

    function updateCuentaOtroVisibility() {
        const cuentaSelect = getFieldBySuffix("-comision_cuenta");
        const wrapper = document.getElementById("comision-cuenta-otro-wrapper");
        if (!cuentaSelect || !wrapper) return;

        toggleElement(wrapper, cuentaSelect.value === "OTROS");
    }

    function updateMovimientoVisibility(movimientoItem) {
        if (!movimientoItem) return;

        const tipoComprobante = getFieldBySuffix("-tipo_comprobante", movimientoItem);
        const facturaModalidad = getFieldBySuffix("-factura_modalidad", movimientoItem);

        const rhBlock = q(".comprobante-rh-fields", movimientoItem);
        const facturaBlock = q(".comprobante-factura-fields", movimientoItem);
        const creditoBlocks = qa(".factura-credito-fields", movimientoItem);

        const isRH = tipoComprobante && tipoComprobante.value === "RH";
        const isFactura = tipoComprobante && tipoComprobante.value === "FACTURA";
        const isCredito = isFactura && facturaModalidad && facturaModalidad.value === "credito";

        toggleElement(rhBlock, isRH);
        toggleElement(facturaBlock, isFactura);

        creditoBlocks.forEach((block) => toggleElement(block, isCredito));
    }

    function bindMovimientoEvents(movimientoItem) {
        if (!movimientoItem || movimientoItem.dataset.bound === "1") return;

        const tipoComprobante = getFieldBySuffix("-tipo_comprobante", movimientoItem);
        const facturaModalidad = getFieldBySuffix("-factura_modalidad", movimientoItem);
        const montoField = getFieldBySuffix("-monto", movimientoItem);
        const tipoMovimientoField = getFieldBySuffix("-tipo_movimiento", movimientoItem);
        const deleteField = getFieldBySuffix("-DELETE", movimientoItem);

        if (tipoComprobante) {
            tipoComprobante.addEventListener("change", function () {
                updateMovimientoVisibility(movimientoItem);
            });
        }

        if (facturaModalidad) {
            facturaModalidad.addEventListener("change", function () {
                updateMovimientoVisibility(movimientoItem);
            });
        }

        [montoField, tipoMovimientoField, deleteField].forEach((field) => {
            if (field) {
                field.addEventListener("input", updateResumen);
                field.addEventListener("change", updateResumen);
            }
        });

        updateMovimientoVisibility(movimientoItem);
        movimientoItem.dataset.bound = "1";
    }

    function initMovimientos() {
        qa(".movimiento-item").forEach(bindMovimientoEvents);
        updateResumen();
    }

    function updateResumen() {
        const montoTotalField = getFieldBySuffix("-monto_total");
        const montoTotal = parseDecimal(montoTotalField ? montoTotalField.value : 0);

        let totalAdelantado = 0;
        let totalCancelado = 0;

        qa(".movimiento-item").forEach((item) => {
            const deleteField = getFieldBySuffix("-DELETE", item);
            if (deleteField && deleteField.checked) return;

            const montoField = getFieldBySuffix("-monto", item);
            const tipoMovimientoField = getFieldBySuffix("-tipo_movimiento", item);

            const monto = parseDecimal(montoField ? montoField.value : 0);
            const tipoMovimiento = tipoMovimientoField ? tipoMovimientoField.value : "";

            if (tipoMovimiento === "adelanto") {
                totalAdelantado += monto;
            } else if (tipoMovimiento === "cancelacion") {
                totalCancelado += monto;
            }
        });

        const totalPagado = totalAdelantado + totalCancelado;
        const saldoPendiente = Math.max(0, montoTotal - totalPagado);

        let estado = "Pendiente";
        if (totalPagado === 0) {
            estado = "Pendiente";
        } else if (saldoPendiente === 0 && totalCancelado > 0) {
            estado = "Cancelada";
        } else {
            estado = "Con adelantos";
        }

        setText("resumen-monto-total", formatMoney(montoTotal));
        setText("resumen-total-adelantado", formatMoney(totalAdelantado));
        setText("resumen-total-cancelado", formatMoney(totalCancelado));
        setText("resumen-total-pagado", formatMoney(totalPagado));
        setText("resumen-saldo-pendiente", formatMoney(saldoPendiente));
        setText("resumen-estado", estado);
    }

    function replacePrefix(html, prefix, index) {
        const regex = new RegExp(`${prefix}-__prefix__-`, "g");
        return html.replace(regex, `${prefix}-${index}-`);
    }

    function updateTotalForms(prefix, newValue) {
        const totalFormsInput = document.getElementById(`id_${prefix}-TOTAL_FORMS`);
        if (totalFormsInput) {
            totalFormsInput.value = String(newValue);
        }
    }

    function getTotalForms(prefix) {
        const totalFormsInput = document.getElementById(`id_${prefix}-TOTAL_FORMS`);
        return totalFormsInput ? parseInt(totalFormsInput.value, 10) || 0 : 0;
    }

    function addFormsetItem(prefix) {
        const container = document.getElementById(`${prefix}-formset-container`);
        const template = document.getElementById(`${prefix}-empty-form-template`);

        if (!container || !template) return;

        const index = getTotalForms(prefix);
        const html = replacePrefix(template.innerHTML, prefix, index);

        const temp = document.createElement("div");
        temp.innerHTML = html.trim();

        const newItem = temp.firstElementChild;
        if (!newItem) return;

        container.appendChild(newItem);
        updateTotalForms(prefix, index + 1);

        if (prefix === "mov") {
            bindMovimientoEvents(newItem);
            updateResumen();
        }
    }

    function bindAddFormsetButtons() {
        qa("[data-add-formset]").forEach((button) => {
            button.addEventListener("click", function () {
                const prefix = this.getAttribute("data-add-formset");
                addFormsetItem(prefix);
            });
        });
    }

    function bindResumenBaseEvents() {
        const montoTotalField = getFieldBySuffix("-monto_total");
        const cuentaSelect = getFieldBySuffix("-comision_cuenta");

        if (montoTotalField) {
            montoTotalField.addEventListener("input", updateResumen);
            montoTotalField.addEventListener("change", updateResumen);
        }

        if (cuentaSelect) {
            cuentaSelect.addEventListener("change", updateCuentaOtroVisibility);
        }
    }

    bindAddFormsetButtons();
    bindResumenBaseEvents();
    initMovimientos();
    updateCuentaOtroVisibility();
    updateResumen();
});