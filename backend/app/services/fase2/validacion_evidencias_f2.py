"""Validación conservadora de evidencias; nunca activa reglas."""
import json
from pathlib import Path

VALIDOS = {"CAET", "CANT"}

def validar_evidencias(ruta):
    datos = json.loads(Path(ruta).read_text(encoding="utf-8-sig"))
    if datos.get("fase") != 2 or datos.get("tipo") != "MATRIZ_EVIDENCIAS_NO_OPERATIVA":
        raise ValueError("Matriz de evidencia inválida")
    reglas = datos.get("reglas")
    if not isinstance(reglas, list) or len(reglas) != 7:
        raise ValueError("Se esperan siete propuestas")
    ids = set()
    for r in reglas:
        rid = r.get("id_regla")
        if not isinstance(rid, str) or rid in ids:
            raise ValueError("ID ausente o duplicado")
        ids.add(rid)
        if r.get("tipo_insumo") not in VALIDOS or not r.get("cuenta_franquicia"):
            raise ValueError("Identidad de propuesta inválida")
        if r.get("habilitada") is not False or r.get("estado_regla") != "PENDIENTE_VALIDACION":
            raise ValueError("No se permite activar propuestas")
        if any(r.get(c) is not None for c in ("centro_host", "campo_host", "campo_franquicia", "factor_signo", "tolerancia")):
            raise ValueError("Se han definido campos contables sin aprobación")
        if r.get("cuenta_host_candidata") and not r.get("evidencias"):
            raise ValueError("Candidato Host sin evidencia")
    return {"total":len(reglas), "candidatas_documentadas":sum(bool(r.get("cuenta_host_candidata")) for r in reglas), "aprobadas":0,"estado":"PENDIENTE_VALIDACION"}

if __name__ == "__main__":
    import sys
    print(json.dumps(validar_evidencias(sys.argv[1]),ensure_ascii=False,indent=2))
