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

        const raw = String(value).trim();
        if (!raw) return 0;

        let normalized = raw;

        if (raw.includes(",") && raw.includes(".")) {
            normalized = raw.replace(/\./g, "").replace(",", ".");
        } else if (raw.includes(",")) {
            normalized = raw.replace(",", ".");
        }

        const parsed = parseFloat(normalized);
        return Number.isFinite(parsed) ? parsed : 0;
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
        const cuentaSelect = document.getElementById("id_comision_cuenta");
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
        const montoTotalField = document.getElementById("id_monto_total");
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
        if (totalPagado <= 0) {
            estado = "Pendiente";
        } else if (montoTotal > 0 && totalPagado >= montoTotal) {
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
        const montoTotalField = document.getElementById("id_monto_total");
        const cuentaSelect = document.getElementById("id_comision_cuenta");
        const monedaField = document.getElementById("id_moneda");

        if (montoTotalField) {
            montoTotalField.addEventListener("input", updateResumen);
            montoTotalField.addEventListener("change", updateResumen);
        }

        if (monedaField) {
            monedaField.addEventListener("change", updateResumen);
        }

        if (cuentaSelect) {
            cuentaSelect.addEventListener("change", updateCuentaOtroVisibility);
        }
    }

    function initEmpresaAutocomplete() {
        const input = document.getElementById("empresa-search-input");
        const hiddenEmpresaId = document.getElementById("empresa-id");
        const resultsBox = document.getElementById("empresa-search-results");
        const form = document.getElementById("propuestas-search-form");

        if (!input || !hiddenEmpresaId || !resultsBox || !form) return;

        const url = input.dataset.autocompleteUrl;
        if (!url) return;

        let debounceTimer = null;
        let lastSelectedLabel = input.value.trim();

        function closeResults() {
            resultsBox.innerHTML = "";
            resultsBox.classList.add("d-none");
        }

        function renderResults(items) {
            if (!items.length) {
                resultsBox.innerHTML = `
                    <div class="propuestas-autocomplete-item">
                        <span class="propuestas-autocomplete-title">Sin coincidencias</span>
                    </div>
                `;
                resultsBox.classList.remove("d-none");
                return;
            }

            resultsBox.innerHTML = items.map((item) => {
                const meta = [
                    item.ruc ? `RUC: ${item.ruc}` : "",
                    item.es_consorcio ? "Consorcio" : "Empresa",
                    item.representante_legal ? `Representante: ${item.representante_legal}` : ""
                ].filter(Boolean).join(" · ");

                return `
                    <button type="button" class="propuestas-autocomplete-item" data-id="${item.id}" data-label="${item.nombre}">
                        <span class="propuestas-autocomplete-title">${item.nombre}</span>
                        <span class="propuestas-autocomplete-meta">${meta}</span>
                    </button>
                `;
            }).join("");

            resultsBox.classList.remove("d-none");

            resultsBox.querySelectorAll(".propuestas-autocomplete-item[data-id]").forEach((button) => {
                button.addEventListener("click", function () {
                    hiddenEmpresaId.value = this.dataset.id;
                    input.value = this.dataset.label;
                    lastSelectedLabel = this.dataset.label;
                    closeResults();
                });
            });
        }

        async function fetchResults(term) {
            try {
                const response = await fetch(`${url}?q=${encodeURIComponent(term)}`, {
                    headers: { "X-Requested-With": "XMLHttpRequest" }
                });

                if (!response.ok) {
                    closeResults();
                    return;
                }

                const data = await response.json();
                renderResults(data.results || []);
            } catch (error) {
                closeResults();
            }
        }

        input.addEventListener("input", function () {
            const term = this.value.trim();

            if (term !== lastSelectedLabel) {
                hiddenEmpresaId.value = "";
            }

            clearTimeout(debounceTimer);

            if (term.length < 2) {
                closeResults();
                return;
            }

            debounceTimer = setTimeout(() => {
                fetchResults(term);
            }, 220);
        });

        input.addEventListener("focus", function () {
            const term = this.value.trim();
            if (term.length >= 2 && !hiddenEmpresaId.value) {
                fetchResults(term);
            }
        });

        document.addEventListener("click", function (event) {
            if (!resultsBox.contains(event.target) && event.target !== input) {
                closeResults();
            }
        });

        form.addEventListener("submit", function () {
            if (hiddenEmpresaId.value) {
                return;
            }
        });
    }

    

    function renderIntegrantesConsorcio(items) {
        const wrapper = document.getElementById("consorcio-integrantes-wrapper");
        const list = document.getElementById("consorcio-integrantes-list");

        if (!wrapper || !list) return;

        list.innerHTML = "";

        const finalItems = Array.isArray(items) ? items.filter(Boolean) : [];

        if (!finalItems.length) {
            wrapper.classList.add("d-none");
            return;
        }

        finalItems.forEach((item) => {
            const li = document.createElement("li");
            li.className = "mb-1";
            li.textContent = item;
            list.appendChild(li);
        });

        wrapper.classList.remove("d-none");
    }

    function applyEmpresaDataToForm(payload) {
        const consorcioCheck = document.getElementById("id_es_consorcio_manual");
        const repField = document.getElementById("id_representante_legal_manual");
        const dniField = document.getElementById("id_dni_representante_manual");
        const facturarField = document.getElementById("id_facturador_texto");

        if (!payload) {
            renderIntegrantesConsorcio([]);
            if (facturarField) {
                facturarField.readOnly = false;
            }
            return;
        }

        const esConsorcio = Boolean(payload.es_consorcio);

        if (consorcioCheck) {
            consorcioCheck.checked = esConsorcio;
            consorcioCheck.dispatchEvent(new Event("change", { bubbles: true }));
        }

        if (repField) {
            repField.value = esConsorcio ? (payload.representante_legal || "") : "";
        }

        if (dniField) {
            dniField.value = esConsorcio ? (payload.dni_representante || "") : "";
        }

        if (facturarField) {
            if (esConsorcio) {
                facturarField.readOnly = false;
                if (facturarField.dataset.autoRuc === "1") {
                    facturarField.value = "";
                }
                facturarField.dataset.autoRuc = "0";
            } else {
                facturarField.value = payload.ruc_facturar_auto || "";
                facturarField.readOnly = true;
                facturarField.dataset.autoRuc = "1";
            }
        }

        renderIntegrantesConsorcio(payload.integrantes_consorcio_lista || []);
    }

    async function fetchEmpresaFormData(empresaId) {
        const empresaField = document.getElementById("id_empresa");
        if (!empresaField) return;

        const url = empresaField.dataset.autocompleteUrl;
        if (!url) return;

        if (!empresaId) {
            applyEmpresaDataToForm(null);
            return;
        }

        try {
            const response = await fetch(`${url}?id=${encodeURIComponent(empresaId)}`, {
                headers: { "X-Requested-With": "XMLHttpRequest" }
            });

            if (!response.ok) {
                return;
            }

            const data = await response.json();
            applyEmpresaDataToForm(data.result || null);
        } catch (error) {
            console.error("No se pudo obtener la empresa/consorcio seleccionado", error);
        }
    }

    function bindPropuestaEmpresaChange() {
        const empresaField = document.getElementById("id_empresa");
        if (!empresaField || empresaField.dataset.boundEmpresaForm === "1") return;

        empresaField.addEventListener("change", function () {
            fetchEmpresaFormData(this.value);
        });

        if (empresaField.value) {
            fetchEmpresaFormData(empresaField.value);
        }

        empresaField.dataset.boundEmpresaForm = "1";
    }

    bindAddFormsetButtons();
    bindResumenBaseEvents();
    initMovimientos();
    updateCuentaOtroVisibility();
    updateResumen();
    bindPropuestaEmpresaChange();
    initEmpresaAutocomplete();
});