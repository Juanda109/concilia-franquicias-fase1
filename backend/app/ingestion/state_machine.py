ALLOWED = {
 "recepcion":{"No recibido":{"Recibido"}},
 "procesamiento":{"Pendiente":{"Procesando"},"Procesando":{"Procesado","Error"},"Error":{"Procesando"}},
}
def ensure_transition(stage,current,target):
    if target not in ALLOWED.get(stage,{}).get(current,set()):
        raise ValueError(f"Transición inválida {stage}: {current} -> {target}")
