from datetime import date,timedelta

def derivar_fechas_contables(fecha_conciliacion:date)->list[date]:
    """A partir de la Fecha de conciliación elegida por la analista, deriva la(s)
    fecha(s) contable(s) reales. Si la fecha cae en martes se derivan 3 fechas
    (sábado/domingo/lunes anteriores, por el rezago de fin de semana sin
    operación bancaria); cualquier otro día se deriva solo 1: el día hábil
    inmediatamente anterior."""
    if fecha_conciliacion.weekday()==1:
        return [fecha_conciliacion-timedelta(days=3),fecha_conciliacion-timedelta(days=2),fecha_conciliacion-timedelta(days=1)]
    b=fecha_conciliacion-timedelta(days=1)
    while b.weekday()>=5:
        b=b-timedelta(days=1)
    return [b]
