// Formato de la hoja de cuadre Credibanco tal como la diligencia Operaciones
// (archivo "Cuadre credibanco 131126.xlsx", hoja 131126): filas en orden,
// secciones, subtotales con sus fórmulas, TOTAL (fila 211) y DIFERENCIA (212).
// Generado desde ese Excel; solo columnas B (cuenta), C (concepto), D (NIT),
// las fórmulas de F/G de subtotales y la nota de la columna H.
// eslint-disable-next-line no-unused-vars
const PLANTILLA_MAESTRA_LAYOUT = Object.freeze({
  fuente: 'Cuadre credibanco 131126.xlsx · hoja 131126',
  filas: [
    {
      "fila": 1,
      "tipo": "titulo",
      "concepto": "CONTABILIDAD CANJE NACIONAL RECIBIDO Y ENVIADO"
    },
    {
      "fila": 3,
      "tipo": "seccion",
      "concepto": "CUADRE CANJE ENVIADO"
    },
    {
      "fila": 4,
      "tipo": "linea",
      "cuenta": "196095001035",
      "concepto": "017- VR. COMPENSACION BBVA",
      "nota": "Se extrae de 3270 HA26: columna F = crédito (h) y columna G = débito (D) del concepto Credibanco."
    },
    {
      "fila": 5,
      "tipo": "linea",
      "cuenta": "196095001063",
      "concepto": "017- VR. COMPENSACION VISA",
      "nota": "F5 = N171: compensación VISA calculada en la liquidación VISA."
    },
    {
      "fila": 6,
      "tipo": "linea",
      "cuenta": "299095107",
      "concepto": "017- PAGOS EFECTUADOS CENTRO 0",
      "nota": "04 ORIGINAL PAGOS Se extrae de la carta de compensación hoja CAI160"
    },
    {
      "fila": 7,
      "tipo": "linea",
      "cuenta": "196095001850",
      "concepto": "017- CJE ENV AVANCE TC AJENA TF Y MP47 NAL -MP2"
    },
    {
      "fila": 8,
      "tipo": "linea",
      "cuenta": "196095001851",
      "concepto": "017- CJE ENV DEV AVANC MP47 TC BBVA EN LA RED -MP2"
    },
    {
      "fila": 9,
      "tipo": "linea",
      "cuenta": "299095843",
      "concepto": "017- VR. COMPENSACION BBVA",
      "nota": "COMISION INTEROPERABILI. ATM se extrae carta de compensacion"
    },
    {
      "fila": 10,
      "tipo": "linea",
      "cuenta": "196095001853",
      "concepto": "017- CJE ENV REPRESENT MP47 AVANCE TC AJENA OF BBVA -MP2"
    },
    {
      "fila": 11,
      "tipo": "linea",
      "cuenta": "196095001854",
      "concepto": "017- CJE ENV DEV A ENT ADQUIRENT PGO TC BBVA EN MP47 -MP2"
    },
    {
      "fila": 12,
      "tipo": "linea",
      "cuenta": "196095001855",
      "concepto": "017- CANJE ENV REV PGOS TC AJENA POR MP47-MP2 COD24"
    },
    {
      "fila": 13,
      "tipo": "linea",
      "cuenta": "196095001856",
      "concepto": "017- CANJE ENV REPRESENTACIONPGOS POR MP47 -MP2"
    },
    {
      "fila": 14,
      "tipo": "linea",
      "cuenta": "196095001847",
      "concepto": "017- CANJE ENVIADO AMEX NACIONAL HA32"
    },
    {
      "fila": 15,
      "tipo": "linea",
      "cuenta": "196095001857",
      "concepto": "017- CANJE ENV VENTAS NAL EN TF Y MP47 HA26"
    },
    {
      "fila": 16,
      "tipo": "linea",
      "cuenta": "196095001859",
      "concepto": "017- CANJE ENV DEVOLUCION VENTAS 16-MP2 HA26",
      "nota": "DEVOLUCION VENTAS Se extrae de la carta de compensación hoja CAI160"
    },
    {
      "fila": 17,
      "tipo": "linea",
      "cuenta": "196095001859",
      "concepto": "017- CANJE ENV DEVOLUCION VENTAS 16-MP2 HA26",
      "nota": "DEVOLUCION VENTAS Se extrae de la carta de compensación hoja CAI160"
    },
    {
      "fila": 18,
      "tipo": "linea",
      "cuenta": "196095001859",
      "concepto": "017- CANJE ENV DEVOLUCION VENTAS 16-MP2 HA26",
      "nota": "DEVOLUCION VENTAS Se extrae de la carta de compensación hoja CAI160"
    },
    {
      "fila": 19,
      "tipo": "linea",
      "cuenta": "196095001859",
      "concepto": "017- CANJE ENV DEVOLUCION VENTAS 16-MP2 HA26"
    },
    {
      "fila": 20,
      "tipo": "linea",
      "cuenta": "196095001859",
      "concepto": "017- CANJE ENV DEVOLUCION VENTAS 16-MP2 HA26"
    },
    {
      "fila": 21,
      "tipo": "linea",
      "cuenta": "196095001859",
      "concepto": "017- CANJE ENV DEVOLUCION VENTAS 16-MP2 HA26"
    },
    {
      "fila": 22,
      "tipo": "linea",
      "cuenta": "196095001859",
      "concepto": "017- CANJE ENV DEVOLUCION VENTAS 16-MP2 HA26"
    },
    {
      "fila": 23,
      "tipo": "linea",
      "cuenta": "196095001859",
      "concepto": "017- CANJE ENV DEVOLUCION VENTAS 16-MP2 HA26"
    },
    {
      "fila": 24,
      "tipo": "linea",
      "cuenta": "196095001860",
      "concepto": "017- CJE ENVIADO VISA REV VENTAS 26-MP2"
    },
    {
      "fila": 25,
      "tipo": "linea",
      "cuenta": "411514005",
      "concepto": "017-TII RECIBIDA EMISOR VISA OP REVER VENTAS"
    },
    {
      "fila": 26,
      "tipo": "linea",
      "cuenta": "196095001861",
      "concepto": "017- CANJE ENV REPRESENTACION VENTAS 36 -MP2",
      "nota": "36 REPRESENT VENTAS Se extrae de la carta de compensación hoja CAI160"
    },
    {
      "fila": 27,
      "tipo": "linea",
      "cuenta": "196095001864",
      "concepto": "017- CJE ENV TX 26 AMEX -MP2"
    },
    {
      "fila": 28,
      "tipo": "linea",
      "cuenta": "299095833",
      "concepto": "017- CJE ENV REVERSION AVANCE HA26 22"
    },
    {
      "fila": 29,
      "tipo": "linea",
      "cuenta": "196095001221",
      "concepto": "017- ORIGINAL REEMBOLSO",
      "nit": "90",
      "nota": "08 ORIGINAL REEMBOLSO Se extrae de la carta de compensación hoja CAI160"
    },
    {
      "fila": 30,
      "tipo": "linea",
      "cuenta": "299095817",
      "concepto": "017- ASC -CANJE ENVI. ADQUIRENTE- BINES NAL T. I.-MP"
    },
    {
      "fila": 31,
      "tipo": "linea",
      "cuenta": "196095001847",
      "concepto": "017- CANJE ENVIADO AMEX NACIONAL"
    },
    {
      "fila": 32,
      "tipo": "linea",
      "cuenta": "196095001848",
      "concepto": "017- CANJE ENVIADO AMEX INTERNACIONAL"
    },
    {
      "fila": 33,
      "tipo": "linea",
      "cuenta": "196095001814",
      "concepto": "017- VR. CANJE ENVIADO AVANCES OTROS BAN"
    },
    {
      "fila": 34,
      "tipo": "linea",
      "cuenta": "196095001865",
      "concepto": "017- CANJE ENV REPRESENTACION VENTAS 36 -MP2"
    },
    {
      "fila": 35,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017-TP 12 DEVO AVANCE",
      "nota": "si esta positivo se alerta (cuenta 419595025 )"
    },
    {
      "fila": 36,
      "tipo": "linea",
      "cuenta": "299095108",
      "concepto": "017- ASCR-CNJE ENV.ADQ BNS INTNAL PGOS"
    },
    {
      "fila": 37,
      "tipo": "linea",
      "cuenta": "411514003",
      "concepto": "017- VR COMISION ADQUIRENCIA"
    },
    {
      "fila": 38,
      "tipo": "linea",
      "cuenta": "419595021",
      "concepto": "017- VR PROCESO CANJE NACIONAL"
    },
    {
      "fila": 39,
      "tipo": "linea",
      "cuenta": "519030008",
      "concepto": "017- VR. FINANCIACION POR CANJE ENVIADO",
      "nota": "VALIDACION CJE ENVIADO"
    },
    {
      "fila": 40,
      "tipo": "linea",
      "cuenta": "419595023",
      "concepto": "017- VR. CTA FOTOCOPIAS CREDIBANCO"
    },
    {
      "fila": 41,
      "tipo": "linea",
      "cuenta": "419595022",
      "concepto": "017- CTA DE RED CANJE NACIONAL"
    },
    {
      "fila": 42,
      "tipo": "subtotal",
      "concepto": "CUADRE CANJE MANUAL",
      "fF": "=SUM(F6:F41)",
      "fG": "=SUM(G6:G41)"
    },
    {
      "fila": 43,
      "tipo": "linea",
      "cuenta": "196095001221",
      "concepto": "017- EXTRACOMPENSACION VISA",
      "nit": "14"
    },
    {
      "fila": 44,
      "tipo": "linea",
      "cuenta": "196095001848",
      "concepto": "017- VOU AMEX",
      "nit": "14"
    },
    {
      "fila": 45,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017- MOV. INCOMING NACIONAL",
      "nit": "76"
    },
    {
      "fila": 46,
      "tipo": "linea",
      "cuenta": "411595196",
      "concepto": "017- DIF TASA TIPO CAMBIO VISA"
    },
    {
      "fila": 47,
      "tipo": "linea",
      "cuenta": "419595025",
      "concepto": "017- VR. FINANCIACION POR CANJE ENVIADO"
    },
    {
      "fila": 48,
      "tipo": "linea",
      "cuenta": "519095145",
      "concepto": "017- DIF TASA DE CAMBIO RED (EXTRACOM)",
      "nota": "reemplazar si es crdito por cuenta 411595196"
    },
    {
      "fila": 49,
      "tipo": "linea",
      "cuenta": "196095001839",
      "concepto": "017-depos inter master credibanco",
      "nota": "VALOR AMEX CAI 250"
    },
    {
      "fila": 50,
      "tipo": "linea",
      "cuenta": "196095001839",
      "concepto": "017-Dif depos inter master credibanco",
      "nota": "VALOR CANJE MANUAL"
    },
    {
      "fila": 51,
      "tipo": "linea",
      "cuenta": "411514023",
      "concepto": "017-CARGO STANDARD RATE AJUSTE AMEX",
      "nota": "DIF:"
    },
    {
      "fila": 52,
      "tipo": "linea",
      "cuenta": "196095001839",
      "concepto": "017- DEPOSITOS ELECTRONICOS AMERICAN EXPRESS"
    },
    {
      "fila": 53,
      "tipo": "linea",
      "cuenta": "519030011",
      "concepto": "017- VR RED, PROCESO CANJE INTERNACIONAL"
    },
    {
      "fila": 54,
      "tipo": "linea",
      "cuenta": "196095001839",
      "concepto": "DCC ORIGINAL SALE"
    },
    {
      "fila": 55,
      "tipo": "linea",
      "cuenta": "519095067",
      "concepto": "017- VR. COBRO (DOC DEP )FOTOCO DEP. ELECTR."
    },
    {
      "fila": 56,
      "tipo": "subtotal",
      "concepto": "CUADRE CANJE ELECTRONICO",
      "fF": "=SUM(F43:F55)",
      "fG": "=SUM(G43:G55)"
    },
    {
      "fila": 57,
      "tipo": "linea",
      "cuenta": "299095302",
      "concepto": "017-CANJE RECIBIDO TARJETA CREDITO"
    },
    {
      "fila": 58,
      "tipo": "linea",
      "cuenta": "299095302",
      "concepto": "017-CANJE RECIBIDO TARJETA CREDITO PAGOS",
      "nota": "VALI CTA 302 HA 32"
    },
    {
      "fila": 59,
      "tipo": "linea",
      "cuenta": "299095302",
      "concepto": "017-CANJE RECIBIDO TARJETA CREDITO REVERSION VENTAS 26 VLR. TOTAL"
    },
    {
      "fila": 60,
      "tipo": "linea",
      "cuenta": "299095302",
      "concepto": "017-ORIGINAL REEMBOLSOS CREDITO"
    },
    {
      "fila": 61,
      "tipo": "linea",
      "cuenta": "299095302",
      "concepto": "017-CANJE RECIBIDO TC REVERSION AVANCES 22"
    },
    {
      "fila": 62,
      "tipo": "linea",
      "cuenta": "299095302",
      "concepto": "017-CANJE RECIBIDO TC REVERSION PAGOS 24"
    },
    {
      "fila": 63,
      "tipo": "linea",
      "cuenta": "299095302",
      "concepto": "CANJE RECIBIDO TAR"
    },
    {
      "fila": 64,
      "tipo": "linea",
      "cuenta": "411514005",
      "concepto": "TII RECIBIDA EMISO"
    },
    {
      "fila": 65,
      "tipo": "linea",
      "cuenta": "196095001830",
      "concepto": "017-RECH CJE RECIBIDO NAL TC PMPD1322"
    },
    {
      "fila": 66,
      "tipo": "linea",
      "cuenta": "299095301",
      "concepto": "017-CANJE RECIBIDO TARJETA DEBITO"
    },
    {
      "fila": 67,
      "tipo": "linea",
      "cuenta": "299095301",
      "concepto": "017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES"
    },
    {
      "fila": 68,
      "tipo": "linea",
      "cuenta": "299095301",
      "concepto": "017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES PAGOS"
    },
    {
      "fila": 69,
      "tipo": "linea",
      "cuenta": "299095301",
      "concepto": "017-ORIGINAL REEMBOLSOS DEBITO",
      "nit": "69"
    },
    {
      "fila": 70,
      "tipo": "linea",
      "cuenta": "196095001770",
      "concepto": "017-OP CNBS"
    },
    {
      "fila": 71,
      "tipo": "linea",
      "cuenta": "196095001813",
      "concepto": "017-NOTAS DEBITO CANJE RECIBIDO"
    },
    {
      "fila": 72,
      "tipo": "linea",
      "cuenta": "259095170",
      "concepto": "017-VISA PAGOS"
    },
    {
      "fila": 73,
      "tipo": "linea",
      "cuenta": "259095341",
      "concepto": "017-CANJE UTILIZACION VISA VALE"
    },
    {
      "fila": 74,
      "tipo": "linea",
      "cuenta": "299095013",
      "concepto": "017-ORIGINAL PAGOS A TARJETAS DEBITO",
      "nit": "14"
    },
    {
      "fila": 75,
      "tipo": "linea",
      "cuenta": "299095300",
      "concepto": "017-COMISIONES EXIT. TARJETA DEBITO ONLINE"
    },
    {
      "fila": 76,
      "tipo": "linea",
      "cuenta": "299095300",
      "concepto": "017-COMISIONES EXIT. TARJETA DEBITO $1800 DIFE CONTA"
    },
    {
      "fila": 77,
      "tipo": "linea",
      "cuenta": "196095001814",
      "concepto": "017-RECHAZOS CANJE RECIBIDO NACIONAL VTA",
      "nit": "14"
    },
    {
      "fila": 78,
      "tipo": "linea",
      "cuenta": "196095001814",
      "concepto": "017-RECHAZOS CANJE RECIBIDO NACIONAL PAGO",
      "nit": "14"
    },
    {
      "fila": 79,
      "tipo": "linea",
      "cuenta": "196095001813",
      "concepto": "017-DEVOLUCION VTA NAL",
      "nit": "87",
      "nota": "MODIFICAR AL VALOR TOTAL"
    },
    {
      "fila": 80,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017-REPRESENTACION VENTA NAL (CENTRO 730)",
      "nit": "98"
    },
    {
      "fila": 81,
      "tipo": "linea",
      "cuenta": "411514023",
      "concepto": "017-T.I CONTRACARGOS ADQ",
      "nota": "411514023-se modifica en la CM a 411514024"
    },
    {
      "fila": 82,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017-SOLICITUD COPIAS"
    },
    {
      "fila": 83,
      "tipo": "linea",
      "cuenta": "299095843",
      "concepto": "017-CJE REC VISA NAL VR COM EXIT TC BATC"
    },
    {
      "fila": 84,
      "tipo": "linea",
      "cuenta": "299095880",
      "concepto": "017-CANJE RECIBIDO TARJETA DEBITO REGALO"
    },
    {
      "fila": 85,
      "tipo": "linea",
      "cuenta": "299095880",
      "concepto": "017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES REGALO"
    },
    {
      "fila": 86,
      "tipo": "linea",
      "cuenta": "511520026",
      "concepto": "017-RETIROS ATMS -USO RED - EFIPAGOS-MPP"
    },
    {
      "fila": 87,
      "tipo": "linea",
      "cuenta": "299095303",
      "concepto": "017-CJE REC VISA NAL VR COMIS"
    },
    {
      "fila": 88,
      "tipo": "linea",
      "cuenta": "411514005",
      "concepto": "017- TII CNBS"
    },
    {
      "fila": 89,
      "tipo": "linea",
      "cuenta": "411514005",
      "concepto": "017-TII RECIBIDA EMISOR VISA OP REVER VENTAS",
      "nota": "VALIDACION CANJE ELEC"
    },
    {
      "fila": 90,
      "tipo": "linea",
      "cuenta": "299095839",
      "concepto": "017-COMISIONES NO EXITOSAS TD Y TC (CMI)"
    },
    {
      "fila": 91,
      "tipo": "linea",
      "cuenta": "299095301",
      "concepto": "017-DEBITO CLASSIC-GOLD BBVA"
    },
    {
      "fila": 92,
      "tipo": "linea",
      "cuenta": "299095843",
      "concepto": "017-COMISIONES NO EXITOSAS TD Y TC IMPUTABLES BANCO"
    },
    {
      "fila": 93,
      "tipo": "linea",
      "cuenta": "299095843",
      "concepto": "017-COMISIONES NO EXITOSAS TD Y TC TIPO 15 Y 16"
    },
    {
      "fila": 94,
      "tipo": "linea",
      "cuenta": "519030009",
      "concepto": "017-CUOTA DE PROCESO CANJE NAL"
    },
    {
      "fila": 95,
      "tipo": "linea",
      "cuenta": "519030008",
      "concepto": "017-CUOTA DE FINANCIACION CANJE NAL"
    },
    {
      "fila": 96,
      "tipo": "linea",
      "cuenta": "419595025",
      "concepto": "017- VR. FINANCIACION POR CANJE ENVIADO"
    },
    {
      "fila": 97,
      "tipo": "linea",
      "cuenta": "519030010",
      "concepto": "017-CUOTA RED CANJE NACIONAL"
    },
    {
      "fila": 98,
      "tipo": "subtotal",
      "concepto": "TOTAL CANJE RECIBIDO",
      "fF": "=SUM(F57:F97)",
      "fG": "=SUM(G57:G97)"
    },
    {
      "fila": 99,
      "tipo": "subtotal",
      "concepto": "CUADRE CANJE DEPOSITOS",
      "fF": "=+F98+F56+F42",
      "fG": "=+G98+G56+G42"
    },
    {
      "fila": 100,
      "tipo": "linea",
      "cuenta": "196095001838",
      "concepto": "017-VR. DEPOSITOS ELECTRONICOS NAL CONSIGNADOS"
    },
    {
      "fila": 101,
      "tipo": "linea",
      "cuenta": "196095001838",
      "concepto": "017-VR. REVERSIONES D.E. NACIONAL"
    },
    {
      "fila": 102,
      "tipo": "linea",
      "cuenta": "196095001838",
      "concepto": "DIF DEPO ELECTRO",
      "nota": "VALIDACION DEPOSITOS"
    },
    {
      "fila": 103,
      "tipo": "linea",
      "cuenta": "299095037",
      "concepto": "017-RECHAZOS DEPOSITOS ELECTRONICOS NAL",
      "nit": "17"
    },
    {
      "fila": 104,
      "tipo": "linea",
      "cuenta": "299095037",
      "concepto": "017-RECHAZOS DEPOSITOS ELECTRONICOS INT",
      "nit": "17"
    },
    {
      "fila": 105,
      "tipo": "linea",
      "cuenta": "299095037",
      "concepto": "017-RECHAZOS DEPOSITOS ELECTRONICOS NAL 26",
      "nit": "17"
    },
    {
      "fila": 106,
      "tipo": "linea",
      "cuenta": "299095037",
      "concepto": "017-RECHAZOS DEPOSITOS ELECTRONICOS INT 26",
      "nit": "17"
    },
    {
      "fila": 107,
      "tipo": "linea",
      "cuenta": "196095001839",
      "concepto": "017-VR. REVERSIONES D.E. INTERNACIONAL"
    },
    {
      "fila": 108,
      "tipo": "linea",
      "cuenta": "196095001839",
      "concepto": "017-VR. DEPOSITOS ELECTRONICOS INT CONSIGNADOS"
    },
    {
      "fila": 109,
      "tipo": "linea",
      "cuenta": "196095001884",
      "concepto": "017-VR. RET ATMs ADQUIRIENTES EN BBV NAL"
    },
    {
      "fila": 110,
      "tipo": "linea",
      "concepto": "017- CNB"
    },
    {
      "fila": 111,
      "tipo": "linea",
      "cuenta": "411514023",
      "concepto": "017-ASC - T. I.-MP TII NAL RECHAZOS"
    },
    {
      "fila": 112,
      "tipo": "linea",
      "cuenta": "299095882",
      "concepto": "017-ASC - T. I.-MP TII NAL RECHAZOS"
    },
    {
      "fila": 113,
      "tipo": "linea",
      "cuenta": "299095882",
      "concepto": "017-ASC -CANJE ENVI. ADQUIRENTE- BINES NAL T. I.-MP TII NAL"
    },
    {
      "fila": 114,
      "tipo": "linea",
      "cuenta": "299095888",
      "concepto": "017-TASA INTERBAN TD-TC D.E. VISA TII INTER"
    },
    {
      "fila": 115,
      "tipo": "linea",
      "cuenta": "411514023",
      "concepto": "017- VR RED, PROCESO CANJE INTERNACIONAL"
    },
    {
      "fila": 116,
      "tipo": "linea",
      "cuenta": "196095001839",
      "concepto": "017-TII AMEX INTERNACIONAL"
    },
    {
      "fila": 117,
      "tipo": "linea",
      "cuenta": "196095001918",
      "concepto": "017-VR. COMISIONES ADQ EN ATMs BBV $3.088"
    },
    {
      "fila": 118,
      "tipo": "linea",
      "cuenta": "196095001918",
      "concepto": "017-VR. COMISIONES ADQ EN ATMs BBV $3.088"
    },
    {
      "fila": 119,
      "tipo": "linea",
      "cuenta": "196095001918",
      "concepto": "017-VR. COMISIONES ADQ EN ATMs BBV $3.088"
    },
    {
      "fila": 120,
      "tipo": "linea",
      "cuenta": "196095001918",
      "concepto": "017-VR. COMISIONES ADQ EN ATMs BBV $3.088"
    },
    {
      "fila": 121,
      "tipo": "linea",
      "cuenta": "196095001918",
      "concepto": "017-VR. COMISIONES ADQ EN ATMs BBV $3.088"
    },
    {
      "fila": 122,
      "tipo": "linea",
      "cuenta": "411595191",
      "concepto": "017-VR. COMISIONES ADQ EN ATMs BBV $3.088",
      "nit": "33"
    },
    {
      "fila": 123,
      "tipo": "subtotal",
      "concepto": "TOTAL DEPOSITOS ELECTRONICOS",
      "fF": "=SUM(F100:F122)",
      "fG": "=SUM(G100:G122)"
    },
    {
      "fila": 126,
      "tipo": "seccion",
      "concepto": "CUADRE CANJE INTERNACIONAL"
    },
    {
      "fila": 127,
      "tipo": "linea",
      "cuenta": "196095001862",
      "concepto": "017- CJE ENV AVANC TC AJENA TF Y MP47 INTERNAL -MP2 (BAI 183 BIN 454100)",
      "nota": "MANUAL CASH"
    },
    {
      "fila": 128,
      "tipo": "linea",
      "cuenta": "196095001885",
      "concepto": "017-CANJE INTERNACIONAL ADQ. EN ATMs BBV (BAI 183 BIN 454100)",
      "nota": "ATM CASH"
    },
    {
      "fila": 129,
      "tipo": "linea",
      "cuenta": "196095001839",
      "concepto": "017- CANJE INTERNAL ENVIADO DEPOS ELECT (BAI 183 BIN 454100)",
      "nota": "PURCHASE"
    },
    {
      "fila": 131,
      "tipo": "linea",
      "cuenta": "196095001858",
      "concepto": "017- CANJE ENVIADO INTERNAL VENTAS 06-MP2",
      "nota": "* No enviar debitos. Se dejan 2 días y se cruza la Ref"
    },
    {
      "fila": 132,
      "tipo": "linea",
      "cuenta": "196095001839",
      "concepto": "017- 858 CANJE INTERNAL ENVIADO DEPOS ELECT"
    },
    {
      "fila": 133,
      "tipo": "linea",
      "cuenta": "196095001815",
      "concepto": "017-VISA REPRESENTACIONES BIN 454100",
      "nit": "76"
    },
    {
      "fila": 134,
      "tipo": "linea",
      "cuenta": "196095001815",
      "concepto": "017-VISA REPRESENTACIONES BIN 454100",
      "nit": "86"
    },
    {
      "fila": 135,
      "tipo": "subtotal",
      "concepto": "TOTAL CANJE INTERNAL ENVIADO",
      "fF": "=SUM(F127:F134)",
      "fG": "=SUM(G127:G134)"
    },
    {
      "fila": 136,
      "tipo": "linea",
      "cuenta": "299095408",
      "concepto": "017- CANJE RECIBIDO INTERNACIONAL (BAI185)"
    },
    {
      "fila": 137,
      "tipo": "linea",
      "cuenta": "299095408",
      "concepto": "017- RECH CANJE RECIBIDO INTERNACIONAL (RECHAZOS)",
      "nota": "COMPRA"
    },
    {
      "fila": 138,
      "tipo": "linea",
      "cuenta": "196095001814",
      "concepto": "017- RECHAZOS CANJE INTERNACIONAL RECIB.",
      "nit": "15"
    },
    {
      "fila": 139,
      "tipo": "linea",
      "cuenta": "196095001830",
      "concepto": "017-RECH CJE RECIBIDO NAL TC PMPD 1322"
    },
    {
      "fila": 140,
      "tipo": "linea",
      "cuenta": "196095001830",
      "concepto": "017-RECH CJE RECIBIDO NAL TC PMPD 1322"
    },
    {
      "fila": 141,
      "tipo": "linea",
      "cuenta": "196095001830",
      "concepto": "017-RECH CJE RECIBIDO NAL TD 404279 PMPD1322"
    },
    {
      "fila": 142,
      "tipo": "linea",
      "cuenta": "196095001830",
      "concepto": "017-RECH CJE RECIBIDO NAL TD 492468 PMPD1322",
      "nota": "VENTA"
    },
    {
      "fila": 143,
      "tipo": "linea",
      "cuenta": "196095001830",
      "concepto": "017-RECH CJE RECIBIDO NAL TD 491268 PMPD1322"
    },
    {
      "fila": 144,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017- REPRE VISA TC",
      "nit": "91"
    },
    {
      "fila": 145,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017- REPRE VISA TC",
      "nit": "91"
    },
    {
      "fila": 146,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017- REPRE VISA TC",
      "nit": "91"
    },
    {
      "fila": 147,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017- REPRE VISA TC",
      "nit": "91"
    },
    {
      "fila": 148,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017- REPRE VISA TC",
      "nit": "91",
      "nota": "DEBIT"
    },
    {
      "fila": 149,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017- REPRE VISA TC",
      "nit": "91",
      "nota": "EMPRES"
    },
    {
      "fila": 150,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017- REPRE VISA TD 404279",
      "nit": "91",
      "nota": "ELECTRON"
    },
    {
      "fila": 151,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017- REPRE VISA TD 492868",
      "nit": "91"
    },
    {
      "fila": 152,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017- REPRE VISA TD 491268",
      "nit": "91"
    },
    {
      "fila": 153,
      "tipo": "linea",
      "cuenta": "196095001862",
      "concepto": "017- CJE ENV AVANC TC AJENA TF Y MP47 INTERNAL -MP2"
    },
    {
      "fila": 154,
      "tipo": "linea",
      "cuenta": "299095818",
      "concepto": "017- TASA INTERBANCARIA INTERNACIONAL"
    },
    {
      "fila": 155,
      "tipo": "linea",
      "cuenta": "196095001770",
      "concepto": "017- CANCELACION PROVISIONAL",
      "nit": "45"
    },
    {
      "fila": 156,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017-VISA CONTRACARGOS EMISOR TC"
    },
    {
      "fila": 157,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017-VISA CONTRACARGOS EMISOR TC"
    },
    {
      "fila": 158,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017-VISA CONTRACARGOS EMISOR TC"
    },
    {
      "fila": 159,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017-VISA CONTRACARGOS EMISOR TC"
    },
    {
      "fila": 160,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017-VISA CONTRACARGOS EMISOR TC"
    },
    {
      "fila": 161,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017-VISA CONTRACARGOS EMISOR TC"
    },
    {
      "fila": 162,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017-VISA CONTRACARGOS EMISOR TC",
      "nota": "VALIDACION CANJE INTERNACIONAL"
    },
    {
      "fila": 163,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017-VISA CONTRACARGOS EMISOR TC"
    },
    {
      "fila": 164,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017-VISA CONTRACARGOS EMISOR TC"
    },
    {
      "fila": 165,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017-VISA CONTRACARGOS EMISOR DIFERENTE 491268"
    },
    {
      "fila": 166,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017-VISA CONTRACARGOS EMISOR DIFERENTE 491268"
    },
    {
      "fila": 167,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017-VISA CONTRACARGOS EMISOR DIFERENTE 492468"
    },
    {
      "fila": 168,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017-VISA CONTRACARGOS EMISOR DIFERENTE 492468"
    },
    {
      "fila": 169,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017-VISA CONTRACARGOS EMISOR DIFERENTE 404279"
    },
    {
      "fila": 170,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017-VISA CONTRACARGOS EMISOR DIFERENTE 404279",
      "nota": "la diferencia(pequeña) va la la cuenta 51903011 en la primer cuenta y se le suma"
    },
    {
      "fila": 171,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017-VISA CONTRACARGOS EMISOR DIFERENTE 404279"
    },
    {
      "fila": 172,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017-VISA CONTRACARGOS EMISOR DIFERENTE 404279"
    },
    {
      "fila": 173,
      "tipo": "linea",
      "cuenta": "196095001815",
      "concepto": "017-VISA CONTRACARGOS ADQUIRENTES BIN 454100",
      "nit": "72"
    },
    {
      "fila": 174,
      "tipo": "linea",
      "cuenta": "196095001815",
      "concepto": "017-VISA CONTRACARGOS ADQUIRENTES BIN 454100",
      "nit": "72"
    },
    {
      "fila": 175,
      "tipo": "linea",
      "cuenta": "196095001815",
      "concepto": "017-VISA CONTRACARGOS ADQUIRENTES BIN 454100",
      "nit": "72"
    },
    {
      "fila": 176,
      "tipo": "linea",
      "cuenta": "196095001815",
      "concepto": "017-VISA CONTRACARGOS ADQUIRENTES BIN 454100",
      "nit": "72"
    },
    {
      "fila": 177,
      "tipo": "linea",
      "cuenta": "196095001815",
      "concepto": "017-VISA CONTRACARGOS ADQUIRENTES BIN 454100",
      "nit": "86"
    },
    {
      "fila": 178,
      "tipo": "linea",
      "cuenta": "196095001815",
      "concepto": "017-VISA CONTRACARGOS ADQUIRENTES BIN 454100",
      "nit": "72"
    },
    {
      "fila": 179,
      "tipo": "linea",
      "cuenta": "196095001815",
      "concepto": "017-VISA REVERSION CONTRACARGOS ADQUIRENTES BIN 454100",
      "nit": "78"
    },
    {
      "fila": 180,
      "tipo": "linea",
      "cuenta": "196095001815",
      "concepto": "017-VISA REVERSION CONTRACARGOS ADQUIRENTES BIN 454100",
      "nit": "78"
    },
    {
      "fila": 181,
      "tipo": "linea",
      "cuenta": "411595196",
      "concepto": "DIF CAMBIO COMP VISA"
    },
    {
      "fila": 182,
      "tipo": "linea",
      "cuenta": "519095145",
      "concepto": "DIF CAMBIO COMP VISA"
    },
    {
      "fila": 183,
      "tipo": "linea",
      "cuenta": "523095003",
      "concepto": "017- DESCONEXIONES TECNICAS CREDIBA"
    },
    {
      "fila": 184,
      "tipo": "linea",
      "cuenta": "196095001885",
      "concepto": "017- FEE COLLECT 454100 BAI 135 - BAI 137 CANJE INTERNACIONAL ADQ. EN ATMs BBV"
    },
    {
      "fila": 185,
      "tipo": "linea",
      "cuenta": "196095001885",
      "concepto": "017- FUNDS DISBURSE 454100 BAI 135 - BAI 137 CANJE INTERNACIONAL ADQ. EN ATMs BBV"
    },
    {
      "fila": 186,
      "tipo": "linea",
      "cuenta": "411514028",
      "concepto": "017- INGRESOS TJ CREDITO"
    },
    {
      "fila": 187,
      "tipo": "linea",
      "cuenta": "411514027",
      "concepto": "017- INGRESOS TJ DEBITO"
    },
    {
      "fila": 188,
      "tipo": "linea",
      "cuenta": "411514023",
      "concepto": "017- TII INTERNACIONAL VISA"
    },
    {
      "fila": 189,
      "tipo": "linea",
      "cuenta": "511595147",
      "concepto": "017- GASTOS TARJETA CREDITO"
    },
    {
      "fila": 190,
      "tipo": "linea",
      "cuenta": "511595148",
      "concepto": "017- GASTOS TARJETA DEBITO"
    },
    {
      "fila": 191,
      "tipo": "linea",
      "cuenta": "511595034",
      "concepto": "017- FEE COLLECT"
    },
    {
      "fila": 192,
      "tipo": "linea",
      "cuenta": "299095038",
      "concepto": "017- FUNDS DISBURSE"
    },
    {
      "fila": 193,
      "tipo": "linea",
      "cuenta": "196095001815",
      "concepto": "017- REPRE TC 20",
      "nit": "71"
    },
    {
      "fila": 194,
      "tipo": "linea",
      "cuenta": "419595006",
      "concepto": "017- VR. FINANCIACION CANJE INTERNACIONAL (CR BAI185)"
    },
    {
      "fila": 195,
      "tipo": "linea",
      "cuenta": "519030011",
      "concepto": "017- VR RED, PROCESO CANJE INTERNACIONAL (BD BAI185)"
    },
    {
      "fila": 196,
      "tipo": "linea",
      "cuenta": "196095001221",
      "concepto": "017- MERCHANDISE CREDIT",
      "nit": "14"
    },
    {
      "fila": 197,
      "tipo": "linea",
      "cuenta": "196095001839",
      "concepto": "DCC ORIGINAL SALE"
    },
    {
      "fila": 198,
      "tipo": "linea",
      "cuenta": "299095409",
      "concepto": "017- VR COMISION 1.5% OPERATIVA DE RED CXP",
      "nota": "VALIDAR CUENTA"
    },
    {
      "fila": 199,
      "tipo": "linea",
      "cuenta": "519030011",
      "concepto": "017- VR RED, PROCESO CJE INTER REINTEGRO 1% COMISION OP RED"
    },
    {
      "fila": 200,
      "tipo": "linea",
      "cuenta": "519030011",
      "concepto": "017- VR RED, PROCESO CJE INTER REINTEGRO 1.9% COMISION OP RED"
    },
    {
      "fila": 201,
      "tipo": "linea",
      "cuenta": "299095400",
      "concepto": "017- VR. TARJETA DEBIT EN EL EXTERIOR-404279 (BAI 183 BINES DB)"
    },
    {
      "fila": 202,
      "tipo": "linea",
      "cuenta": "299095400",
      "concepto": "017- VR. TARJETA ELECT EMPRES EN EL EXTERIOR-492468 (BAI 183 BINES DB)"
    },
    {
      "fila": 203,
      "tipo": "linea",
      "cuenta": "299095400",
      "concepto": "017- VR. TARJETA ELECTRON EN EL EXTERIOR 491268 (BAI 183 BINES DB)"
    },
    {
      "fila": 204,
      "tipo": "linea",
      "cuenta": "299095400",
      "concepto": "017- VR. TARJETA ELECTRON EN EL EXTERIOR 459317 (BAI 183 BINES DB)"
    },
    {
      "fila": 205,
      "tipo": "linea",
      "cuenta": "299095400",
      "concepto": "017- VR. TARJETA ELECTRON EN EL EXTERIOR 418253 (BAI 183 BINES DB)"
    },
    {
      "fila": 206,
      "tipo": "linea",
      "cuenta": "299095400",
      "concepto": "017- VR. TARJETA ELECTRON EN EL EXTERIOR 432346 (BAI 183 BINES DB)"
    },
    {
      "fila": 207,
      "tipo": "linea",
      "cuenta": "419595022",
      "concepto": "017- APROVECHAMIENTOS DIFERENCIA TASA DE CAMBIO"
    },
    {
      "fila": 208,
      "tipo": "subtotal",
      "concepto": "TOTAL CANJE INTERNAL RECIBIDO",
      "fF": "=SUM(F136:F207)",
      "fG": "=SUM(G136:G207)"
    },
    {
      "fila": 209,
      "tipo": "subtotal",
      "concepto": "TOTAL CANJE INTERNAL ENVIADO Y RECIBIDO",
      "fF": "=+F208+F135",
      "fG": "=+G208+G135"
    },
    {
      "fila": 211,
      "tipo": "total",
      "concepto": "TOTAL",
      "fF": "=+F209+F123+F99+F4+F5",
      "fG": "=+G209+G123+G99+G4+G5"
    },
    {
      "fila": 212,
      "tipo": "diferencia",
      "concepto": "DIFERENCIA",
      "fG": "=+F211-G211"
    }
  ],
});
