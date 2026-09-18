"""Recorre por HTTP los casos de prueba del flujo trx contra el agente local.

Respeta el contrato de turnos largos: POST /chat puede devolver el aviso de
"estoy revisando", y entonces hay que sondear POST /polling hasta el 303 y leer
el mensaje final en GET /polling/{id}. Mandar el siguiente mensaje antes de eso
deja la conversacion en un estado incoherente.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request

BASE = "http://localhost:8000"
ESPERA = "estoy revisando tu informacion"


def _norm(t: str) -> str:
    t = re.sub(r"\s+", " ", (t or "")).strip().lower()
    for a, b in zip("áéíóúü", "aeiouu"):
        t = t.replace(a, b)
    return t


def _peticion(path: str, payload: dict | None, metodo: str) -> tuple[int, dict | None]:
    datos = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}", data=datos,
        headers={"Content-Type": "application/json"}, method=metodo,
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            cuerpo = json.loads(raw) if raw.strip() else None
        except Exception:  # noqa: BLE001
            cuerpo = {"raw": raw[:200]}
        return e.code, cuerpo


def _post(path, payload):
    return _peticion(path, payload, "POST")


def _get(path):
    return _peticion(path, None, "GET")


def _leer(body: dict | None) -> tuple[str, list[tuple[str, str]]]:
    """Devuelve (texto, [(key, label)]) del sobre del agente."""
    if not body:
        return "", []
    contenido = (body.get("message") or {}).get("content") or {}
    if isinstance(contenido, str):
        return contenido, []
    opciones = [
        (str(o.get("key", "")), str(o.get("label", "")))
        for o in (contenido.get("options") or []) if isinstance(o, dict)
    ]
    return contenido.get("label") or "", opciones


class Conversacion:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.cid = ""
        self.turnos: list[tuple[str, str, list[str]]] = []
        self.opciones: list[tuple[str, str]] = []
        self.error = ""

    def abrir(self) -> bool:
        # Una conversacion por cliente y dia. Se cierra antes por si quedo viva;
        # el id lo estampa el servidor en UTC (que puede ir un dia por delante
        # de la hora local), asi que se cierran ayer, hoy y manana dinamicos.
        from datetime import datetime, timedelta, timezone

        hoy = datetime.now(timezone.utc)
        for delta in (-1, 0, 1):
            dia = (hoy + timedelta(days=delta)).strftime("%Y%m%d")
            _post("/end", {"conversation_id": f"{self.user_id}_{dia}"})
        code, body = _post("/start", {"user_id": self.user_id})
        if code not in (200, 201):
            self.error = f"/start devolvio {code}: {body}"
            return False
        self.cid = (body or {}).get("conversation_id", "")
        texto, self.opciones = _leer(body)
        self.turnos.append(("(inicio)", texto, [l for _k, l in self.opciones]))
        return True

    def decir(self, entrada: str) -> tuple[str, list[str]]:
        """Envia `entrada`; si coincide con una etiqueta ofrecida, manda su key."""
        contenido = entrada
        for key, label in self.opciones:
            if _norm(label) == _norm(entrada) and key:
                contenido = key
                break
        code, body = _post("/chat", {"conversation_id": self.cid, "content": contenido})
        if code == 204 or body is None:
            body = self._sondear()
        elif code not in (200, 201):
            self.error = f"/chat devolvio {code}: {body}"
            return "", []
        texto, opciones = _leer(body)
        if _norm(texto).startswith(ESPERA) or (body or {}).get("status") == "Running":
            body = self._sondear()
            texto, opciones = _leer(body)
        self.opciones = opciones
        etiquetas = [l for _k, l in opciones]
        self.turnos.append((entrada, texto, etiquetas))
        return texto, etiquetas

    def _sondear(self) -> dict | None:
        for _ in range(60):
            code, _b = _post("/polling", {"conversation_id": self.cid})
            if code == 303:
                _c, body = _get(f"/polling/{self.cid}")
                return body
            time.sleep(1.0)
        self.error = "polling agotado (60 s)"
        return None


def transcribir(c: Conversacion) -> str:
    out = []
    for entrada, texto, opciones in c.turnos:
        if entrada != "(inicio)":
            out.append(f"    > {entrada}")
        out.append(f"    BOT: {' '.join((texto or '').split())[:400]}")
        if opciones:
            out.append(f"    OPC: {opciones}")
    if c.error:
        out.append(f"    ERROR: {c.error}")
    return "\n".join(out)


if __name__ == "__main__":
    c = Conversacion(sys.argv[1] if len(sys.argv) > 1 else "500000001")
    if c.abrir():
        for paso in sys.argv[2:]:
            c.decir(paso)
            if c.error:
                break
    print(transcribir(c))
