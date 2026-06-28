"""
Agente Músico
Entrada:  atmosfera + entorno de la Escena (Organizador) + id_escena
Salida:   SalidaMusico con URLs de preview MP3 de Freesound

Freesound API v2:
  GET https://freesound.org/apiv2/search/text/
  ?query=...&token=API_KEY&fields=id,name,username,duration,previews,avg_rating
  &filter=duration:[30 TO 300]&sort=rating_desc&page_size=5

Los previews son URLs MP3 públicas, reproducibles directamente en el browser
sin autenticación adicional.
"""

import re
import time
import logging
import requests
from typing import Optional

from config.settings import settings
from config.llm import get_llm
from schemas.audio import PistaAudio, SalidaMusico

logger = logging.getLogger(__name__)

FREESOUND_SEARCH = "https://freesound.org/apiv2/search/text/"

# Palabras vacías que no aportan nada a una búsqueda de soundscape
_STOPWORDS = {
    "a", "an", "the", "and", "or", "with", "of", "in", "on", "at", "for",
    "to", "from", "by", "as", "is", "are", "was", "be", "it", "its",
    "very", "some", "this", "that", "these", "those",
}

# Palabras sufijo de soundscape aceptadas por Freesound
_SOUNDSCAPE_SUFIJOS = {"loop", "ambience", "ambiance", "drone", "soundscape"}

# Heurísticas para elegir el sufijo más adecuado si la descripción no trae ninguno
_SUFIJO_POR_CONTEXTO = [
    ({"fire", "flame", "crackle", "crackling", "hearth", "fireplace"}, "loop"),
    ({"bird", "birds", "chirp", "morning", "forest", "wind", "outdoor", "nature"}, "ambience"),
    ({"cave", "stone", "castle", "dungeon", "hall", "chamber", "crypt", "drip"}, "drone"),
    ({"rain", "thunder", "storm", "ocean", "water", "river", "wave"}, "soundscape"),
    ({"night", "tavern", "market", "crowd", "street", "medieval", "town"}, "ambience"),
]


def _extraer_keywords(descripcion: str, max_palabras: int = 4) -> str:
    """
    Construye una query de Freesound orientada a soundscapes/paisajes sonoros
    a partir de la descripción del Director.

    Siempre termina con una de las palabras mágicas: loop | ambience | drone | soundscape.

    Ejemplo:
      "fire crackling fireplace loop"  →  "fire crackling fireplace loop"
      "birds morning forest"           →  "birds morning forest ambience"
      "cave dark tense"                →  "cave dark drone"
    """
    palabras = re.findall(r"[a-zA-Z]+", descripcion.lower())
    keywords = [p for p in palabras if p not in _STOPWORDS and len(p) > 2]

    # Si el Director ya incluyó un sufijo soundscape, respetar el orden original
    tiene_sufijo = any(k in _SOUNDSCAPE_SUFIJOS for k in keywords)

    # Separar sufijos de palabras de contenido
    contenido = [k for k in keywords if k not in _SOUNDSCAPE_SUFIJOS]
    sufijos_presentes = [k for k in keywords if k in _SOUNDSCAPE_SUFIJOS]

    # Elegir sufijo: primero los que trajo el Director, luego heurística, luego "ambience"
    if sufijos_presentes:
        sufijo = sufijos_presentes[0]
    else:
        sufijo = "ambience"
        for palabras_clave, suf in _SUFIJO_POR_CONTEXTO:
            if any(c in palabras_clave for c in contenido):
                sufijo = suf
                break

    resultado = contenido[:max_palabras] + [sufijo]
    return " ".join(resultado)


