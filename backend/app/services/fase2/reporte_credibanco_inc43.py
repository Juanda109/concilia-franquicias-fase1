"""Inc43: puente diagnostico Inc41 -> Inc42 -> contrato Inc39, sin alterar UI.

No acredita correspondencias ni consulta Host. La matriz JSON de reglas es
opcional y solo se admite con evidencia explicita de homologacion.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from app.services.fase2.calculo_canje_pg_inc41 import leer_pg
from app.services.fase2.correspondencias_canje_inc42 import aplicar
from app.services.fase2.contrato_maestro_inc39 import COLUMNAS, validar_fila


def construir(informe41, correspondencias=()):
    if informe41.get('certificado') is not False or informe41.get('origen') != 'POSTGRESQL_SOLO_LECTURA':
        raise ValueError('Se requiere informe Inc41 diagnostico')
    if not isinstance(correspondencias, (list, tuple)):
        raise ValueError('Correspondencias deben ser una lista')
    informe42 = aplicar(informe41, correspondencias)
    # Los importes del Inc41 son diagnosticos: nunca se presentan como
    # valor_franquicia sin correspondencia y campo monetario acreditados.
    grupos41 = {}
    for grupo in informe41.get('resultados', []):
        clave = (grupo['id_archivo'], grupo['insumo'], grupo['familia'], grupo['concepto_literal'])
        if clave in grupos41:
            raise ValueError(f'Grupo de origen duplicado: {clave}')
        grupos41[clave] = grupo
    filas, detalle, vistos = [], [], set()
    for r in informe42['resultados']:
        identidad = (r['id_archivo'], r['insumo'], r['familia'], r['concepto'])
        if identidad in vistos:
            raise ValueError(f'Grupo duplicado: {identidad}')
        vistos.add(identidad)
        origen = grupos41.get(identidad)
        if origen is None:
            raise ValueError(f'Falta grupo original Inc41: {identidad}')
        importes = origen.get('importes', {})
        if not isinstance(importes, dict):
            raise ValueError('Importes diagnosticos invalidos')
        # Copia literal, sin elegir arbitrariamente un campo de conciliacion.
        diagnostico = {
            'importes_diagnosticos': dict(importes),
            'nulos_familia': dict(origen.get('nulos_familia') or {}),
            'estado_importes': 'CALCULADO_DIAGNOSTICO_NO_HOMOLOGADO',
            'fuente_importes': 'INC41_POSTGRESQL_SOLO_LECTURA',
            'campos_disponibles': list(importes),
        }
        # Cuenta 880 es vista auxiliar solapada: nunca fila monetaria del maestro.
        if r['familia'] == 'cuenta_880':
            detalle.append({**r, **diagnostico, 'uso': 'SOLO_TRAZABILIDAD_NO_SUMAR'})
            continue
        estado = ('CALCULADO_NO_HOMOLOGADO' if r['cuenta'] is not None and
                  r['valor_franquicia'] is not None else 'PENDIENTE_HOMOLOGACION')
        fila = dict(franquicia='CREDIBANCO', cuenta=r['cuenta'], concepto=r['concepto'],
                    valor_franquicia=r['valor_franquicia'], ha22=None, ha26=None,
                    ha32=None, total_host=None, diferencia=None,
                    estado_conciliacion=estado, accion='DETALLE')
        validar_fila(fila)
        filas.append(fila)
        detalle.append({**r, **diagnostico, 'uso': 'FILA_MAESTRO', 'indice_fila':len(filas)-1})
    if any(tuple(f.keys()) != COLUMNAS for f in filas):
        raise ValueError('Contrato de 11 columnas alterado')
    return dict(id_jornada=informe41['id_jornada'], origen='INC41_INC42_INC39_DIAGNOSTICO',
                columnas=list(COLUMNAS), filas=filas, detalle=detalle,
                indicadores=dict(cruces=0, conciliados=0, diferencias=0, incorporados_maestro=0),
                certificado=False, estado='SIN_CRUCES_HOST_HOMOLOGADOS',
                correspondencias_sin_grupo=informe42['correspondencias_sin_grupo'],
                conteos=informe41.get('conteos'), archivos=informe41.get('archivos'),
                advertencias=['La tabla contiene resultados diagnosticos; no se ha realizado conciliacion.',
                              'Cuenta 880 es vista auxiliar y no se suma de nuevo.',
                              'Los importes diagnosticos Inc41 se conservan en detalle; valor_franquicia requiere correspondencia y campo_importe acreditados.',
                              'Las columnas Host, total_host y diferencia permanecen nulas.',
                              'Los indicadores de cruces permanecen en cero hasta homologacion.'])


def ejecutar(id_jornada, correspondencias=()):
    return construir(leer_pg(id_jornada), correspondencias)


def main():
    p = argparse.ArgumentParser(description='Inc43: puente Credibanco PG a contrato Maestro, solo lectura')
    p.add_argument('--jornada', type=int, required=True)
    p.add_argument('--salida', type=Path, required=True)
    p.add_argument('--correspondencias', type=Path, help='JSON de correspondencias con evidencia; opcional')
    a = p.parse_args()
    if a.salida.exists(): p.error('La salida ya existe')
    reglas = []
    if a.correspondencias:
        reglas = json.loads(a.correspondencias.read_text(encoding='utf-8-sig'))
    informe = ejecutar(a.jornada, reglas)
    texto = json.dumps(informe, ensure_ascii=False, indent=2, default=str)
    a.salida.mkdir(parents=True, exist_ok=False)
    (a.salida / 'reporte_maestro_diagnostico.json').write_text(texto, encoding='utf-8')
    (a.salida / 'sha256_reporte.txt').write_text(hashlib.sha256(texto.encode('utf-8')).hexdigest()+'\n', encoding='utf-8')
    print(json.dumps({'jornada':a.jornada,'filas':len(informe['filas']),
                      'estado':informe['estado'],'certificado':False}, indent=2))

if __name__ == '__main__': main()
