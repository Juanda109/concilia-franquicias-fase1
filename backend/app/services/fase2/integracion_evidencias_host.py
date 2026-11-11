"""Incremento 21: evaluación conservadora de evidencia externa sin acreditar autenticidad."""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from app.services.fase2.control_procedencia_host import evaluar_procedencia
from app.services.fase2.evidencias_externas_host import validar_evidencia


def integrar(filas: list[dict], archivos: dict[int, str | Path], evidencias: dict[int, dict], *, fuentes_acreditadas: dict | None = None) -> dict:
    """No convierte declaraciones de evidencia en autorizaciones ni certificaciones.

    archivos: id_archivo -> ruta de archivo original. No lee ni altera BD.
    """
    ids = {r.get('id_archivo') for r in filas}
    if any(not isinstance(i, int) or isinstance(i, bool) or i <= 0 for i in ids):
        raise ValueError('ID_ARCHIVO_INVALIDO')
    if len({r.get('id_host_resultado') for r in filas}) != len(filas):
        raise ValueError('ID_REGISTRO_DUPLICADO')
    if set(archivos) - ids or set(evidencias) - ids:
        raise ValueError('ARCHIVO_FUERA_DE_POBLACION')
    controles = {}
    for id_archivo in sorted(ids):
        ruta = archivos.get(id_archivo)
        if ruta is None:
            controles[id_archivo] = {'estado': 'ORIGEN_NO_VERIFICADO', 'motivos': ['ARCHIVO_ORIGINAL_NO_DISPONIBLE'], 'sha256': None}
        else:
            controles[id_archivo] = validar_evidencia(ruta, evidencias.get(id_archivo), fuentes_acreditadas=fuentes_acreditadas)
        e = evidencias.get(id_archivo)
        if isinstance(e, dict) and e.get('id_archivo') != id_archivo:
            controles[id_archivo]['estado'] = 'ORIGEN_NO_VERIFICADO'
            controles[id_archivo]['motivos'] = list(dict.fromkeys(controles[id_archivo]['motivos'] + ['ID_ARCHIVO_NO_COINCIDE']))
    base = evaluar_procedencia(filas)  # Sin evidencias: nunca se eleva por datos autodeclarados
    resultados = []
    for fila, clasificacion in zip(filas, base['registros']):
        id_archivo = fila['id_archivo']
        control = controles[id_archivo]
        resultados.append({
            'id_archivo': id_archivo,
            'id_host_resultado': fila.get('id_host_resultado'),
            'tx_host': fila.get('tx_host'),
            'cuenta': fila.get('cuenta'),
            'centro': fila.get('centro'),
            'fecha_contable': str(fila.get('fecha_contable') or ''),
            'estado': clasificacion['estado'],
            'motivo': clasificacion['motivo'],
            'estado_evidencia': control['estado'],
            'motivos_evidencia': control['motivos'],
            'sha256': control.get('sha256'),
            'certificable': False,
        })
    return {'estado': 'DIAGNOSTICO_SIN_CONCILIACION_CERTIFICADA',
            'filas': len(resultados), 'conteos': dict(Counter(x['estado'] for x in resultados)),
            'cruces_certificados': 0, 'registros': resultados,
            'advertencias': ['Hash y autorizacion declarada no acreditan autenticidad', 'Sin verificador independiente no se habilita certificacion']}


def diagnosticar_jornada_1377(archivos: dict[int, str | Path] | None = None, evidencias: dict[int, dict] | None = None) -> dict:
    """Reutiliza lectura y validación de jornada 1377 del incremento 19."""
    import os
    if os.environ.get('DB_NAME') != 'concilia_test':
        raise RuntimeError('Solo se permite concilia_test')
    import psycopg
    from psycopg.rows import dict_row
    from app.services.fase2.diagnostico_procedencia_host import IDS, diagnosticar
    with psycopg.connect(host=os.environ['DB_HOST'], port=int(os.environ['DB_PORT']),
                         dbname='concilia_test', user=os.environ['DB_USER'],
                         password=os.environ['DB_PASSWORD'], connect_timeout=5) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute('''SELECT id_archivo,id_host_resultado,tx_host,cuenta,centro,
                           fecha_contable,concepto,valor_debe,valor_haber
                           FROM public.con_host_resultado WHERE id_archivo = ANY(%s)
                           ORDER BY id_archivo,id_host_resultado''', (list(IDS.values()),))
            filas = cur.fetchall()
            cur.execute('''SELECT a.id_archivo,a.tipo_archivo,a.estado,i.id_jornada,
                           i.estado AS estado_insumo FROM public.con_archivo_carga a
                           JOIN public.con_insumo_esperado i ON i.id_archivo=a.id_archivo
                           WHERE a.id_archivo = ANY(%s)''', (list(IDS.values()),))
            metadatos = cur.fetchall()
    if len(metadatos) != 3 or {m['id_archivo'] for m in metadatos} != set(IDS.values()):
        raise RuntimeError('Metadatos Host incompletos')
    if any(m['tipo_archivo'] != next(k for k,v in IDS.items() if v == m['id_archivo'])
           or m['id_jornada'] != 1377 or m['estado'] != 'PROCESADO'
           or m['estado_insumo'] != 'PROCESADO' for m in metadatos):
        raise RuntimeError('Metadatos Host no validos')
    diagnosticar(filas)  # Contrato de fecha y origen del incremento 19
    resultado = integrar(filas, archivos or {}, evidencias or {})
    resultado['jornada'] = 1377
    resultado['fecha'] = '2026-10-21'
    return resultado


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--salida', required=True)
    args = parser.parse_args()
    destino = Path(args.salida)
    if destino.exists():
        raise FileExistsError('Salida existente: no sobrescribir')
    resultado = diagnosticar_jornada_1377()
    destino.mkdir(parents=True, exist_ok=False)
    import csv
    with (destino / 'movimientos_host.csv').open('w', encoding='utf-8-sig', newline='') as f:
        cols = ['id_archivo','id_host_resultado','tx_host','cuenta','centro','fecha_contable','estado','motivo','estado_evidencia','motivos_evidencia','sha256','certificable']
        writer = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        writer.writeheader()
        for r in resultado['registros']:
            writer.writerow({**r, 'motivos_evidencia': '|'.join(r['motivos_evidencia'])})
    resumen = {k:v for k,v in resultado.items() if k != 'registros'}
    (destino / 'informe.json').write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(resumen, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
