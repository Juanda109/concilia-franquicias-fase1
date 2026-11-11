"""INC56-D: verificacion monetaria NO certificante y sin escritura."""
from pathlib import Path
from collections import Counter
import hashlib

# Coordenadas 1-based verificadas en Revisión campos de la plantilla.
CAMPOS = {
    "TIPO_MOVIMIENTO": (1, 2), "COD_OFICINA": (52, 4),
    "VALOR_TOTAL": (123, 9), "VALOR_INTERCAMBIO": (141, 9),
    "VALOR_INTERCAMBIO_2": (246, 9), "INDICADOR_CASH_BACK": (265, 3),
}

def campo(linea, inicio, longitud):
    return linea[inicio-1:inicio-1+longitud]

def verificar_archivo(ruta):
    ruta = Path(ruta)
    datos = ruta.read_bytes()
    lineas = datos.decode("latin-1").splitlines()
    conteo = Counter()
    problemas = []
    ejemplos = []
    for numero, linea in enumerate(lineas, 1):
        if not linea: continue
        tipo = campo(linea, *CAMPOS["TIPO_MOVIMIENTO"])
        conteo[tipo] += 1
        if len(linea) != 280:
            problemas.append({"linea": numero, "problema": "LONGITUD_DISTINTA_280", "longitud": len(linea)})
        valores = {k: campo(linea, *p).strip() for k,p in CAMPOS.items()}
        if len(ejemplos) < 8: ejemplos.append({"linea": numero, **valores})
    return {
        "archivo": ruta.name, "sha256": hashlib.sha256(datos).hexdigest(),
        "registros": sum(conteo.values()), "tipos_registro": dict(sorted(conteo.items())),
        "problemas": problemas, "ejemplos": ejemplos,
        "certificado_monetario": False,
        "estado": "PENDIENTE_ESCALA_FORMULAS_Y_CORRESPONDENCIA_CONTABLE",
        "advertencia": "No calcular Debe/Haber/Neto ni proyectar Valor Franquicia con importes crudos.",
    }

def verificar_formulas(ruta):
    from openpyxl import load_workbook
    libro = load_workbook(ruta, read_only=True, data_only=False)
    esperado = {
        "D2": ('196095001838', '"D"'),
        "D3": ('196095001838', '"H"'),
        "D4": ('196095001839', '"D"'),
        "D5": ('196095001839', '"H"'),
    }
    hoja = libro["datos contabilidad"]
    filas=[]
    for celda,(cuenta,naturaleza) in esperado.items():
        formula=str(hoja[celda].value or "")
        filas.append({"celda": celda, "formula": formula,
                      "coincide_referencia": cuenta in formula and naturaleza in formula})
    discrepancia = [c for c in ("F4","F5") if str(hoja[c].value) != "196095001839"]
    return {"formulas": filas, "referencias_auxiliares_a_revisar": discrepancia,
            "certificado_monetario": False}
