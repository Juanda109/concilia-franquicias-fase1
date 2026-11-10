"""Aplica cambios incrementales y reversibles al codigo existente; NO ejecuta SQL."""
from pathlib import Path
from datetime import datetime
import ast
import shutil

SERVICE = Path('backend/app/services/persistencia_detalle.py')
API = Path('backend/app/api/detalle_archivos.py')
FIELDS = ('seccion','motivo_codigo','es_control','lado','concepto','valor_principal',
          'valor_proceso','valor_financiacion','valor_fotocopias','valor_red',
          'valor_depositos_electronicos','valor_total','valor_outgoing','valor_incoming',
          'factor_compra','factor_venta','cinta','fecha_cinta')
NUMERIC = tuple(x for x in FIELDS if x.startswith('valor_') or x.startswith('factor_'))

s = SERVICE.read_text(encoding='utf-8-sig')
a = API.read_text(encoding='utf-8-sig')
if 'CAMPOS_CARTA' in s or '"CARTA_COMPENSACION": "con_carta_compensacion_detalle"' in a:
    raise RuntimeError('Carta ya parece integrada; revisar manualmente')

def replace_once(txt, old, new, label):
    if txt.count(old) != 1:
        raise RuntimeError(f'Ancla no unica o inexistente: {label} ({txt.count(old)})')
    return txt.replace(old,new,1)

s = replace_once(s, 'class DetalleError',
    'CAMPOS_CARTA = '+repr(FIELDS)+'\nNUMERICOS_CARTA = frozenset('+repr(NUMERIC)+')\n\nclass DetalleError', 'constantes')
s = replace_once(s, "('CAET','CANT','DEPO',*HOST)",
    "('CAET','CANT','DEPO','CARTA_COMPENSACION',*HOST)", 'tipos')
s = replace_once(s, "('con_depo_detalle' if tipo=='DEPO' else HOST[tipo])",
    "('con_depo_detalle' if tipo=='DEPO' else ('con_carta_compensacion_detalle' if tipo=='CARTA_COMPENSACION' else HOST[tipo]))", 'tabla')
s = replace_once(s, "            elif tipo == 'DEPO':", """            elif tipo == 'CARTA_COMPENSACION':
                columnas = ['id_archivo','fecha_contable','linea_origen','correlation_id',*CAMPOS_CARTA]
                stmt = sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
                    sql.Identifier(tabla), sql.SQL(',').join(map(sql.Identifier,columnas)),
                    sql.SQL(',').join(sql.Placeholder()*len(columnas)))
                for registro in registros:
                    valores = [id_archivo,fecha,registro['numero_linea'],corr]
                    for campo in CAMPOS_CARTA:
                        valor = registro.get(campo)
                        if valor == '': valor = None
                        if campo in NUMERICOS_CARTA and valor is not None:
                            valor = Decimal(str(valor))
                        valores.append(valor)
                    cur.execute(stmt,valores)
            elif tipo == 'DEPO':""", 'insercion')
s = replace_once(s, "if tipo in ('CAET','DEPO') and estado=='RECIBIDO':",
    "if tipo in ('CAET','DEPO','CARTA_COMPENSACION') and estado=='RECIBIDO':", 'estados')

a = replace_once(a, '"DEPO": "con_depo_detalle",',
    '"DEPO": "con_depo_detalle",\n                    "CARTA_COMPENSACION": "con_carta_compensacion_detalle",', 'api tabla')
a = replace_once(a, "                            elif tipo == 'DEPO':", """                            elif tipo == 'CARTA_COMPENSACION':
                                from app.services.persistencia_detalle import CAMPOS_CARTA
                                campos = ('linea_origen', *CAMPOS_CARTA)
                                cur.execute(
                                    f"SELECT {', '.join(campos)} FROM {tabla_nueva} WHERE id_archivo=%s ORDER BY linea_origen LIMIT %s OFFSET %s",
                                    (id_archivo, pageSize, offset),
                                )
                                items = cur.fetchall()
                            elif tipo == 'DEPO':""", 'api consulta')
ast.parse(s)
ast.parse(a)
for path, content in ((SERVICE,s),(API,a)):
    backup = path.with_name(path.name+'.pre_carta_022_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.bak')
    shutil.copy2(path,backup)
    path.write_text(content,encoding='utf-8',newline='\n')
    print('ACTUALIZADO',path,'RESPALDO',backup)
print('CODIGO INTEGRADO; SQL NO EJECUTADO')
