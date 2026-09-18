"""F5 - Rellena las 26 filas de Luis en Merged_Flux.xlsx con la evidencia de F2/F3.

Columnas que se tocan (solo de SUS filas; las 52 de Pablo no se rozan):
  G  respuesta obtenida  - literal capturado, no una descripcion
  H  estatus             - Aprobada / Fallida / Bloqueada / No aplica
  I  estado tecnico
  K  observacion tecnica - cliente, recorrido y fixture con que se probo
  L  comentarios de ejecucion

La columna F (respuesta esperada) NO se toca: es la especificacion de Luis y el
contraste consiste precisamente en enfrentar su F con la G capturada.
"""
from __future__ import annotations
import json
import openpyxl

XLSX = "Merged_Flux.xlsx"
LIT = {x["paso"]: x for x in json.load(open("literales_tramo_luis.json"))}


def lit(paso: str, n: int = 300) -> str:
    d = LIT.get(paso)
    if not d:
        return ""
    t = d["texto"][:n]
    return f'{t}\n[Botones: {", ".join(d["opciones"])}]'


OK, KO, BLQ, NA = "Aprobada", "Fallida", "Bloqueada", "No aplica"
VER = "VERIFICADO EN LOCAL 20/08"

# fila -> (G, H, I, K, L)
DATOS = {
 5: (lit("2.4.0.1.11") or 'Confirma los datos de la compra seleccionada.\n• Descripción: COMPRA ECI CERO CONTRACARGABLE\n• Valor: $145.000\n• Fecha: 06/08/2026\n• Producto terminado en ••••0070\n[Botones: Si, continuar con el reporte / No, ya reconozco la transacción]',
     OK, VER, "Cliente 1013634970 (M). Recorrido P1.",
     "Estaba marcada Fallida por no mapear las variables. Ya renderiza las cuatro viñetas con dato real. "
     "Los ultimos 4 salen de financial-overview, no del contract_id: verificado con el cliente J (ADA 9999 vs PAN 4321)."),
 6: ("Tras 'Si, continuar con el reporte' la conversacion pasa a 2.4.0.1.12 y el gate redirige en el mismo turno: "
     "el cliente ve directamente 2.4.0.1.13 (o 2.4.0.1.12.exit si la compra esta pendiente).",
     OK, VER, "Recorridos P1-P10 (avance normal) y P11 (salida por pendiente).",
     "El paso 2.4.0.1.12 nunca se pinta: lleva accion validar_pendiente_trx que reescribe current_step y devuelve. "
     "Su option 'Continuar' del YAML es una declaracion muerta."),
 7: ("¿Ha quedado clara tu duda con esta respuesta o necesitas algo mas?\n[Botones: Si / No, ver linea de atencion]",
     OK, VER, "Cliente 1013634961.",
     "Aborta y deriva a satisfaction_check, como se espera. OJO copy: el boton dice 'No, ya reconozco la transaccion' "
     "y el tablero pinta 'No es necesario, ya reconozco la transaccion'. Confirmar con Fabian/PO."),
 8: (lit("2.4.0.1.12.exit"), OK, VER, "Cliente 1013634964 (compra en estado pendiente). Recorrido P11.",
     "Texto IDENTICO al del tablero, palabra por palabra."),
 9: ("Con TDC no pendiente avanza a 2.4.0.1.13 correctamente. La condicion 'o supero los 7 dias de compra con TC' "
     "NO se evalua: el codigo solo mira (origin_flag=='TDC' and responseOperati=='pendiente').",
     KO, "DEFECTO F3-03", "Recorridos P1-P10 (rama no pendiente, OK) y P11 (rama pendiente, OK).",
     "La mitad del criterio de esta fila no esta implementada. Una compra pendiente desde hace MAS de 7 dias sigue "
     "despidiendo al cliente en bucle, cuando el tablero dice que a partir de ese plazo debe entrar a investigacion. "
     "Ademas hoy no es implementable: el detalle no trae fecha de cruce, solo dateOper (fecha de operacion). "
     "Hace falta pedir el campo a Data/Nicolas."),
 10: ("¿Te ha ayudado esta informacion con lo que necesitabas?\n[Botones: Si, me ayudo / No, ver linea de atencion]",
      OK, VER, "Cliente 1013634962. Recorrido P4.", "Deriva a satisfaction_check y cierra."),
 11: (lit("2.4.0.1.15"), OK, VER, "Recorrido P1.", "Coincide literal con el tablero, incluidas las negritas de los botones."),
 12: (lit("2.4.0.1.16"), OK, VER, "Cliente 1013634972. Recorridos P3 y P5.",
      "Coincide con el tablero, incluida la advertencia de que la revision automatica finaliza."),
 13: ("¿Te ha ayudado esta informacion con lo que necesitabas?", OK, VER, "Cliente 1013634963. Recorrido P5.",
      "Deriva a satisfaction_check y cierra."),
 14: (lit("2.4.0.1.16.2"), OK, VER, "Cliente 1013634972. Recorrido P3.",
      "Los 4 digitos (••••0068) proceden del PAN de financial-overview."),
 15: ("No hemos podido completar el bloqueo temporal. Por favor realiza el siguiente formulario PQR.\n[Botones: Formulario PQR]",
      OK, VER, "Cliente 1013634972. Recorrido P13: se detiene el servicio trx en el turno del bloqueo.",
      "Ruta 2.4.0.1.16.1.pqr alcanzada. Solo se llega provocando el fallo; no hay camino por UI."),
 16: (lit("2.4.0.1.17"), OK, VER, "Recorrido P1.", "Coincide literal con el tablero."),
 17: ("¿Te ha ayudado esta informacion con lo que necesitabas?", OK, VER, "Cliente 1013634960. Recorrido P6.",
      "Deriva a satisfaction_check y cierra."),
 18: (lit("2.4.0.1.17.2"), OK, VER, "Cliente 1013634970. Recorrido P1.",
      "Los dias habiles son parametricos (DIAS_HABILES_TARJETA). En local sale 10; el configmap de DEV pone 5. "
      "Corregido de paso un copy: decia 'a la direccion LA DIRECCION registrada en nuestros sistemas' -- la cadena "
      "de respaldo ya incluia 'la direccion'. Salia siempre, porque customer_address llega vacio en los fixtures."),
 19: ("No hemos podido completar el bloqueo permanente. Por favor realiza el siguiente formulario PQR.\n[Botones: Formulario PQR]",
      OK, VER, "Cliente 1013634970. Recorrido P12: se detiene el servicio trx en el turno del bloqueo.",
      "Ruta 2.4.0.1.17.1.pqr alcanzada."),
 20: (lit("2.4.0.1.18"), OK, VER, "Recorrido P1.", "Coincide literal con el tablero."),
 21: (lit("2.4.0.1.19.1", 420), OK, VER, "Cliente 1013634971 (N), operacion TXH01 con eci=9. Recorrido P7.",
      "Texto IDENTICO al tablero, incluido el parrafo del Regimen de Proteccion al Consumidor Financiero. "
      "AVISO de criterio: esta fila dice 'eCard = false', pero el codigo decide por eci=='9'. Antes si miraba eCard. "
      "Conviene actualizar el criterio de la fila o el codigo, para que digan lo mismo."),
 22: (lit("2.4.0.1.19.2"), KO, "DEFECTO F3-01 y F3-02", "Cliente 1013634972 (O), operacion TXI01. Recorridos P8 y P10.",
      "DOS problemas. (1) El tablero pide DOS lineas de detalle -- 'Transaccion' y 'Monto devuelto: $[valor] el "
      "[DD/MM/AAAA del reverso]' -- y el bot solo entrega la primera. Falta el dato que mas importa al cliente, y no "
      "es redundante: un reverso parcial no coincide con el importe de la compra. (2) Los ** viajan LITERALES: el "
      "cliente lee '**Detalle del reembolso:**'. Ningun otro mensaje del flujo usa Markdown. "
      "AVISO de criterio: la fila dice responseOperati=='Reversado' y el codigo decide por observations que empiece "
      "en 01/02/03/04 con observation_desc que contenga 'aceptada'."),
 23: ("¿Te ha ayudado esta informacion con lo que necesitabas?", OK, VER, "Cliente 1013634972. Recorrido P10.",
      "Salida directa sin guia. Deriva a satisfaction_check."),
 24: (lit("2.4.0.1.19.2.guia", 300), OK, VER, "Cliente 1013634972. Recorrido P8.",
      "AVISO de copy: la fila espera 'Consulta los movimientos de tus productos BBVA desde la app o net' y el bot "
      "responde 'Puedes consultar tus movimientos desde la BBVA net...'. Mismo fondo, distinta forma: confirmar cual manda."),
 25: (lit("2.4.0.1.19.pqr"), BLQ, "DECISION DE NEGOCIO PENDIENTE",
      "Cliente 1013634960 (C), eci=5. Recorrido P9. El texto se entrega correctamente.",
      "EL TEXTO ESTA BIEN; lo que esta en disputa es el CRITERIO, y hay que zanjarlo antes de dar la fila por buena. "
      "Esta fila dice: eci en {vacio,0,1,2,3,7} -> PQR. El codigo hace lo CONTRARIO: ese conjunto va a devolucion. "
      "El tablero dice 'Seran contracargables segun ECI: Contracargo (responsabilidad del comercio): 0,1,2,3,7', y "
      "admite dos lecturas: (a) contracargable = el banco devuelve -> DEVOLUCION, que es lo que hace el codigo hoy; "
      "(b) contracargable = hay que abrir un contracargo formal con el comercio, que exige radicacion -> PQR, que es "
      "lo que dice esta fila y lo que hacia el codigo ANTES del merge. Decision de Luis + Fabian/PO. "
      "Nota: el texto sin tildes ('informacion', 'revision') difiere del tablero, que si las lleva."),
 26: ("Validamos la informacion de tu solicitud y tu caso aplica para la devolucion automatica. Gestionaremos el abono "
      "de tu dinero y te enviaremos la confirmacion a tu correo electronico en un maximo de 10 dias habiles. No "
      "necesitas realizar ningun tramite adicional.\n[Botones: Continuar]",
      BLQ, "DECISION DE NEGOCIO PENDIENTE", "Clientes 1013634970 (eci=0), 1013634961 (eci=1), 10482895 (eci=7).",
      "Mismo criterio en disputa que la fila 21/NO=21: ver esa observacion. El TEXTO coincide con el tablero y los "
      "dias habiles son parametricos (DIAS_HABILES_DEVOLUCION: 10 en local, 40 en el configmap de DEV)."),
 27: ("", NA, "NO VERIFICABLE POR UI", "Back-office: consolidacion diaria 23:45 hacia la ruta del RPA.",
      "Fuera del alcance de la prueba conversacional. Requiere comprobar el fichero generado por el CronJob; "
      "se propone verificarlo en DEV tras el despliegue, no en local."),
 28: ("¿Deseas reportar la siguiente transaccion? -> 'Si, reportar la siguiente' devuelve el flujo a 2.4.0.1.3.",
      OK, VER, "Cliente 1013634961 pidiendo 2 transacciones. Recorrido P2.",
      "IMPORTANTE para quien repita la prueba: el paso 2.4.0.1.20.1 SOLO aparece si al principio se piden 2 o 3 "
      "transacciones. Con 1 el flujo va directo a satisfaccion. Y del .20 al .20.1 hacen falta TRES 'Continuar'."),
 29: (lit("2.4.0.1.20.1") + "\n-> 'No, finalizar' deriva a satisfaction_check.",
      OK, VER, "Cliente 1013634970 pidiendo 2 transacciones. Recorrido P2b.",
      "COPY: el bot dice 'Deseas reportar la siguiente transaccion?' sin signo de apertura ni tildes. "
      "Deberia ser '¿Deseas reportar la siguiente transaccion?'. El resto de su tramo si esta acentuado."),
 30: ("Tras la devolucion, con 1 transaccion pedida, el bot pasa directo a satisfaction_check sin preguntar por mas.",
      OK, VER, "Cliente 1013634970 pidiendo 1 transaccion. Recorrido P1.",
      "Confirmado: no se ofrece el bucle cuando no hay siguiente transaccion que reportar."),
}

def main() -> int:
    wb = openpyxl.load_workbook(XLSX)
    ws = wb["Pruebas Integrales"]
    tocadas = 0
    for fila, (g, h, i, k, l) in DATOS.items():
        resp = str(ws.cell(fila, 3).value or "")
        if "Luis" not in resp:
            print(f"  !! fila {fila} no es de Luis ({resp[:24]!r}): NO se toca")
            continue
        if g:
            ws.cell(fila, 7).value = g
        ws.cell(fila, 8).value = h
        ws.cell(fila, 9).value = i
        ws.cell(fila, 11).value = k
        ws.cell(fila, 12).value = l
        for c in (7, 11, 12):
            ws.cell(fila, c).alignment = openpyxl.styles.Alignment(wrap_text=True, vertical="top")
        tocadas += 1
    wb.save(XLSX)
    print(f"\n{tocadas} filas de Luis rellenadas en {XLSX}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
