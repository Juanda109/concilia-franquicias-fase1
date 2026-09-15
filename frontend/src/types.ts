export type TipoInsumo = 'PMPD1322'|'PMRD8000'|'HA22'|'HA26'|'HA32'|'CAET'|'CANT'|'DEPO'|'CARTA_COMPENSACION'|'PMD'|'MEP'|'VSS';
export interface ArchivoEstado {
  idArchivo?: number; fuente: 'HOST'|'CREDIBANCO'|'REDEBAN'|'VISA'; tipoInsumo: TipoInsumo;
  nombreArchivo?: string; totalRegistros?: number; estadoRecepcion: string; estadoValidacion: string;
  estadoProcesamiento: string; estadoCarga: string; estadoDisponibilidad: string; disponible: boolean;
}
