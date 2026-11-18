"""INC64: vinculo explicito jornada/catalogo; solo lectura y sin certificacion."""
import hashlib
import json
import os
from datetime import date
from pathlib import Path


def resolver_vinculo(id_jornada, fecha_contable, ruta_registro=None):
    """Devuelve ruta autorizada o None si no hay registro configurado.

    Registro JSON: {"jornadas": {"123": {"fecha_contable": "YYYY-MM-DD",
    "archivo": "ruta absoluta", "sha256": "64 caracteres hex"}}}.
    """
    ruta_registro = ruta_registro or os.getenv('INC64_REGISTRO_CATALOGOS')
    if not ruta_registro:
        return None
    ruta = Path(ruta_registro)
    if not ruta.is_file():
        raise ValueError('Registro INC64 no disponible')
    datos = json.loads(ruta.read_text(encoding='utf-8-sig'))
    if not isinstance(datos, dict) or not isinstance(datos.get('jornadas'), dict):
        raise ValueError('Registro INC64 invalido')
    vinculo = datos['jornadas'].get(str(id_jornada))
    if vinculo is None:
        return None
    if not isinstance(vinculo, dict):
        raise ValueError('Vinculo INC64 invalido')
    fecha = fecha_contable.isoformat() if isinstance(fecha_contable, date) else str(fecha_contable)
    if vinculo.get('fecha_contable') != fecha:
        raise ValueError('Fecha jornada/catalogo incompatible')
    archivo = Path(vinculo.get('archivo', ''))
    huella = vinculo.get('sha256')
    if not archivo.is_absolute() or archivo.suffix.lower() not in ('.xlsx', '.xlsm'):
        raise ValueError('Ruta catalogo INC64 invalida')
    if not isinstance(huella, str) or len(huella) != 64 or any(c not in '0123456789abcdef' for c in huella.lower()):
        raise ValueError('Huella catalogo INC64 invalida')
    if not archivo.is_file():
        raise ValueError('Catalogo INC64 inexistente')
    real = hashlib.sha256(archivo.read_bytes()).hexdigest()
    if real.lower() != huella.lower():
        raise ValueError('Huella catalogo INC64 diferente')
    return archivo


def consultar_fecha_jornada(id_jornada):
    """Consulta fecha contable con transaccion de solo lectura."""
    from app.repositories.database import connection
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute('SELECT fecha_contable FROM public.con_jornada WHERE id_jornada = %s', (id_jornada,))
            fila = cur.fetchone()
    if fila is None:
        raise ValueError('Jornada inexistente')
    return fila[0]
