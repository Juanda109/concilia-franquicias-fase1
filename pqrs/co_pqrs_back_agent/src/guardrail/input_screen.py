"""Guardrail : filtro deterministico de entrada (sin LLM, 0 tokens).

Detecta entradas inseguras o invalidas por patrones (no entiende semantica):
longitud e inyeccion de prompt / jailbreak. 
Devuelve un mensaje fijo de bloqueo, o None si la entrada pasa.
"""

from __future__ import annotations

import re
import unicodedata

from guardrail.judge import random_out_of_scope_message

MAX_INPUT_LENGTH = 2000

# Mensajes fijos para entradas invalidas. NO se usa el mensaje de "fuera de
# alcance" porque un mensaje vacio o muy largo no es un tema ajeno al banco:
# decirle "enfoquemonos en temas bancarios" a quien escribio una queja larga y
# legitima es desconcertante.
EMPTY_INPUT_MESSAGE = (
    "No recibí tu mensaje. Por favor escríbeme qué necesitas y te ayudo."
)
TOO_LONG_INPUT_MESSAGE = (
    "Tu mensaje es más largo de lo que puedo procesar. ¿Me lo resumes en pocas "
    "líneas, con el producto y lo que necesitas resolver?"
)

# --- Inyeccion de prompt / jailbreak -----------------------------------------
#
# PRECISION CRITICA. Estos patrones se aplican ANTES de cualquier ruteo y su
# falso positivo expulsa a un cliente real con el mensaje de fuera de alcance.
#
# Caso real (2026-08-20, conversacion 98909004_20260820): el patron `\bDAN\b`,
# compilado con IGNORECASE para atrapar el jailbreak "DAN", coincidia con el
# verbo espanol "dan". El mensaje "en el banco no me DAN razon y por la linea
# tampoco" -- una queja legitima por un CDT de 50 millones -- fue bloqueado como
# inyeccion. Medido sobre un corpus de quejas reales: 8 de 12 frases legitimas
# quedaban bloqueadas ("no me dan solucion", "me dan largas", "no dan
# respuesta", "olvida lo anterior, mejor quiero...", "el banco actua como
# intermediario").
#
# Reglas de diseno para no repetirlo:
#  1. Nada de siglas sueltas que coincidan con palabras comunes: exigir CONTEXTO
#     de jailbreak ("modo DAN", "eres DAN", "actua como DAN").
#  2. "ignora/olvida" solo cuenta cuando el objeto es una instruccion/regla/
#     prompt/sistema. "olvida lo anterior" es una correccion conversacional
#     normal de un cliente, no un ataque.
#  3. "actua/comportate como" exige un objeto de persona o sistema; "el banco
#     actua como intermediario" no es un ataque.
_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        # Anular instrucciones: el objeto debe ser la instruccion/regla/prompt.
        r"ignora\w*\s+(?:\w+\s+){0,3}(instruccion|instruccione|regla|prompt|sistema)",
        r"olvida\w*\s+(?:\w+\s+){0,3}(instruccion|instruccione|regla|prompt|sistema)",
        r"no\s+sigas\s+(?:\w+\s+){0,2}(instruccion|instruccione|regla)",
        # Suplantacion de rol: exige objeto de persona/sistema (incluye DAN).
        r"(?:act[uú]a|comp[oó]rtate|hazte\s+pasar|haz\s+de\s+cuenta)\s+"
        r"(?:como|por|que\s+eres)\s+(?:un[ao]?\s+|el\s+|la\s+)?"
        r"(dan\b|asistente|ia\b|inteligencia\s+artificial|modelo|bot\b|chatgpt|"
        r"gpt|hacker|administrador|admin\b|desarrollador|programador|sistema)",
        # Jailbreak "DAN": SIEMPRE con contexto, nunca la palabra suelta.
        r"\bmodo\s+dan\b",
        r"\bdan\s+mode\b",
        r"\beres\s+dan\b",
        r"\bmodo\s+desarrollador\b",
        # Revelar o reemplazar el system prompt.
        r"system\s+prompt",
        r"prompt\s+del\s+sistema",
        r"eres\s+ahora\s+(?:un|una|el|la)\b",
        r"a\s+partir\s+de\s+ahora\s+eres",
        r"jailbreak",
    )
)


