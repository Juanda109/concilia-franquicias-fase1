"""Incremento 15: diagnostico seguro, sin cruces contables ni escrituras."""
import argparse
import csv
import json
import os
from collections import Counter
from pathlib import Path

HOST_IDS = {"HA22": 1136, "HA26": 1141, "HA32": 1142}
CANJE_IDS = {"CAET": 1253, "CANT": 1254}


def clasificar_host(fila):
    """La muestra 1377 no acredita origen real, incluso si HA32 carece de etiqueta."""
    if fila.get("concepto") and "PRUEBA SINTETICA" in str(fila["concepto"]).upper():
        return "BLOQUEADO_SINTETICO"
    if fila.get("tx_host") == "HA32":
        return "ORIGEN_NO_VERIFICADO"
    return "ORIGEN_NO_VERIFICADO"


def evaluar(host, canje, matriz):
    if not isinstance(matriz, dict) or matriz.get("fase") != 2 or not isinstance(matriz.get("reglas"), list):
        raise ValueError("Matriz invalida")
    if any(r.get("estado_regla") == "APROBADA" for r in matriz["reglas"]):
        raise ValueError("Matriz con reglas aprobadas: requiere evaluador transaccional auditado; no ejecutar este diagnostico")
    if len({(r["id_archivo"], r["id_host_resultado"]) for r in host}) != len(host):
        raise ValueError("Identificadores Host duplicados")
    if len({(r["id_archivo"], r["id_canje_detalle"]) for r in canje}) != len(canje):
        raise ValueError("Identificadores canje duplicados")
    conteo = Counter(clasificar_host(r) for r in host)
    return {"estado": "DIAGNOSTICO_SIN_CONCILIACION_CERTIFICADA", "filas_host": len(host),
            "filas_canje": len(canje), "host_estados": dict(conteo), "cruces_aprobados": 0,
            "reglas_aprobadas": 0, "advertencias": ["Sin matriz aprobada", "Datos Host sin procedencia acreditada", "No se suman HA22 HA26 HA32"]}


def ejecutar(salida, matriz_ruta):
    if os.getenv("DB_NAME") != "concilia_test":
        raise RuntimeError("Solo se permite base concilia_test para diagnostico")
    import psycopg
    matriz = json.loads(Path(matriz_ruta).read_text(encoding="utf-8-sig"))
    if any(r.get("estado_regla") == "APROBADA" for r in matriz.get("reglas", [])):
        raise RuntimeError("No ejecutar con reglas aprobadas: esta herramienta solo diagnostica")
    salida = Path(salida)
    if salida.exists():
        raise FileExistsError("La carpeta de salida existe")
    with psycopg.connect(host=os.environ["DB_HOST"], port=int(os.environ["DB_PORT"]),
                         dbname="concilia_test", user=os.environ["DB_USER"],
                         password=os.environ["DB_PASSWORD"], connect_timeout=5) as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("""SELECT id_archivo, id_host_resultado, tx_host, cuenta, centro, concepto,
                       fecha_contable FROM public.con_host_resultado WHERE id_archivo = ANY(%s)
                       ORDER BY id_archivo, id_host_resultado""", (list(HOST_IDS.values()),))
            host = cur.fetchall()
            cur.execute("""SELECT id_archivo, id_canje_detalle, cuenta, tx, bin_dest, fecha_contable
                       FROM public.con_canje_detalle WHERE id_archivo = ANY(%s)
                       ORDER BY id_archivo, id_canje_detalle""", (list(CANJE_IDS.values()),))
            canje = cur.fetchall()
            cur.execute("""SELECT a.id_archivo, a.tipo_archivo, a.estado, i.id_jornada, i.estado AS estado_insumo
                       FROM public.con_archivo_carga a JOIN public.con_insumo_esperado i ON i.id_archivo=a.id_archivo
                       WHERE a.id_archivo = ANY(%s)""", (list(HOST_IDS.values()) + list(CANJE_IDS.values()),))
            metadata = cur.fetchall()
    esperado = {**{v:k for k,v in HOST_IDS.items()}, **{v:k for k,v in CANJE_IDS.items()}}
    if len(metadata) != 5 or any(r["id_archivo"] not in esperado or r["tipo_archivo"] != esperado[r["id_archivo"]] or r["estado"] != "PROCESADO" or r["estado_insumo"] != "PROCESADO" or r["id_jornada"] != 1377 for r in metadata):
        raise RuntimeError("Archivos, estados o jornada no coinciden con caso autorizado")
    if any(str(r["fecha_contable"]) != "2026-10-21" for r in host + canje):
        raise RuntimeError("Fecha contable inesperada")
    informe = evaluar(host, canje, matriz)
    informe.update({"jornada": 1377, "fecha": "2026-10-21", "ids_host": HOST_IDS, "ids_canje": CANJE_IDS})
    salida.mkdir(parents=True, exist_ok=False)
    with (salida / "host_diagnostico.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["id_archivo", "id_host_resultado", "tx_host", "cuenta", "centro", "concepto", "estado"])
        for r in host:
            w.writerow([r.get(k) for k in ("id_archivo", "id_host_resultado", "tx_host", "cuenta", "centro", "concepto")] + [clasificar_host(r)])
    (salida / "informe.json").write_text(json.dumps(informe, indent=2, ensure_ascii=False), encoding="utf-8")
    return informe


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--salida", required=True)
    p.add_argument("--matriz", default="backend/app/services/fase2/matriz_correspondencias.json")
    a = p.parse_args()
    print(json.dumps(ejecutar(a.salida, a.matriz), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