def _buscar_freesound(query: str, api_key: str, reintentos_5xx: int = 3) -> list[dict]:
    """
    Busca soundscapes en Freesound y devuelve hasta 8 resultados ordenados por rating.
    Filtra por duración entre 10 s y 20 min — los soundscapes y drones suelen ser largos.

    Freesound devuelve 5xx de forma intermitente cuando está sobrecargado. Como la query
    es válida, reintentamos la MISMA petición con backoff corto antes de rendirnos (evita
    que un 503 transitorio cascade hasta el fallback). No reintenta en 401 (auth) ni 4xx.
    """
    params = {
        "query":     query,
        "token":     api_key,
        "fields":    "id,name,username,duration,previews,avg_rating,num_downloads",
        "filter":    "duration:[20 TO 1200]",  # >=20s: evita micro-clips que loopean mal
        "sort":      "rating_desc",
        "page_size": 8,
    }
    for intento in range(reintentos_5xx):
        ultimo = intento == reintentos_5xx - 1
        try:
            resp = requests.get(FREESOUND_SEARCH, params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json().get("results", [])
            if resp.status_code == 401:
                logger.error("[Musico] Freesound API key inválida (401).")
                return []
            # 5xx (sobrecarga): reintentar con backoff si quedan intentos
            if 500 <= resp.status_code < 600 and not ultimo:
                espera = 1.0 * (intento + 1)
                logger.warning(
                    f"[Musico] Freesound {resp.status_code} (sobrecarga), "
                    f"reintento {intento + 1}/{reintentos_5xx - 1} en {espera:.0f}s..."
                )
                time.sleep(espera)
                continue
            logger.warning(f"[Musico] Freesound error {resp.status_code}: {resp.text[:200]}")
            return []
        except requests.RequestException as e:
            if not ultimo:
                espera = 1.0 * (intento + 1)
                logger.warning(f"[Musico] Error de red ({e}), reintento en {espera:.0f}s...")
                time.sleep(espera)
                continue
            logger.warning(f"[Musico] Error de red: {e}")
            return []
    return []


def _resultado_a_pista(r: dict, volumen: float = 0.6) -> Optional[PistaAudio]:
    """Convierte un resultado de Freesound en PistaAudio."""
    previews = r.get("previews", {})
    url = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3")
    if not url:
        return None
    return PistaAudio(
        url_preview=url,
        titulo=r.get("name", "Desconocido"),
        autor=r.get("username", "Desconocido"),
        duracion_segundos=round(r.get("duration", 0), 1),
        volumen=volumen,
    )


# Guía común de las queries: sonidos FÍSICOS reales del lugar (no música), con sufijo
# ambient para sesgar hacia field recordings y no hacia drones cinematográficos virales.
_GUIA_QUERY = (
    "Generate a 3-5 word Freesound query for the soundscape of this scene.\n\n"
    "STEP 1 — Does the place have a CHARACTERISTIC REAL-WORLD SOUND? (nature, water, "
    "weather, fire, animals, a crowd, machinery, an engine, a rocket, traffic, a market...)\n\n"
    "· IF YES → query the SINGLE MOST DEFINING / dominant sound you would actually hear "
    "there — not a secondary detail (a rocket launch → its engine ROAR, not the metal or "
    "the crowd). A real physical sound, NOT a song. End the query with: loop, ambience or "
    "soundscape.\n"
    "  Examples: 'rocket launch roar loop', 'farm rooster birds ambience', "
    "'ocean waves beach ambience', 'fireplace crackling cabin loop', 'busy market crowd ambience'.\n\n"
    "· IF NO — the place has no characteristic real sound (deep space, the silent surface of "
    "the Moon, a void, an abstract or purely emotional moment, a quiet room) → do NOT force a "
    "literal sound. Query a SOFT ATMOSPHERIC ambient pad/drone that matches the MOOD; here a "
    "gentle musical drone IS appropriate. End the query with: ambient, drone or pad.\n"
    "  Examples: 'cosmic space ambient drone', 'tense suspense ambient drone', "
    "'ethereal weightless ambient pad', 'warm hopeful ambient drone', 'quiet room tone ambience'.\n\n"
    "Reply with ONLY the query, nothing else."
)


def _generar_query_inicial(atmosfera: str, entorno: str, provider: str) -> str:
    """
    Genera la query inicial de Freesound a partir de la atmósfera y entorno de la escena.
    Busca sonidos físicos reales del lugar (no música). Si el LLM falla, cae a la heurística.
    """
    prompt = (
        f"You are searching for an ambient soundscape on Freesound for a scene.\n"
        f"Scene location: \"{entorno}\"\n"
        f"Scene mood/atmosphere: \"{atmosfera}\"\n"
        f"{_GUIA_QUERY}"
    )
    try:
        llm = get_llm(provider)
        q = llm.invoke(prompt).content.strip().strip('"').strip("'").lower()
        logger.info(f"[Musico/LLM] Query inicial: '{q}'")
        return q
    except Exception as e:
        logger.warning(f"[Musico/LLM] Error generando query inicial ({e}). Usando heurística.")
        return _extraer_keywords(atmosfera)


def _refinar_query_musica(descripcion: str, queries_anteriores: list[str], provider: str) -> str:
    """Query alternativa cuando las anteriores no dieron resultados."""
    historial = ", ".join(f'"{q}"' for q in queries_anteriores)
    prompt = (
        f"You are searching for an ambient soundscape on Freesound for a scene.\n"
        f"Scene description: \"{descripcion}\"\n"
        f"Already tried (no audio found): {historial}\n"
        f"Suggest a DIFFERENT query.\n"
        f"{_GUIA_QUERY}"
    )
    try:
        llm = get_llm(provider)
        q = llm.invoke(prompt).content.strip().strip('"').strip("'").lower()
        logger.info(f"[Musico/LLM] Query refinada: '{q}'")
        return q
    except Exception as e:
        logger.warning(f"[Musico/LLM] Error refinando query: {e}")
        return "nature outdoor ambience"


def _elegir_mejor_pista(descripcion: str, query: str, resultados: list[dict], provider: str) -> int:
    """
    Freesound ordena por rating, pero el #1 puede ser topicalmente absurdo para la escena
    (una "Crashing Starship" muy votada para una charca). Este filtro le pasa al LLM los
    títulos candidatos y le pide el índice del que MEJOR encaja con el sonido real del lugar,
    descartando los que no pegan. Devuelve 0 (comportamiento anterior) si falla o no decide.
    """
    if len(resultados) <= 1:
        return 0
    listado = "\n".join(f"{i}: {r.get('name', '')}" for i, r in enumerate(resultados))
    prompt = (
        f"A scene needs an ambient soundscape (a real-world sound, not a song).\n"
        f"Scene: \"{descripcion}\"\n"
        f"Search query: \"{query}\"\n\n"
        f"Freesound returned these tracks (index: title), already sorted by rating:\n{listado}\n\n"
        f"Pick the index of the track whose TITLE best matches the scene's real sound. "
        f"REJECT titles that are topically WRONG for the scene (e.g. a spaceship, an "
        f"explosion or a song for a quiet pond). Among titles that fit, prefer the lowest "
        f"index (it is higher rated).\n"
        f"Reply with ONLY the number."
    )
    try:
        raw = get_llm(provider).invoke(prompt).content.strip()
        m = re.search(r"\d+", raw)
        if m:
            idx = int(m.group())
            if 0 <= idx < len(resultados):
                return idx
    except Exception as e:
        logger.warning(f"[Musico/LLM] Error eligiendo pista ({e}). Uso el top por rating.")
    return 0


# ─── Fallback local por tipo de ambiente ─────────────────────────────────────
# 6 paisajes sonoros CC0 empaquetados en assets/music/fallback/<bucket>.mp3.
# Se usan cuando la búsqueda en vivo no encuentra nada (o Freesound está caído).
# Descargar/refrescar con: python scripts/descargar_musica_fallback.py

from runtime_paths import recurso

_FALLBACK_DIR = recurso("assets", "music", "fallback")
_FALLBACK_URL_BASE = "/assets/music/fallback"  # ruta servida por FastAPI al browser

# tipo_ambiente (19 valores del catálogo) → uno de los 6 buckets de paisaje sonoro
_BUCKET_POR_AMBIENTE = {
    # naturaleza
    "naturaleza": "naturaleza", "bosque": "naturaleza", "selva": "naturaleza",
    "pradera": "naturaleza", "campo": "naturaleza",
    # agua
    "playa": "agua", "bajo_el_agua": "agua", "sobre_agua": "agua", "barco": "agua",
    # árido / viento abierto
    "desierto": "arido", "sabana": "arido", "montaña": "arido",
    # urbano / habitado
    "ciudad": "urbano", "pueblo": "urbano", "ruinas": "urbano",
    # cósmico
    "espacio": "cosmico", "superficie_planeta": "cosmico",
    # interior / cerrado
    "habitacion": "interior", "interior": "interior", "interior_grande": "interior", "cueva": "interior",
    "otro": "interior",
}
_BUCKET_DEFECTO = "naturaleza"


def _pista_mock(id_escena: str) -> PistaAudio:
    """Pista silenciosa para modo mock / sin API key."""
    return PistaAudio(
        url_preview="",
        titulo="[mock] Sin audio",
        autor="mock",
        duracion_segundos=0,
        volumen=0.0,
    )


def _pista_defecto(tipo_ambiente: Optional[str] = None) -> PistaAudio:
    """
    Pista de reserva local elegida por tipo_ambiente (determinista, sin LLM ni red).
    Si el MP3 del bucket no existe en disco, degrada a mock (silencio) en vez de
    apuntar a una URL que podría no cargar.
    """
    bucket = _BUCKET_POR_AMBIENTE.get(tipo_ambiente or "", _BUCKET_DEFECTO)
    archivo = _FALLBACK_DIR / f"{bucket}.mp3"
    if not archivo.exists():
        logger.warning(
            f"[Musico] Fallback local '{bucket}.mp3' no encontrado en {_FALLBACK_DIR}. "
            f"Reproduciendo en silencio. (Descarga con scripts/descargar_musica_fallback.py)"
        )
        return PistaAudio(url_preview="", titulo="[sin audio]", autor="-",
                          duracion_segundos=0, volumen=0.0)
    return PistaAudio(
        url_preview=f"{_FALLBACK_URL_BASE}/{bucket}.mp3",
        titulo=f"Ambiente: {bucket}",
        autor="freesound (CC0)",
        duracion_segundos=0,
        volumen=0.5,
    )


def ejecutar_musico(
    id_escena: str,
    atmosfera: str,
    entorno: str,
    modo: str = "auto",
    provider: str = "mercury",
    tipo_ambiente: Optional[str] = None,
) -> SalidaMusico:
    """
    Busca música ambiente en Freesound a partir de la atmósfera y entorno de la escena.
    Genera la query inicial con LLM y, si no hay resultados, hace hasta 2 reintentos
    con queries refinadas. Si aun así no encuentra nada, cae a un paisaje sonoro local
    (CC0) elegido determinísticamente por `tipo_ambiente`.

    modo:
      "freesound" → usa Freesound siempre
      "mock"      → devuelve pista vacía sin llamadas a API
      "auto"      → freesound si FREESOUND_API_KEY presente, si no mock
    """
    api_key = settings.freesound_api_key

    if modo == "mock" or (modo == "auto" and not api_key):
        logger.info(f"[Musico] Modo mock para '{id_escena}'.")
        return SalidaMusico(
            id_escena=id_escena,
            query_usada="mock",
            pista_principal=_pista_mock(id_escena),
            fuente="mock",
        )

    # Una query literal del entorno; si no devuelve nada, refinamos hasta 2 veces.
    # Tomamos el primer resultado (Freesound ya ordena por rating para ESA query, así que
    # es el más relevante para una búsqueda concreta — sin pooling cross-query que colaba
    # drones cinematográficos virales ajenos a la escena).
    descripcion = f"{entorno}. {atmosfera}"
    query = _generar_query_inicial(atmosfera, entorno, provider)
    queries_usadas = [query]
    resultados = []

    for intento in range(3):  # intento 0: inicial, 1-2: refinados si no hubo resultados
        if intento > 0:
            query = _refinar_query_musica(descripcion, queries_usadas, provider)
            queries_usadas.append(query)
        resultados = _buscar_freesound(query, api_key)
        if resultados:
            break

    # Solo resultados con preview usable (evita que un #1 sin audio caiga al fallback local
    # cuando había otros válidos). Sobre esos, el LLM elige el más coherente con la escena.
    usables = [r for r in resultados if _resultado_a_pista(r) is not None]
    idx = _elegir_mejor_pista(descripcion, query, usables, provider) if usables else 0
    pista_principal = _resultado_a_pista(usables[idx]) if usables else None

    if pista_principal is None:
        # Sin resultados usables: paisaje sonoro local por tipo_ambiente
        logger.warning(
            f"[Musico] Sin audio de Freesound para '{id_escena}' tras {len(queries_usadas)} "
            f"queries. Fallback local (ambiente: {tipo_ambiente})."
        )
        return SalidaMusico(
            id_escena=id_escena,
            query_usada="; ".join(queries_usadas),
            pista_principal=_pista_defecto(tipo_ambiente),
            fuente="fallback",
        )

    # Fallback: primer usable distinto del elegido.
    fb_idx = next((j for j in range(len(usables)) if j != idx), None)
    pista_fallback = _resultado_a_pista(usables[fb_idx]) if fb_idx is not None else None

    logger.info(
        f"[Musico] ✓ '{id_escena}': '{pista_principal.titulo}' por {pista_principal.autor} "
        f"({pista_principal.duracion_segundos}s)"
        + (f" [query {len(queries_usadas)}]" if len(queries_usadas) > 1 else "")
    )

    return SalidaMusico(
        id_escena=id_escena,
        query_usada=query,
        pista_principal=pista_principal,
        pista_fallback=pista_fallback,
        fuente="freesound",
    )
