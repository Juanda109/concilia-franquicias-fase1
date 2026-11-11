"""INC56-B: diagnostico DEPO sin escrituras ni homologacion monetaria."""
from collections import Counter
from pathlib import Path
from decimal import Decimal

# Posiciones 1-based del parser existente; campos de 9 digitos en unidad cruda.
CAMPOS = {"tipo": (1,2), "bin_fuente": (3,6), "bin_destino": (9,6),
          "valor_total": (123,9), "valor_intercambio": (141,9),
          "valor_intercambio_2": (246,9), "indicador_cnb": (265,3)}
TIPOS_PERSISTIDOS = {"02", "06", "26", "42"}

def campo(linea, inicio, longitud):
    return linea[inicio-1:inicio-1+longitud].strip()

def entero(valor):
    return int(valor) if valor and valor.isdigit() else 0

def analizar(ruta):
    ruta = Path(ruta)
    resultado = {"archivo": ruta.name, "total_lineas": 0, "registros_control_05": 0,
                 "movimientos": 0, "tipos": {}, "longitudes": {},
                 "sumas_crudas_por_tipo": {}, "alertas": [], "muestras": []}
    tipos, longitudes, sumas = Counter(), Counter(), {}
    for numero, linea in enumerate(ruta.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not linea: continue
        resultado["total_lineas"] += 1
        longitudes[len(linea)] += 1
        tipo = campo(linea, 1, 2)
        tipos[tipo] += 1
        if tipo == "05":
            resultado["registros_control_05"] += 1
            continue
        if tipo not in TIPOS_PERSISTIDOS:
            resultado["alertas"].append({"linea": numero, "motivo": "TIPO_NO_HOMOLOGADO", "tipo": tipo})
            continue
        resultado["movimientos"] += 1
        valores = {k: entero(campo(linea, *CAMPOS[k])) for k in ("valor_total", "valor_intercambio", "valor_intercambio_2")}
        tasa = valores["valor_total"] - valores["valor_intercambio_2"]
        if tipo == "26": tasa = -tasa
        s = sumas.setdefault(tipo, {"cantidad":0, "valor_total_crudo":0, "valor_intercambio_crudo":0,
                                   "valor_intercambio_2_crudo":0, "tasa_intercambio_cruda":0})
        s["cantidad"] += 1
        for k,v in valores.items(): s[k+"_crudo"] += v
        s["tasa_intercambio_cruda"] += tasa
        if len(resultado["muestras"]) < 8:
            resultado["muestras"].append({"linea":numero, "tipo":tipo,
                "bin_fuente":campo(linea,*CAMPOS["bin_fuente"]),
                "bin_destino":campo(linea,*CAMPOS["bin_destino"]),
                "indicador_cnb_crudo":campo(linea,*CAMPOS["indicador_cnb"]),
                "valores_crudos":valores})
    resultado["tipos"] = dict(sorted(tipos.items()))
    resultado["longitudes"] = {str(k):v for k,v in sorted(longitudes.items())}
    resultado["sumas_crudas_por_tipo"] = sumas
    resultado["alertas"].append({"motivo":"SIN_ESCALA_MONETARIA_VALIDADA", "detalle":"Los importes son enteros crudos de 9 posiciones; no convertir a COP sin validar escala de plantilla."})
    resultado["alertas"].append({"motivo":"CNB_AMEX_PENDIENTES", "detalle":"No se certifican reglas CNB/AMEX ni cuenta contable por BIN."})
    return resultado

if __name__ == "__main__":
    import argparse, json
    a=argparse.ArgumentParser()
    a.add_argument("archivo")
    a.add_argument("--salida")
    args=a.parse_args()
    texto=json.dumps(analizar(args.archivo),ensure_ascii=False,indent=2)
    if args.salida: Path(args.salida).write_text(texto,encoding="utf-8")
    else: print(texto)