# --- Solicitud de datos de TERCEROS (habeas data / reserva bancaria) ----------
# Rechazo controlado y ACOTADO: solo patrones CLAROS de "obtener datos/cedula/
# cuenta de otra persona o de un familiar/conocido". Ante cualquier duda NO
# dispara (None) y se deja la decision al LLM-judge de alcance. Nunca se rutea ni
# se consulta la cedula del tercero: el mensaje se responde y se bloquea. El bot
# ademas ingresa desde la cuenta personal (identidad ya validada en ese paso).
THIRD_PARTY_DATA_MESSAGE = (
    "Por protección de datos personales, no puedo consultar ni gestionar "
    "información de otras personas. Cada cliente debe realizar sus solicitudes "
    "directamente y con su propia identidad. Con gusto te ayudo con tus "
    "productos o solicitudes. ¿En qué puedo apoyarte?"
)

# Objeto de la consulta (dato personal / producto).
_THIRD_PARTY_OBJECT = (
    r"(?:datos|informacion|info|cedula|cedulas|documento|documentos|"
    r"cuenta|cuentas|saldo|saldos|movimientos|productos)"
)
# Relacion de tercero (familiar/conocido) o mencion explicita de un tercero.
# Texto ya normalizado sin acentos ni enes (companer, mama, cunad, ...).
_THIRD_PARTY_RELATION = (
    r"(?:otra\s+persona|otras\s+personas|un\s+tercero|una\s+tercera|terceros?|"
    r"alguien\s+mas|amig[oa]s?|companer[oa]s?|vecin[oa]s?|herman[oa]s?|"
    r"espos[oa]s?|mama|papa|madre|padre|hij[oa]s?|ti[oa]s?|prim[oa]s?|"
    r"jef[ae]|soci[oa]s?|novi[oa]s?|suegr[oa]s?|cunad[oa]s?|conocid[oa]s?|"
    r"familiar(?:es)?)"
)
# OBJETO + (hasta 2 palabras) + "de" + [determinante] + RELACION.
_THIRD_PARTY_PATTERN = re.compile(
    rf"{_THIRD_PARTY_OBJECT}\s+(?:\w+\s+){{0,2}}de\s+"
    rf"(?:(?:mi|el|la|los|las|un|una|su)\s+)?{_THIRD_PARTY_RELATION}\b"
)


def _normalize_ascii(text: str) -> str:
    """Lowercase + strip accents/ñ for accent-insensitive matching."""

    decomposed = unicodedata.normalize("NFKD", (text or "").casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def looks_like_third_party_data_request(text: str) -> bool:
    """Whether the message clearly asks to obtain a THIRD PARTY's data.

    Deterministic and intentionally NARROW (see module note): matches only the
    clear "obtener datos/cedula/cuenta de otra persona o de un familiar"
    phrasings, so the LLM-judge keeps authority over the ambiguous rest.
    """

    return bool(_THIRD_PARTY_PATTERN.search(_normalize_ascii(text)))


def screen_user_input(text: str) -> str | None:
    """Return a fixed block message if the input is unsafe/invalid, else None."""

    stripped = (text or "").strip()
    if not stripped:
        return EMPTY_INPUT_MESSAGE
    if len(text or "") > MAX_INPUT_LENGTH:
        return TOO_LONG_INPUT_MESSAGE
    # La deteccion corre sobre el texto normalizado (sin acentos) para que
    # "ignora las instrucciónes" no evada el filtro.
    normalized = _normalize_ascii(stripped)
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(normalized):
            return random_out_of_scope_message()
    # Solicitud de datos de terceros -> rechazo especifico de proteccion de datos
    # (no se rutea ni se consulta la cedula del tercero).
    if looks_like_third_party_data_request(stripped):
        return THIRD_PARTY_DATA_MESSAGE
    return None
