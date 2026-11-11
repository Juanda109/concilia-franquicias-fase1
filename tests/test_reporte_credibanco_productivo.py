from app.services.fase2.reporte_credibanco_productivo import construir


def base():
    return {
        "id_jornada": 2590,
        "fecha_contable": "2026-10-23",
        "certificado": False,
        "totales_diagnosticos": [
            {"A": "017-CANJE RECIBIDO TARJETA CREDITO PAGOS", "B": 4, "C": "219.00", "D": "398.00"},
            {"A": "017-ORIGINAL REEMBOLSOS CREDITO", "B": 3, "C": "117.00", "D": "219.00"},
            {"A": "017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES", "B": 2, "C": "80.00", "D": "100.00"},
            {"A": "017-ORIGINAL REEMBOLSOS DEBITO", "B": 1, "C": "50.00", "D": "70.00"},
            {"A": "017-REPRESENTACION  VENTA NAL (CENTRO 730)", "B": 5, "C": "20.00", "D": "30.00"},
            {"A": "017-COMISIONES NO EXITOSAS TD Y TC IMPUTABLES BANCO", "B": 2, "C": "8.00", "D": "9.00"},
        ],
        "host_por_cuenta_y_fuente": [
            {"cuenta": "299095302", "fuente": "HA22", "debe": "100", "haber": "0", "cantidad": 4, "sinteticos": True},
            {"cuenta": "299095302", "fuente": "HA26", "debe": "101", "haber": "0", "cantidad": 4, "sinteticos": True},
            {"cuenta": "299095302", "fuente": "HA32", "debe": "101", "haber": "0", "cantidad": 4, "sinteticos": True},
        ],
        "depo_agregados_crudos": [
            {"concepto": "017-VR. DEPOSITOS ELECTRONICOS NAL CONSIGNADOS", "valor_total_crudo": "219894"}
        ],
        "control_canje_carta": {"L3_comisiones_canje": {}, "L5_carta_componente_G": {}, "L6_evidencia": {}},
        "carta_posicion_neta": {},
        "pendientes": [],
        "cruces_host_credibanco_diagnosticos": [],
    }


def catalogo_test():
    return {
        "reglas": [
            {"concepto": "017-CANJE RECIBIDO TARJETA CREDITO PAGOS", "cuenta": "299095302", "fila": 58, "formula_G": "x"},
            {"concepto": "017-ORIGINAL REEMBOLSOS CREDITO", "cuenta": "299095302", "fila": 60, "formula_G": "x"},
            {"concepto": "017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES", "cuenta": "299095301", "fila": 67, "formula_G": "x"},
            {"concepto": "017-ORIGINAL REEMBOLSOS DEBITO", "cuenta": "299095301", "fila": 69, "formula_G": "x"},
            {"concepto": "017-REPRESENTACION  VENTA NAL (CENTRO 730)", "cuenta": "299095038", "fila": 80, "formula_F": "x"},
            {"concepto": "017-COMISIONES NO EXITOSAS TD Y TC IMPUTABLES BANCO", "cuenta": "299095843", "fila": 92, "formula_F": "x"},
        ]
    }

def test_construye_matriz_documentada_sin_certificar():
    salida = construir(base(), catalogo_test())
    assert salida["estado"] == "CONCILIACION_OPERATIVA_PENDIENTE_HOMOLOGACION"
    assert salida["certificado"] is False
    assert len(salida["filas"]) == 8
    assert salida["resumen"]["cruces_homologados"] == 0
    assert all(f["total_host_homologado"] is None for f in salida["filas"])


def test_host_neto_no_suma_fuentes():
    salida = construir(base(), catalogo_test())
    fila = next(f for f in salida["filas"] if f["cuenta"] == "299095302")
    assert fila["ha22_neto"] == "100"
    assert fila["ha26_neto"] == "101"
    assert fila["ha32_neto"] == "101"
    assert fila["total_host_homologado"] is None


def test_expone_vl_total_y_vl_interc_separados_y_depo_intercambio():
    informe = base()
    informe["totales_diagnosticos"][0]["C"] = "219.00"
    informe["totales_diagnosticos"][0]["D"] = "398.00"
    informe["depo_agregados_crudos"].append({
        "concepto": "017-VR. DEPOSITOS ELECTRONICOS NAL CONSIGNADOS",
        "cantidad": 2,
        "valor_total_crudo": "1000.00",
        "valor_intercambio_crudo": "700.00",
    })
    salida = construir(informe, catalogo_test())
    canje = next(f for f in salida["filas"] if f["concepto"] == "017-CANJE RECIBIDO TARJETA CREDITO PAGOS")
    depo = next(f for f in salida["filas"] if f["insumo"] == "DEPO")
    assert canje["cantidad_operaciones"] == 4
    assert canje["vl_total"] == "398.00"
    assert canje["vl_interc"] == "219.00"
    assert canje["valor_origen"] == "4"
    assert depo["vl_total"] == "220894.00"
    assert depo["vl_interc"] == "700.00"
    assert depo["cantidad_operaciones"] == 2
    assert depo["total_host_homologado"] is None
    assert depo["diferencia_homologada"] is None


def test_totales_origen_acepta_clave_base_persistida_y_conserva_monetarios():
    informe = base()
    informe["totales_diagnosticos"] = [
        {
            "A": "017-CANJE RECIBIDO TARJETA CREDITO",
            "B": 8,
            "C": "0.0000",
            "D": "23494500.0000",
        }
    ]
    salida = construir(informe, catalogo_test())
    fila = next(f for f in salida["filas"] if f["fila_plantilla"] == 58)
    assert fila["cantidad_operaciones"] == 8
    assert fila["vl_interc"] == "0.0000"
    assert fila["vl_total"] == "23494500.0000"
    assert fila["valor_origen"] == "8"
    assert fila["unidad_origen"] == "CANTIDAD_OPERACIONES"


def test_totales_origen_no_asigna_base_a_otros_conceptos():
    informe = base()
    informe["totales_diagnosticos"] = [
        {
            "A": "017-CANJE RECIBIDO TARJETA CREDITO",
            "B": 8,
            "C": "0.0000",
            "D": "23494500.0000",
        }
    ]
    salida = construir(informe, catalogo_test())
    fila = next(f for f in salida["filas"] if f["fila_plantilla"] == 60)
    assert fila["cantidad_operaciones"] == 0
    assert fila["vl_total"] == "0.0000"
    assert fila["vl_interc"] == "0.0000"


def test_vlookup_sin_coincidencia_devuelve_cero_funcional():
    informe = base()
    informe["totales_diagnosticos"] = []
    salida = construir(informe, catalogo_test())
    filas = {f["concepto"]: f for f in salida["filas"]}
    assert filas["017-ORIGINAL REEMBOLSOS CREDITO"]["valor_origen"] == "0.0000"
    assert filas["017-ORIGINAL REEMBOLSOS CREDITO"]["vl_total"] == "0.0000"
    assert filas["017-ORIGINAL REEMBOLSOS CREDITO"]["vl_interc"] == "0.0000"
    assert filas["017-CANJE RECIBIDO TARJETA CREDITO PAGOS"]["estado_conciliacion"] == "PENDIENTE_HOMOLOGACION"
