"""Concilia F1: aplicar DDL 021 y persistir DEPO 289 en una sola transaccion.
No ejecuta nada al importarse. Solo concilia_test. Ejecutar con PYTHONPATH=backend;tests.
"""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import re

from app.repositories.database import connection
from app.services import persistencia_detalle

ID = 289
TABLA = 'con_depo_detalle'
DDL_PATH = Path('sql/migrations/021_DEPO_DETALLE.sql')
PENDIENTES = ('amex_nacional', 'cuenta', 'tii', 'comision_adq_atm_2888', 'tii_5130')


def ddl_sin_transaccion(texto):
    # Extrae los delimitadores sin ejecutar COMMIT del archivo.
    texto = re.sub(r'\bBEGIN\s*;', '', texto, count=1, flags=re.I)
    texto, n = re.subn(r'\bCOMMIT\s*;\s*$', '', texto, count=1, flags=re.I)
    if n != 1 or re.search(r'\b(COMMIT|ROLLBACK)\s*;', texto, flags=re.I):
        raise RuntimeError('DDL con delimitadores de transaccion inesperados')
    return texto


def main():
    ddl = ddl_sin_transaccion(DDL_PATH.read_text(encoding='utf-8-sig'))
    with connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT current_database()')
                if cur.fetchone()[0] != 'concilia_test':
                    raise RuntimeError('Base de datos no autorizada')
                cur.execute("SET LOCAL lock_timeout = '5s'")
                cur.execute("SELECT to_regclass('public.con_depo_detalle')")
                if cur.fetchone()[0] is not None:
                    raise RuntimeError('Tabla DEPO ya existe; no repetir migracion')
                cur.execute("""SELECT a.estado, i.estado FROM con_archivo_carga a
                    JOIN con_insumo_esperado i ON i.id_archivo=a.id_archivo
                    WHERE a.id_archivo=%s AND a.tipo_archivo='DEPO'""", (ID,))
                estados = cur.fetchall()
                if len(estados) != 1 or estados[0] != ('RECIBIDO', 'RECIBIDO'):
                    raise RuntimeError(f'Estado DEPO no esperado: {estados}')
                cur.execute('SELECT COUNT(*) FROM con_host_resultado WHERE id_archivo IN (290,291,292)')
                if cur.fetchone()[0] != 32:
                    raise RuntimeError('Resultados Host inesperados')
                cur.execute('SELECT COUNT(*) FROM con_canje_detalle WHERE id_archivo IN (286,287)')
                if cur.fetchone()[0] != 191:
                    raise RuntimeError('Detalle CAET/CANT inesperado')
                cur.execute('SELECT COUNT(*) FROM con_franquicia_resultado WHERE id_archivo=287')
                if cur.fetchone()[0] != 4:
                    raise RuntimeError('Resultados contables CANT inesperados')
                print('PRECONDICIONES: OK', flush=True)
                cur.execute(ddl)
                @contextmanager
                def compartida():
                    yield conn
                with patch.object(persistencia_detalle, 'connection', compartida):
                    resultado = persistencia_detalle.persistir_detalle(ID)
                if resultado['registros'] != 21 or resultado['idempotente']:
                    raise RuntimeError(f'Resultado inesperado: {resultado}')
                cur.execute('SELECT COUNT(*), COUNT(DISTINCT linea_origen), COUNT(tasa_de_intercambio) FROM con_depo_detalle WHERE id_archivo=%s', (ID,))
                if cur.fetchone() != (21,21,21):
                    raise RuntimeError('Conteos o tasa DEPO inconsistentes')
                cur.execute('SELECT COUNT(*) FROM con_depo_detalle WHERE id_archivo=%s AND tipo_movimiento NOT IN (\'02\',\'06\',\'26\',\'42\')', (ID,))
                if cur.fetchone()[0] != 0:
                    raise RuntimeError('Movimientos DEPO inesperados')
                condicion = ' OR '.join(f'{c} IS NOT NULL' for c in PENDIENTES)
                cur.execute(f'SELECT COUNT(*) FROM con_depo_detalle WHERE id_archivo=%s AND ({condicion})', (ID,))
                if cur.fetchone()[0] != 0:
                    raise RuntimeError('Derivados pendientes no son NULL')
                cur.execute('SELECT codigo, valor_obtenido FROM con_detalle_control WHERE id_archivo=%s', (ID,))
                controles = dict(cur.fetchall())
                if controles.get('TOTAL_REGISTROS') != '21' or controles.get('DESCARTADOS_FILTRO_PERSISTENCIA') != '4' or 'DERIVADOS_PENDIENTES' not in controles:
                    raise RuntimeError(f'Controles DEPO inesperados: {controles}')
                cur.execute("""SELECT a.estado,i.estado FROM con_archivo_carga a
                    JOIN con_insumo_esperado i ON i.id_archivo=a.id_archivo WHERE a.id_archivo=%s""", (ID,))
                if cur.fetchone() != ('PROCESADO','PROCESADO'):
                    raise RuntimeError('Estados DEPO no actualizados')
                cur.execute('SELECT COUNT(*) FROM con_host_resultado WHERE id_archivo IN (290,291,292)')
                if cur.fetchone()[0] != 32:
                    raise RuntimeError('Resultados Host alterados')
                cur.execute('SELECT COUNT(*) FROM con_canje_detalle WHERE id_archivo IN (286,287)')
                if cur.fetchone()[0] != 191:
                    raise RuntimeError('Detalle Canje alterado')
                print('VALIDACION PRE-COMMIT: OK', resultado, controles, flush=True)
            conn.commit()
            print('COMMIT: OK', flush=True)
        except BaseException:
            conn.rollback()
            print('ROLLBACK POR ERROR', flush=True)
            raise
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM con_depo_detalle WHERE id_archivo=%s", (ID,))
            assert cur.fetchone()[0] == 21
    print('VERIFICACION POST-COMMIT: OK', flush=True)


if __name__ == '__main__':
    main()
