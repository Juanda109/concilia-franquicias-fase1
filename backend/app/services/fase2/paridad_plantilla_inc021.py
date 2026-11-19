"""Paridad aritmética de subtotales F/G de plantilla maestra INC021.

Solo lectura; no ejecuta fórmulas externas, no homologa cuentas ni certifica.
"""
import re
import ast
from decimal import Decimal
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.utils.cell import get_column_letter

CELDAS_OBJETIVO = (
    'F42','G42','F56','G56','F98','G98','F99','G99',
    'F122','G122','F134','G134','F207','G207',
    'F208','G208','F210','G210','G211',
)
SUMA = re.compile(r'^=SUM\(([FG])(\d+):\1(\d+)\)$', re.I)
REFERENCIA = re.compile(r'^[FG]\d+$', re.I)

class DependenciaNoResuelta(ValueError):
    pass


def cargar_formulas(ruta):
    """Carga celdas de la hoja completa para resolver dependencias internas."""
    libro = load_workbook(Path(ruta), read_only=True, data_only=False, keep_links=True)
    try:
        hoja = libro['PLANTILLA (2)']
        hoja.reset_dimensions()
        return {celda.coordinate: celda.value
                for fila in hoja.iter_rows() for celda in fila
                if celda.value is not None and celda.column <= 36}  # Excluye AK.
    finally:
        libro.close()


_CELDA = re.compile(r"(?<![A-Z0-9_!])\$?([A-Z]{1,2})\$?([1-9][0-9]*)(?![A-Z0-9_])", re.I)
_RANGO = re.compile(r"^=SUM\(\$?([A-Z]{1,2})\$?([0-9]+):\$?([A-Z]{1,2})\$?([0-9]+)\)$", re.I)
_SIMPLE = re.compile(r"^=[+\-*/().0-9 A-Z$]+$", re.I)


def evaluar(celda, valores, formulas, pila=None):
    """Evalua aritmetica y SUM de referencias internas con Decimal.

    No interpreta textos, referencias externas, IF, VLOOKUP, ni #REF!.
    Las celdas vacias valen cero solo como operandos dentro de formulas.
    """
    pila = set() if pila is None else pila
    celda = celda.upper().replace('$', '')
    if celda in pila:
        raise DependenciaNoResuelta(f'Referencia circular: {celda}')
    if celda in valores:
        try:
            numero = Decimal(str(valores[celda]))
        except Exception as exc:
            raise DependenciaNoResuelta(f'Importe invalido: {celda}') from exc
        if not numero.is_finite():
            raise DependenciaNoResuelta(f'Importe no finito: {celda}')
        return numero
    contenido = formulas.get(celda)
    if isinstance(contenido, (int, float, Decimal)) and not isinstance(contenido, bool):
        numero = Decimal(str(contenido))
        if numero.is_finite():
            return numero
        raise DependenciaNoResuelta(f'Importe no finito: {celda}')
    if not isinstance(contenido, str) or not contenido.startswith('='):
        raise DependenciaNoResuelta(f'Sin importe verificable: {celda}')
    if '#REF!' in contenido or '!' in contenido or '[' in contenido:
        raise DependenciaNoResuelta(f'Referencia externa o rota: {celda}')
    pila.add(celda)
    try:
        rango = _RANGO.fullmatch(contenido.strip())
        if rango:
            c1, r1, c2, r2 = rango.groups()
            from openpyxl.utils.cell import column_index_from_string
            x1, x2 = column_index_from_string(c1), column_index_from_string(c2)
            r1, r2 = int(r1), int(r2)
            if x1 > x2 or r1 > r2 or (x2-x1+1)*(r2-r1+1)>100000:
                raise DependenciaNoResuelta(f'Rango no permitido: {celda}')
            total = Decimal(0)
            for x in range(x1, x2+1):
                for r in range(r1, r2+1):
                    ref = f'{get_column_letter(x)}{r}'
                    if ref not in valores and ref not in formulas:
                        continue
                    total += evaluar(ref, valores, formulas, pila)
            return total
        if not _SIMPLE.fullmatch(contenido.strip()):
            raise DependenciaNoResuelta(f'Formula no admitida: {celda}: {contenido}')
        expresion = contenido.strip()[1:].replace('$', '')
        referencias = {}
        def reemplazar(m):
            ref = f'{m.group(1).upper()}{m.group(2)}'
            variable = f'R{len(referencias)}'
            referencias[variable] = ref
            return variable
        expresion = _CELDA.sub(reemplazar, expresion)
        try:
            arbol = ast.parse(expresion, mode='eval')
        except SyntaxError as exc:
            raise DependenciaNoResuelta(f'Formula no admitida: {celda}') from exc
        def resolver(n):
            if isinstance(n, ast.Expression):
                return resolver(n.body)
            if isinstance(n, ast.Name) and n.id in referencias:
                ref = referencias[n.id]
                if ref not in valores and ref not in formulas:
                    return Decimal(0)
                return evaluar(ref, valores, formulas, pila)
            if isinstance(n, ast.Constant) and type(n.value) in (int, float):
                return Decimal(str(n.value))
            if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
                v = resolver(n.operand)
                return v if isinstance(n.op, ast.UAdd) else -v
            if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
                izq, der = resolver(n.left), resolver(n.right)
                if isinstance(n.op, ast.Add): return izq + der
                if isinstance(n.op, ast.Sub): return izq - der
                if isinstance(n.op, ast.Mult): return izq * der
                if der == 0: raise DependenciaNoResuelta(f'Division por cero: {celda}')
                return izq / der
            raise DependenciaNoResuelta(f'Operacion no admitida: {celda}')
        return resolver(arbol)
    finally:
        pila.remove(celda)


def diagnostico_paridad(ruta, valores):
    formulas = cargar_formulas(ruta)
    resultado = {}
    for celda in CELDAS_OBJETIVO:
        try:
            resultado[celda] = {'estado':'CALCULADO', 'valor':str(evaluar(celda,valores,formulas))}
        except (DependenciaNoResuelta, ValueError) as exc:
            resultado[celda] = {'estado':'DEPENDENCIA_PENDIENTE','detalle':str(exc)}
    return {
        'incremento':'INC021', 'alcance':'PARIDAD_ARITMETICA_PLANTILLA_NO_VISA_EXCLUSIVA',
        'celdas':resultado, 'diferencia_contable':None,
        'certificado':False,'conciliado_host':False,'homologado_contablemente':False,
    }
