"""
Agente 3 — El Constructor

Responsabilidades:
  1. Posicionamiento espacial (determinístico): convierte el grid del Director
     a coordenadas 3D en el escenario cilíndrico.
  2. Búsqueda de modelos 3D (poly.pizza): para cada elemento usa la keyword_busqueda
     del Director para encontrar el glTF correspondiente.

Grid 7 filas × columnas variables (pirámide):
  - fila    0-6 → radio desde el centro (0=horizonte, 6=primer plano)
  - columna → ángulo dentro del arco de la fila; rango por fila:
      fila 0: 0-8 (9 cols)   fila 1: 0-6 (7 cols)   fila 2: 0-4 (5 cols)
      fila 3: 0-7 (8 cols)   fila 4: 0-6 (7 cols)   fila 5: 0-4 (5 cols)
      fila 6: 0-2 (3 cols)
  - Filas jugables (narrativos): 3-6
  - Filas de fondo (decorados):  0-2

Los tamaños (ancho, alto) los decide el Director.
Los modelos 3D son buscados en poly.pizza usando keyword_busqueda.
"""
import os
import math
import time
import zlib
import logging
import requests
from typing import Optional, Dict, Any

_POLY_SESSION = requests.Session()

from schemas.especificacion import SalidaDirector, ElementoEscena
from schemas.escenas import TipoCielo, TipoAmbiente
from schemas.scene_graph import SceneGraph, NodoEscena, Vector3, CieloConfig
from schemas.personaje import SkinPersonaje
from config.settings import settings
from config.llm import get_llm
from config.catalogo_personajes import (
    CATALOGO, PERSONAJES, SKIN_TONES, SKIN_TONE_HEX, HAIR_COLORS,
    TALLAS, TALLA_DEFECTO, TALLA_ALTURA,
)
from pipeline.errors import ServicioModelosCaido

logger = logging.getLogger(__name__)

# ── Resiliencia ante caídas de la API de búsqueda de poly.pizza ───────────────
# Timeout corto (fallar rápido) + diagnóstico activo: si se acumulan timeouts seguidos,
# se SONDEAN keywords garantizadas para distinguir "API caída" de "objeto raro". Si la
# sonda confirma la caída, se aborta la generación (ServicioModelosCaido); si responde,
# fue cosa de esos objetos concretos y se continúa (billboard).
_POLY_TIMEOUT = 8.0                      # segundos por petición (antes 20)
_POLY_TIMEOUTS_PARA_DIAGNOSTICO = 3      # timeouts seguidos que disparan el sondeo
_PALABRAS_DIAGNOSTICO = ["tree", "barrel"]  # existen siempre si la API está viva
_poly_estado = {"timeouts_seguidos": 0}


def _reset_estado_poly() -> None:
    """Reinicia el contador de timeouts (al inicio de cada escena/generación)."""
    _poly_estado["timeouts_seguidos"] = 0


def _diagnosticar_poly_caido(api_key: str) -> bool:
    """Sondea la API con keywords garantizadas. Devuelve True solo si NINGUNA responde
    (API caída); False si alguna responde (estaba viva → fueron objetos concretos)."""
    for kw in _PALABRAS_DIAGNOSTICO:
        try:
            resp = _POLY_SESSION.get(
                f"https://api.poly.pizza/v1.1/search/{kw}",
                headers={"x-auth-token": api_key}, params={"Limit": 1}, timeout=_POLY_TIMEOUT,
            )
            if resp.status_code == 200:
                return False   # responde → viva
        except requests.RequestException:
            continue           # esta sonda falló; probar la siguiente
    return True                # ninguna respondió → caída


def _registrar_timeout_poly(api_key: str) -> None:
    """Suma un timeout consecutivo; al alcanzar el umbral, diagnostica. Si la API está
    caída de verdad, lanza ServicioModelosCaido (aborta la generación)."""
    _poly_estado["timeouts_seguidos"] += 1
    if _poly_estado["timeouts_seguidos"] >= _POLY_TIMEOUTS_PARA_DIAGNOSTICO:
        logger.warning(
            f"[Constructor] {_poly_estado['timeouts_seguidos']} timeouts seguidos de "
            "poly.pizza — diagnosticando si la API está caída..."
        )
        if _diagnosticar_poly_caido(api_key):
            raise ServicioModelosCaido(
                "La API de búsqueda de modelos 3D (poly.pizza) no responde."
            )
        # La sonda respondió: la API está viva → fueron objetos concretos. Continuar.
        logger.info("[Constructor] Diagnóstico: poly.pizza responde — eran objetos concretos, sigo.")
        _poly_estado["timeouts_seguidos"] = 0


def _registrar_ok_poly() -> None:
    """Una respuesta (no timeout) reinicia la racha de timeouts."""
    _poly_estado["timeouts_seguidos"] = 0


# ---------------------------------------------------------------------------
# Parámetros del escenario cilíndrico
# ---------------------------------------------------------------------------
# Fuente única de verdad en config/geometria.py — compartida con el Director
# (reparación de separación física) y los validadores.

from config.geometria import (
    N_COLS_POR_FILA,
    RADIO_CILINDRO_BAJO_AGUA,
    RADIO_CUBIERTA_BARCO,
    params_escena,
)

# Capa de renderizado por fila
CAPA_POR_FILA = {0: 1, 1: 2, 2: 3, 3: 5, 4: 7, 5: 9, 6: 11}


# ---------------------------------------------------------------------------
# Posicionamiento cilíndrico (determinístico)
# ---------------------------------------------------------------------------

def _grid_a_posicion(
    columna: int,
    fila: int,
    alto: float,
    radio_por_fila: dict,
    arco_por_fila: dict,
) -> Vector3:
    """
    Convierte (columna, fila) del grid pirámide a coordenadas 3D.

    columna → ángulo dentro del arco frontal de la fila (rango variable por fila)
    fila    → radio desde el centro (0=horizonte, 6=primer plano)

    El ángulo 0° apunta hacia la cámara (eje -Z).
    x = radio * sin(ángulo)
    z = -radio * cos(ángulo)
    """
    radio  = radio_por_fila.get(fila, 3.0)
    arco   = arco_por_fila.get(fila, 80)
    n_cols = N_COLS_POR_FILA.get(fila, 5)
    centro = (n_cols - 1) / 2.0
    paso   = arco / max(n_cols - 1, 1)
    offset_ladrillo = 0.5 if (fila % 2 == 1) else 0.0
    angulo_deg = (columna - centro + offset_ladrillo) * paso

    angulo_rad = math.radians(angulo_deg)
    x = radio * math.sin(angulo_rad)
    z = -radio * math.cos(angulo_rad)
    y = alto / 2  # el elemento apoya en el suelo

    return Vector3(x=round(x, 2), y=round(y, 2), z=round(z, 2))


# Interiores construidos: rejilla RECTANGULAR del suelo (7×7) en vez de la pirámide
# radial. (columna, fila) se reinterpretan como celda (gx, gy) sobre el plano de la sala:
#   columna 0..6 → x de izquierda(-X) a derecha(+X)
#   fila    0..6 → z de la pared frontal(-Z, la que ve el jugador) al fondo(+Z)
# Borde (columna/fila ∈ {0,6}) = pegado a la pared; centro = suelo libre.
GRID_INT_N = 7


def _grid_rect_a_posicion(columna: int, fila: int, alto: float, radio: float) -> Vector3:
    """Mapea una celda (columna, fila) de la rejilla 7×7 de interior a (x, z).

    Las celdas del BORDE (columna o fila ∈ {0,6}) se PEGAN a la pared correspondiente
    (margen pequeño) y se reparten a lo largo del muro por el otro índice → el mobiliario
    de pared queda contra la pared, no flotando a media sala. Las celdas del CENTRO quedan
    en una zona central recogida por la que el jugador camina.
    """
    N      = GRID_INT_N                             # 7
    medio  = (N - 1) / 2.0                          # 3.0
    pared  = max(radio - 0.6, 0.8)                  # casi tocando la pared
    span   = max(radio - 1.0, 1.0)                  # reparto a lo largo del muro
    centro = max(radio - 2.2, 0.8)                  # zona central (más recogida)
    en_col  = columna in (0, N - 1)
    en_fila = fila in (0, N - 1)

    if en_col and not en_fila:                      # pared izquierda (-X) / derecha (+X)
        x = -pared if columna == 0 else pared
        z = ((fila - medio) / medio) * span
    elif en_fila and not en_col:                    # pared frontal (-Z) / fondo (+Z)
        z = -pared if fila == 0 else pared
        x = ((columna - medio) / medio) * span
    elif en_col and en_fila:                        # esquina
        x = -pared if columna == 0 else pared
        z = -pared if fila == 0 else pared
    else:                                           # centro de la sala
        x = ((columna - medio) / medio) * centro
        z = ((fila    - medio) / medio) * centro

    return Vector3(x=round(x, 2), y=round(alto / 2, 2), z=round(z, 2))


# ---------------------------------------------------------------------------
# Barco (tipo_ambiente='barco'): cubierta (rejilla rect) + agua (anillos)
# ---------------------------------------------------------------------------

# Palabras que delatan un elemento que vive en el AGUA, no en la cubierta. Sirve de
# fallback determinista si la clasificación LLM falla (y para sembrar al LLM).
_BARCO_KW_AGUA = (
    "submarino", "submarine", "barca", "bote", "boya", "buoy", "isla", "island",
    "pez", "fish", "ballena", "whale", "delfin", "delfín", "dolphin", "tiburon",
    "tiburón", "shark", "coral", "arrecife", "reef", "sirena", "mermaid", "alga",
    "medusa", "jellyfish", "tortuga", "turtle", "naufragio", "wreck", "ancla", "anchor",
)


def _elegir_variante_barco(id_escena: str) -> str:
    """Variante de barco determinista por id de escena. El viewer la lee de
    SceneGraph.variante_barco (misma tabla _VARIANTES_BARCO), así cubierta y casco
    coinciden con la rejilla que coloca el Constructor."""
    tipos = ["balsa", "barco", "galeon"]
    return tipos[zlib.crc32(id_escena.encode()) % 3]


def _heuristica_zona_barco(elem: ElementoEscena) -> str:
    """Fallback: 'agua' si el nombre es marino o el objeto es grande (≥3 m); si no,
    'cubierta'. Los personajes se quedan en cubierta salvo que el nombre sea marino."""
    nombre = (elem.nombre or "").lower()
    if any(k in nombre for k in _BARCO_KW_AGUA):
        return "agua"
    if elem.tipo != "personaje" and max(elem.ancho or 0.0, elem.alto or 0.0) >= 3.0:
        return "agua"
    return "cubierta"


def _clasificar_zona_barco(
    elementos: list, entorno: str, atmosfera: str, provider: str
) -> dict:
    """Una llamada LLM que decide, por cada elemento, si va en la CUBIERTA del barco
    o en el AGUA alrededor. Devuelve {id: 'cubierta'|'agua'}. Degrada a la heurística
    determinista ante cualquier fallo (patrón de _elegir_atmosfera_otro)."""
    items = [{"id": e.id, "nombre": e.nombre, "tipo": e.tipo} for e in elementos]
    prompt = (
        "Escena marina con un barco sobre el agua. Para cada elemento decide dónde está:\n"
        "- \"cubierta\": sobre la cubierta del barco (personas, objetos de a bordo, "
        "barriles, cofres, cuerdas, timón, mástil, cajas, herramientas...).\n"
        "- \"agua\": flotando en el agua alrededor del barco, NO a bordo (submarinos, "
        "boyas, peces, corales, islas, otras barcas, criaturas marinas, naufragios...).\n"
        "Si dudas, 'cubierta'. Responde SOLO con JSON {id: \"cubierta\"|\"agua\"}.\n\n"
        f"Entorno: \"{entorno}\"\nAtmósfera: \"{atmosfera}\"\n"
        f"Elementos: {items}"
    )
    zonas: dict = {}
    try:
        import json as _json
        import re as _re
        raw = get_llm(provider).invoke(prompt).content
        m = _re.search(r'\{.*\}', raw, _re.DOTALL)
        d = _json.loads(m.group()) if m else {}
        for e in elementos:
            v = str(d.get(e.id, "")).lower().strip()
            zonas[e.id] = v if v in ("cubierta", "agua") else _heuristica_zona_barco(e)
        logger.info(
            "[Constructor/LLM] Zona barco → "
            + ", ".join(f"{k}={v}" for k, v in zonas.items())
        )
    except Exception as e:
        logger.warning(f"[Constructor/LLM] Error clasificando zona barco (heurística): {e}")
        zonas = {el.id: _heuristica_zona_barco(el) for el in elementos}
    return zonas


def _planificar_barco(
    elementos: list, zonas: dict, radio_cubierta: float, player_limit: float,
) -> dict:
    """Asigna a cada elemento su posición en el barco:
      - cubierta → celda (columna, fila) de la rejilla 7×7 (personajes al centro,
        decorados hacia los bordes), repartidas de dentro hacia afuera.
      - agua → (x, z) en anillos alrededor del casco, repartidos por ángulo áureo.
        Los NARRATIVOS de agua (personaje/objeto) van en un anillo cercano dentro del
        alcance del jugador (al desembarcar con B se les llega); los decorados de agua
        pueden ir en anillos más lejanos (son fondo).
    Devuelve {id: ("deck", col, fila)} | {id: ("water", x, z)}."""
    N = GRID_INT_N
    medio = (N - 1) / 2.0
    # Celdas ordenadas de dentro hacia afuera (centro = personajes; borde = decorados)
    celdas = sorted(
        ((c, f) for c in range(N) for f in range(N)),
        key=lambda cf: (cf[0] - medio) ** 2 + (cf[1] - medio) ** 2,
    )
    prioridad = {"personaje": 0, "objeto": 1, "decorado": 2}
    cubierta = sorted(
        [e for e in elementos if zonas.get(e.id) != "agua"],
        key=lambda e: prioridad.get(e.tipo, 3),
    )
    agua = [e for e in elementos if zonas.get(e.id) == "agua"]
    # Desbordamiento de cubierta (más elementos que celdas) → al agua
    if len(cubierta) > len(celdas):
        agua += cubierta[len(celdas):]
        cubierta = cubierta[:len(celdas)]

    plan: dict = {}
    for e, (c, f) in zip(cubierta, celdas):
        plan[e.id] = ("deck", c, f)

    GA = math.pi * (3.0 - math.sqrt(5.0))  # ángulo áureo → reparto uniforme
    # Anillo cercano para narrativos: justo fuera del casco, pero SIEMPRE dentro del
    # límite de jugador (al desembarcar se puede llegar). El margen de 0.4 garantiza
    # que el jugador pueda plantarse junto al objeto, no solo a rango de interacción.
    r_narr = min(radio_cubierta + 2.5, player_limit - 0.4)
    agua_narr = [e for e in agua if e.tipo in ("personaje", "objeto")]
    agua_deco = [e for e in agua if e.tipo not in ("personaje", "objeto")]
    for k, e in enumerate(agua_narr):
        a = k * GA + 0.6  # desfase para no encarar exactamente a los decorados
        plan[e.id] = ("water", round(r_narr * math.sin(a), 2), round(-r_narr * math.cos(a), 2))
    for k, e in enumerate(agua_deco):
        r = radio_cubierta + 4.5 + (k // 8) * 3.0  # decorados de fondo: pueden ir lejos
        a = k * GA
        plan[e.id] = ("water", round(r * math.sin(a), 2), round(-r * math.cos(a), 2))
    return plan


def _aplicar_jitter(pos: Vector3, elem_id: str, fila: int, arco_por_fila: dict) -> Vector3:
    """
    Añade un desplazamiento angular pequeño y determinístico (seeded por elem_id)
    para romper la rigidez del grid y evitar alineaciones accidentales entre filas.
    Magnitud: ±15% del paso de columna de la fila, máx ±10°.
    """
    paso = arco_por_fila.get(fila, 80) / max(N_COLS_POR_FILA.get(fila, 5) - 1, 1)
    max_jitter_deg = min(paso * 0.15, 10.0)

    seed = sum(ord(c) * (i + 1) for i, c in enumerate(elem_id)) % 10000
    jitter_frac = (seed / 10000) * 2 - 1          # [-1, 1]
    jitter_rad  = math.radians(jitter_frac * max_jitter_deg)

    r = math.sqrt(pos.x ** 2 + pos.z ** 2)
    if r < 0.001:
        return pos
    angle     = math.atan2(pos.x, -pos.z)
    new_angle = angle + jitter_rad
    return Vector3(
        x=round(r * math.sin(new_angle), 2),
        y=pos.y,
        z=round(-r * math.cos(new_angle), 2),
    )


def _reparar_colisiones_3d(nodos: list) -> None:
    """
    Detecta y resuelve solapamientos en el plano X-Z usando los valores de ancho
    como radio aproximado de cada nodo. Opera sobre narrativos y decorados;
    ignora fondo, suelo y ambiente. Itera hasta convergencia o MAX_ITER.
    """
    candidatos = [n for n in nodos if n.tipo in ("personaje", "objeto", "decorado")]
    if len(candidatos) < 2:
        return

    MAX_ITER = 6
    colisiones_resueltas = 0

    for _ in range(MAX_ITER):
        hay_colision = False
        for i, a in enumerate(candidatos):
            for b in candidatos[i + 1:]:
                dx   = b.posicion.x - a.posicion.x
                dz   = b.posicion.z - a.posicion.z
                dist = math.sqrt(dx * dx + dz * dz)
                # Usar ancho como radio de cada nodo; factor 0.8 da algo de tolerancia
                min_dist = (a.ancho + b.ancho) / 2 * 0.8

                if dist < min_dist and dist > 0.001:
                    hay_colision = True
                    colisiones_resueltas += 1
                    empuje = (min_dist - dist) / 2
                    nx, nz = dx / dist, dz / dist
                    a.posicion = Vector3(
                        x=round(a.posicion.x - nx * empuje, 2),
                        y=a.posicion.y,
                        z=round(a.posicion.z - nz * empuje, 2),
                    )
                    b.posicion = Vector3(
                        x=round(b.posicion.x + nx * empuje, 2),
                        y=b.posicion.y,
                        z=round(b.posicion.z + nz * empuje, 2),
                    )
        if not hay_colision:
            break

    if colisiones_resueltas:
        logger.info(f"[Constructor] Colisiones 3D resueltas: {colisiones_resueltas}")


def _clamp_narrativos_alcance(nodos: list, player_limit: float) -> None:
    """Red de seguridad final (solo escenas exteriores/barco, clamp radial): ningún
    NARRATIVO (personaje/objeto del Organizador) puede quedar fuera del alcance del
    jugador. Si alguno cae más allá de `player_limit` (p. ej. un narrativo desbordado
    a fila 0-2 por el Director, o un fallo de la planificación de barco), se reintroduce
    al anillo del límite conservando su ángulo. Los decorados/ambiente pueden ir lejos.
    En interiores en caja el límite no es radial → no se aplica (otra ruta lo cubre)."""
    movidos = 0
    for n in nodos:
        if getattr(n, "origen", None) != "narrativo":
            continue
        r = math.hypot(n.posicion.x, n.posicion.z)
        if r > player_limit and r > 0.001:
            f = (player_limit - 0.3) / r
            n.posicion = Vector3(
                x=round(n.posicion.x * f, 2),
                y=n.posicion.y,
                z=round(n.posicion.z * f, 2),
            )
            movidos += 1
    if movidos:
        logger.warning(
            f"[Constructor] {movidos} narrativo(s) fuera de alcance reubicados "
            f"al límite del jugador ({player_limit})."
        )


# ---------------------------------------------------------------------------
# Búsqueda en poly.pizza
# ---------------------------------------------------------------------------

# Plurales que casi siempre son modelos de GRUPO (arboledas, montones de rocas...) y
# escalan mal: se vetan globalmente en toda búsqueda de poly.pizza, SALVO que el propio
# keyword los pida (p. ej. receta "Gold Rocks" o "Stalactites & gems").
_BAN_PLURALES = [
    "trees", "rocks", "stones", "boulders", "bushes", "shrubs", "plants",
    "flowers", "mushrooms", "crystals", "gems", "shells", "corals",
    "logs", "leaves", "branches", "ferns", "vines",
]


def _buscar_polypizza(keyword: str, api_key: str, ban: list[str] | None = None) -> Optional[str]:
    """
    Busca un modelo 3D en poly.pizza por keyword.
    Devuelve la URL del glTF (.glb) del primer resultado, o None si no se encuentra.

    API v1.1:
      GET https://api.poly.pizza/search/{keyword}?Limit=5
      Header: x-auth-token: API_KEY
      Response: {"total": N, "results": [{"ID": "...", "Title": "...", "Download": "URL.glb", ...}]}

    ban: lista de subcadenas (case-insensitive) para excluir resultados por título.
    """
    if not api_key:
        logger.warning(f"[Constructor] polypizza_api_key no configurada. Saltando búsqueda para '{keyword}'")
        return None

    url     = f"https://api.poly.pizza/v1.1/search/{requests.utils.quote(keyword)}"
    headers = {"x-auth-token": api_key}
    params  = {"Limit": 5}
    # Veto por receta + veto global de plurales (omitiendo los que el keyword ya pide).
    _kw = keyword.lower()
    ban_lower = [b.lower() for b in (ban or [])] + [p for p in _BAN_PLURALES if p not in _kw]

    for intento in range(2):
        try:
            resp = _POLY_SESSION.get(url, headers=headers, params=params, timeout=_POLY_TIMEOUT)

            if resp.status_code == 401:
                logger.error("[Constructor] poly.pizza API key inválida (401). Comprueba POLYPIZZA_API_KEY en .env")
                return None
            if resp.status_code == 429:
                logger.warning("[Constructor] poly.pizza rate limit alcanzado. Esperando 3s...")
                time.sleep(3)
                continue
            if resp.status_code != 200:
                logger.warning(f"[Constructor] poly.pizza error {resp.status_code} para '{keyword}': {resp.text[:200]}")
                return None

            _registrar_ok_poly()   # la API respondió → reinicia la racha de timeouts
            data    = resp.json()
            results = data.get("results", [])

            if not results:
                logger.warning(f"[Constructor] poly.pizza: sin resultados para '{keyword}'")
                return None

            for model in results:
                download_url = model.get("Download")
                if not download_url:
                    continue
                title_lower = model.get("Title", "").lower()
                if ban_lower and any(b in title_lower for b in ban_lower):
                    logger.info(f"[Constructor] poly.pizza '{keyword}' → '{model.get('Title')}' descartado (ban)")
                    continue
                logger.info(
                    f"[Constructor] poly.pizza '{keyword}' → '{model.get('Title', '?')}' "
                    f"({model.get('Licence', '?')}) — {download_url}"
                )
                return download_url

            logger.warning(f"[Constructor] poly.pizza: resultados sin URL de descarga para '{keyword}'")
            return None

        except requests.exceptions.Timeout:
            if intento == 0:
                logger.warning(f"[Constructor] poly.pizza timeout para '{keyword}', reintentando...")
                time.sleep(1.5)
            else:
                logger.warning(f"[Constructor] poly.pizza error de red para '{keyword}': timeout tras reintento")
                _registrar_timeout_poly(api_key)   # puede lanzar ServicioModelosCaido si está caída
                return None
        except requests.RequestException as e:
            logger.warning(f"[Constructor] poly.pizza error de red para '{keyword}': {e}")
            return None
    return None


def _keyword_para_escena(entorno: str) -> str:
    """
    Extrae una keyword simple en inglés a partir de la descripción del entorno
    para buscar en poly.pizza Category=10 (Scenes & Levels).
    Mapeo basado en palabras clave comunes del entorno.
    """
    entorno_lower = entorno.lower()
    mapeo = [
        (["bosque", "forest", "árbol", "tree", "wood"],        "forest"),
        (["cocina", "kitchen"],                                 "kitchen"),
        (["cabaña", "cabin", "cottage"],                        "cottage"),
        (["castillo", "castle", "fortaleza"],                   "castle"),
        (["cueva", "cave", "caverna"],                          "cave"),
        (["playa", "beach", "mar", "ocean", "sea"],             "beach"),
        (["montaña", "mountain", "nieve", "snow"],              "mountain"),
        (["ciudad", "city", "calle", "street", "town"],         "city"),
        (["campo", "meadow", "prado", "granja", "farm"],        "meadow"),
        (["mazmorra", "dungeon", "subterráneo"],                 "dungeon"),
        (["mercado", "market", "pueblo", "village"],            "village"),
        (["habitación", "bedroom", "room", "interior"],         "room"),
        (["jardín", "garden", "parque", "park"],                "garden"),
        (["lago", "pond", "estanque", "river", "río"],          "pond"),
    ]
    for palabras, keyword in mapeo:
        if any(p in entorno_lower for p in palabras):
            return keyword
    return "landscape"  # fallback genérico


def _buscar_resultados_polypizza(keyword: str, api_key: str, limit: int = 5) -> list[dict]:
    """
    Igual que _buscar_polypizza pero devuelve la lista completa de resultados
    en lugar de solo la primera URL. Usada para selección inteligente por LLM.
    """
    if not api_key:
        return []

    url     = f"https://api.poly.pizza/v1.1/search/{requests.utils.quote(keyword)}"
    headers = {"x-auth-token": api_key}
    params  = {"Limit": limit}

    for intento in range(2):
        try:
            resp = _POLY_SESSION.get(url, headers=headers, params=params, timeout=_POLY_TIMEOUT)
            if resp.status_code == 429:
                time.sleep(3)
                continue
            if resp.status_code != 200:
                return []
            _registrar_ok_poly()   # la API respondió → reinicia la racha de timeouts
            return [m for m in resp.json().get("results", []) if m.get("Download")]
        except requests.exceptions.Timeout:
            if intento == 0:
                time.sleep(1.5)
            else:
                _registrar_timeout_poly(api_key)   # puede lanzar ServicioModelosCaido si está caída
                return []
        except requests.RequestException:
            return []
    return []


def _generar_keyword_inicial(
    nombre: str,
    descripcion: str,
    tipo: str,
    provider: str,
) -> str:
    """
    Genera la keyword inicial para buscar el modelo 3D en poly.pizza a partir de la
    DESCRIPCIÓN física (qué ES el elemento), ignorando el nombre propio: un perro
    llamado "Bip" debe buscar "dog", no "bip" (que devuelve cualquier cosa).
    """
    prompt = (
        f"Pick a 1-2 word ENGLISH noun to find a low-poly 3D model on poly.pizza.\n"
        f"What the element IS (physical description): \"{descripcion}\"\n"
        f"(its name in the story is \"{nombre}\", type: {tipo})\n"
        f"Give the GENERIC noun for WHAT IT IS, based on the DESCRIPTION — never its proper name.\n"
        f"E.g.: a dog named 'Bip' -> 'dog'; a man nicknamed 'Pitbull' -> 'man'; "
        f"a sword called 'Tizona' -> 'sword'.\n"
        f"Use a simple, concrete noun that exists as a low-poly 3D model.\n"
        f"Examples: 'girl', 'man', 'dog', 'wolf', 'basket', 'oak tree', 'rock', 'barrel', 'lantern'\n"
        f"Reply with ONLY the keyword, nothing else."
    )
    try:
        llm = get_llm(provider)
        kw = llm.invoke(prompt).content.strip().strip('"').strip("'").lower()
        logger.info(f"[Constructor/LLM] Keyword inicial para '{nombre}': '{kw}'")
        return kw
    except Exception as e:
        logger.warning(f"[Constructor/LLM] Error generando keyword para '{nombre}': {e}")
        return nombre.lower().split()[0]


def _refinar_keyword_modelo(
    nombre: str,
    tipo: str,
    keywords_anteriores: list[str],
    provider: str,
) -> str:
    """
    Pide al LLM una keyword alternativa para poly.pizza cuando las anteriores
    no devolvieron resultados. Sugiere sinónimos, categorías más amplias o
    aproximaciones visuales simples.
    """
    historial = ", ".join(f'"{k}"' for k in keywords_anteriores)
    prompt = (
        f"You are searching for a low-poly 3D model on poly.pizza for a scene element.\n"
        f"Element: \"{nombre}\" (type: {tipo})\n"
        f"Already tried keywords (no results found): {historial}\n"
        f"Suggest a different, simpler 1-2 word English noun to find a suitable model.\n"
        f"Think of synonyms, broader categories, or visual approximations.\n"
        f"Examples: if 'little girl' failed, try 'child'; if 'cauldron' failed, try 'pot'.\n"
        f"Reply with ONLY the keyword, nothing else."
    )
    try:
        llm = get_llm(provider)
        kw = llm.invoke(prompt).content.strip().strip('"').strip("'").lower()
        logger.info(f"[Constructor/LLM] Keyword refinada para '{nombre}': '{kw}'")
        return kw
    except Exception as e:
        logger.warning(f"[Constructor/LLM] Error refinando keyword para '{nombre}': {e}")
        return keywords_anteriores[-1]


def _elegir_mejor_modelo(
    nombre: str,
    tipo: str,
    resultados: list[dict],
    provider: str = "mercury",
) -> Optional[str]:
    """
    Usa el LLM para elegir el modelo más adecuado de la lista de resultados.
    Devuelve la URL Download del modelo elegido, o None si no hay resultados.

    Solo se llama para tipo == "personaje" o tipo == "objeto" (narrativo).
    Para decorado se usa directamente el primer resultado.
    """
    if not resultados:
        return None
    if len(resultados) == 1:
        return resultados[0].get("Download")

    # Construir lista numerada de títulos
    opciones = "\n".join(
        f"{i+1}. \"{m.get('Title', '?')}\"" for i, m in enumerate(resultados)
    )

    prompt = (
        f"You are selecting a 3D model from poly.pizza for a scene element.\n"
        f"Element: \"{nombre}\" (type: {tipo})\n\n"
        f"Available models:\n{opciones}\n\n"
        f"Which number best matches \"{nombre}\"? "
        f"Reply with ONLY the number, nothing else."
    )

    try:
        llm = get_llm(provider)
        respuesta = llm.invoke(prompt).content.strip()
        # Extraer el primer dígito de la respuesta
        import re
        match = re.search(r'\d+', respuesta)
        if match:
            idx = int(match.group()) - 1
            if 0 <= idx < len(resultados):
                elegido = resultados[idx]
                logger.info(
                    f"[Constructor/LLM] '{nombre}' → eligió [{idx+1}] '{elegido.get('Title', '?')}'"
                )
                return elegido.get("Download")
    except Exception as e:
        logger.warning(f"[Constructor/LLM] Error eligiendo modelo para '{nombre}': {e}")

    # Fallback: primer resultado
    return resultados[0].get("Download")


def _buscar_escena_base(entorno: str, api_key: str) -> tuple[Optional[str], Optional[str]]:
    """
    Busca un modelo 3D de escena completa en poly.pizza (Category=10 Scenes & Levels).
    Devuelve (gltf_url, keyword_usada) o (None, None) si no se encuentra.
    """
    keyword = _keyword_para_escena(entorno)
    url     = f"https://api.poly.pizza/v1.1/search/{requests.utils.quote(keyword)}"
    headers = {"x-auth-token": api_key}
    params  = {"Limit": 5, "Category": 10}

    try:
        resp = _POLY_SESSION.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"[Constructor] escena base: error {resp.status_code} para '{keyword}'")
            return None, None

        results = resp.json().get("results", [])
        if not results:
            logger.warning(f"[Constructor] escena base: sin resultados para '{keyword}' (Category=10)")
            return None, None

        for model in results:
            url_glb = model.get("Download")
            if url_glb:
                logger.info(
                    f"[Constructor] escena base '{keyword}' → '{model.get('Title', '?')}' "
                    f"({model.get('Licence', '?')}) — {url_glb}"
                )
                return url_glb, keyword

    except requests.RequestException as e:
        logger.warning(f"[Constructor] escena base: error de red — {e}")

    return None, None


# ---------------------------------------------------------------------------
# Generación de configuración de cielo (preset procedural con variación aleatoria)
# ---------------------------------------------------------------------------

import random as _random


def _rng(a: float, b: float) -> float:
    return a + _random.random() * (b - a)


def _rng_hex(c1: str, c2: str) -> str:
    t = _random.random()
    r = int(int(c1[1:3], 16) + (int(c2[1:3], 16) - int(c1[1:3], 16)) * t)
    g = int(int(c1[3:5], 16) + (int(c2[3:5], 16) - int(c1[3:5], 16)) * t)
    b = int(int(c1[5:7], 16) + (int(c2[5:7], 16) - int(c1[5:7], 16)) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


# Palabras que delatan el momento del día FUERA de un interior. Se escanean en la
# atmósfera + entorno (donde el Organizador anota "qué momento del día es") para que el
# haz de luz de las ventanas sea fiel a la historia: una escena nocturna entra luz de
# luna, una de tarde luz dorada. Si nada lo delata → genérico derivado del cielo.
_LUZ_NOCHE = (
    "noche", "nocturn", "anochec", "medianoche", "madrugada", "estrella", "luna",
    "lunar", "oscurid", "penumbra", "a oscuras", "night", "midnight", "moonlit",
    "moonlight", "starlit", "starry", "nightfall", "after dark",
)
_LUZ_TARDE = (
    "atardecer", "ocaso", "crepúscul", "crepuscul", "poniente", "la tarde",
    "caer la tarde", "hora dorada", "sunset", "dusk", "evening", "twilight",
    "golden hour", "afternoon",
)
_LUZ_DIA = (
    "mañana", "amanec", "mediodía", "mediodia", "pleno día", "pleno dia", "soleado",
    "luz del sol", "morning", "noon", "midday", "daylight", "sunrise", "broad daylight",
)


def _inferir_luz_exterior(atmosfera: str, entorno: str, cielo: str) -> str:
    """
    Deduce qué luz entra por las ventanas de un interior — 'dia' | 'tarde' | 'noche' —
    a partir del texto de la escena. Determinista, sin coste LLM. Si el texto no da
    pistas, cae a un genérico derivado del cielo interior (cálido → tarde, resto → día).
    """
    txt = f"{atmosfera} {entorno}".lower()
    if any(k in txt for k in _LUZ_NOCHE):
        return "noche"
    if any(k in txt for k in _LUZ_TARDE):
        return "tarde"
    if any(k in txt for k in _LUZ_DIA):
        return "dia"
    return "tarde" if cielo == "interior_calido" else "dia"


def _generar_cielo(tipo: str) -> CieloConfig:
    presets = {
        "amanecer": dict(
            color_fondo    = _rng_hex("#f07030", "#ffaa60"),
            color_ambiente = _rng_hex("#ff8850", "#ffaa70"),
            intensidad_ambiente = _rng(0.42, 0.55),
            color_sol      = _rng_hex("#ff8800", "#ffaa00"),
            intensidad_sol = _rng(0.9, 1.3),
            pos_sol        = {"x": _rng(-5.0, -3.0), "y": _rng(0.05, 0.25), "z": _rng(-2.0, -1.0)},
            niebla         = {"color": _rng_hex("#f07030", "#ffaa60"), "near": _rng(12, 18), "far": _rng(26, 36)},
        ),
        "manana_despejada": dict(
            color_fondo    = _rng_hex("#87ceeb", "#a8d8f5"),
            color_ambiente = "#ffffff",
            intensidad_ambiente = _rng(0.55, 0.65),
            color_sol      = _rng_hex("#ffcc00", "#ffe040"),
            intensidad_sol = _rng(1.0, 1.3),
            pos_sol        = {"x": _rng(-1.5, 1.5), "y": _rng(3.0, 5.0), "z": _rng(-2.0, -0.5)},
            niebla         = None,
        ),
        "manana_nublada": dict(
            color_fondo    = _rng_hex("#8898a8", "#a0b0c0"),
            color_ambiente = _rng_hex("#c8d4e0", "#d8e4f0"),
            intensidad_ambiente = _rng(0.70, 0.85),
            color_sol      = _rng_hex("#d0dce8", "#ddeaf5"),
            intensidad_sol = _rng(0.40, 0.60),
            pos_sol        = {"x": _rng(-1.0, 1.0), "y": _rng(3.0, 5.0), "z": _rng(-2.0, -0.5)},
            niebla         = {"color": _rng_hex("#8898a8", "#a0b0c0"), "near": _rng(10, 14), "far": _rng(20, 26)},
        ),
        "mediodia_soleado": dict(
            color_fondo    = _rng_hex("#4fa8dc", "#6ac0ee"),
            color_ambiente = "#ffffff",
            intensidad_ambiente = _rng(0.70, 0.80),
            color_sol      = _rng_hex("#ffd020", "#ffe840"),
            intensidad_sol = _rng(1.2, 1.5),
            pos_sol        = {"x": _rng(-0.5, 0.5), "y": _rng(5.0, 7.0), "z": _rng(-1.0, 0.0)},
            niebla         = None,
        ),
        "atardecer": dict(
            color_fondo    = _rng_hex("#c03010", "#e04020"),
            color_ambiente = _rng_hex("#c05030", "#e07040"),
            intensidad_ambiente = _rng(0.40, 0.50),
            color_sol      = _rng_hex("#ff5010", "#ff7020"),
            intensidad_sol = _rng(0.9, 1.2),
            pos_sol        = {"x": _rng(-5.0, -3.0), "y": _rng(0.05, 0.20), "z": _rng(-1.5, -0.5)},
            niebla         = {"color": _rng_hex("#c03010", "#d04018"), "near": _rng(10, 14), "far": _rng(22, 30)},
        ),
        "noche_estrellada": dict(
            color_fondo    = _rng_hex("#040410", "#080818"),
            color_ambiente = _rng_hex("#2c3858", "#3a4870"),
            intensidad_ambiente = _rng(0.40, 0.50),
            color_sol      = _rng_hex("#c8deff", "#d8e8ff"),
            intensidad_sol = _rng(0.25, 0.40),
            pos_sol        = {"x": _rng(-3.0, -1.0), "y": _rng(3.0, 5.0), "z": _rng(-4.0, -2.0)},
            niebla         = {"color": _rng_hex("#040410", "#080818"), "near": _rng(8, 12), "far": _rng(16, 22)},
        ),
        "noche_cerrada": dict(
            color_fondo    = _rng_hex("#020208", "#060614"),
            color_ambiente = _rng_hex("#242a3a", "#30384c"),
            intensidad_ambiente = _rng(0.46, 0.56),
            color_sol      = _rng_hex("#304050", "#405060"),
            intensidad_sol = _rng(0.40, 0.58),
            pos_sol        = {"x": _rng(-2.0, 2.0), "y": _rng(2.0, 4.0), "z": _rng(-2.0, 0.0)},
            niebla         = {"color": "#020208", "near": _rng(5, 8), "far": _rng(12, 18)},
        ),
        "tormenta": dict(
            color_fondo    = _rng_hex("#2a3040", "#3a4050"),
            color_ambiente = _rng_hex("#506080", "#607090"),
            intensidad_ambiente = _rng(0.35, 0.45),
            color_sol      = _rng_hex("#607090", "#708098"),
            intensidad_sol = _rng(0.15, 0.25),
            pos_sol        = {"x": 0.0, "y": _rng(2.0, 4.0), "z": _rng(-2.0, -1.0)},
            niebla         = {"color": _rng_hex("#2a3040", "#3a4050"), "near": _rng(4, 7), "far": _rng(12, 16)},
        ),
        "lluvia_suave": dict(
            color_fondo    = _rng_hex("#6878a0", "#7888b0"),
            color_ambiente = _rng_hex("#8898b8", "#9aa8c8"),
            intensidad_ambiente = _rng(0.50, 0.60),
            color_sol      = _rng_hex("#a0b0c8", "#b0c0d8"),
            intensidad_sol = _rng(0.25, 0.40),
            pos_sol        = {"x": _rng(-1.0, 1.0), "y": _rng(2.0, 4.0), "z": _rng(-2.0, -0.5)},
            niebla         = {"color": _rng_hex("#6878a0", "#7888b0"), "near": _rng(7, 10), "far": _rng(16, 20)},
        ),
        "niebla_densa": dict(
            color_fondo    = _rng_hex("#c8ccd0", "#d8dde0"),
            color_ambiente = _rng_hex("#d0d4d8", "#e0e4e8"),
            intensidad_ambiente = _rng(0.85, 1.0),
            color_sol      = _rng_hex("#c0c8d0", "#d0d8e0"),
            intensidad_sol = _rng(0.20, 0.35),
            pos_sol        = {"x": 0.0, "y": _rng(2.0, 4.0), "z": _rng(-2.0, -1.0)},
            niebla         = {"color": _rng_hex("#c8ccd0", "#d8dde0"), "near": _rng(1.5, 2.5), "far": _rng(5, 8)},
        ),
        "dia_nevado": dict(
            color_fondo    = _rng_hex("#ccd4dc", "#dde4ec"),
            color_ambiente = _rng_hex("#c0ccdc", "#d0dced"),
            intensidad_ambiente = _rng(0.75, 0.90),
            color_sol      = _rng_hex("#c8d8e8", "#d8e4f0"),
            intensidad_sol = _rng(0.35, 0.55),
            pos_sol        = {"x": _rng(-1.0, 1.0), "y": _rng(3.0, 5.0), "z": _rng(-2.0, -0.5)},
            niebla         = {"color": _rng_hex("#ccd4dc", "#dde4ec"), "near": _rng(8, 12), "far": _rng(18, 25)},
        ),
        "cielo_magico": dict(
            color_fondo    = _rng_hex("#0c0424", "#180838"),
            color_ambiente = _rng_hex("#6010a0", "#8020c0"),
            intensidad_ambiente = _rng(0.50, 0.65),
            color_sol      = _rng_hex("#40d0c0", "#60f0d0"),
            intensidad_sol = _rng(0.8, 1.2),
            pos_sol        = {"x": _rng(-2.0, 2.0), "y": _rng(3.0, 5.0), "z": _rng(-3.0, -1.0)},
            niebla         = {"color": _rng_hex("#0c0424", "#180838"), "near": _rng(8, 12), "far": _rng(18, 25)},
        ),
        "interior_calido": dict(
            color_fondo    = _rng_hex("#120804", "#1c0e06"),
            color_ambiente = _rng_hex("#ff7828", "#ff9040"),
            intensidad_ambiente = _rng(0.60, 0.75),
            color_sol      = _rng_hex("#ffa038", "#ffb858"),
            intensidad_sol = _rng(0.8, 1.1),
            pos_sol        = {"x": _rng(-1.0, 1.0), "y": _rng(3.0, 5.0), "z": _rng(-1.0, 1.0)},
            niebla         = None,
        ),
        "interior_luminoso": dict(
            color_fondo    = _rng_hex("#e8eef4", "#f0f4f8"),
            color_ambiente = _rng_hex("#f0f4ff", "#ffffff"),
            intensidad_ambiente = _rng(0.52, 0.62),
            color_sol      = _rng_hex("#f8f8ff", "#ffffff"),
            intensidad_sol = _rng(1.0, 1.2),
            pos_sol        = {"x": _rng(-2.0, 2.0), "y": _rng(4.0, 6.0), "z": _rng(-2.0, 0.0)},
            niebla         = None,
        ),
        "interior_frio": dict(
            color_fondo    = _rng_hex("#080810", "#0c0c1a"),
            color_ambiente = _rng_hex("#6a7a9a", "#7c8cac"),
            intensidad_ambiente = _rng(0.40, 0.50),
            color_sol      = _rng_hex("#90a8c8", "#a0b8d8"),
            intensidad_sol = _rng(0.4, 0.6),
            pos_sol        = {"x": _rng(-1.0, 1.0), "y": _rng(3.0, 5.0), "z": _rng(-1.0, 1.0)},
            niebla         = {"color": _rng_hex("#080810", "#0c0c1a"), "near": _rng(6, 9), "far": _rng(14, 20)},
        ),
    }

    params = presets.get(tipo) or presets["manana_despejada"]
    return CieloConfig(tipo=tipo, **params)


# ---------------------------------------------------------------------------
# Relleno ambiental procedural
# ---------------------------------------------------------------------------

# Recetas por tipo_ambiente: lista de elementos que pueblan el fondo.
# n_ext = instancias en anillo exterior (r≈80-95% del cilindro, muy al fondo)
# n_int = instancias en anillo interior (r≈48-65%, añade profundidad intermedia)
# Solo se hace UNA llamada a poly.pizza por keyword; el modelo se reutiliza N veces.
# Tipos de ambiente generados proceduralmente en JS (no usan poly.pizza)
_AMBIENTES_PROCEDURALES = {"espacio", "superficie_planeta", "bajo_el_agua", "sobre_agua", "barco", "interior"}

# Niebla de horizonte por tipo de ambiente: (near_pct, far_pct) del radio_cilindro.
# Solo se aplica cuando el preset de cielo no incluye ya niebla propia.
# far_pct debe ser < (1 - PLAYER_LIMIT_EXT/radio) para que el cilindro quede invisible
# desde el límite del jugador. El ejecutor aplica un clamp de seguridad adicional.
_NIEBLA_AMBIENTE: dict[str, tuple[float, float]] = {
    "bosque":     (0.30, 0.56),
    "selva":      (0.28, 0.54),
    "sabana":     (0.38, 0.60),
    "pradera":    (0.36, 0.58),
    "campo":      (0.38, 0.60),
    "naturaleza": (0.34, 0.58),
    "montaña":    (0.32, 0.58),
    "cueva":      (0.24, 0.55),
    "ruinas":     (0.34, 0.60),
    "ciudad":     (0.30, 0.62),
    "pueblo":     (0.28, 0.62),
    "desierto":   (0.32, 0.62),
    "playa":      (0.42, 0.62),
}


def _tono_bruma(hex_color: str) -> str:
    """Suaviza el color de la niebla auto-generada: lo desatura levemente hacia un
    gris neutro y baja un punto su luminosidad. Así los objetos lejanos leen como
    bruma con profundidad en vez de una capa de pintura plana (el síntoma de 'capa
    blanca' se dispara con cielos muy claros). El blend es sutil para no despegar
    la niebla del color del cielo (el horizonte debe seguir fundiéndose con él)."""
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
    except (ValueError, IndexError):
        return hex_color
    gris = (r + g + b) / 3.0
    mezcla = 0.18      # cuánto tira hacia el gris neutro (desaturación leve)
    oscurecer = 0.94   # baja un 6 % la luminosidad
    canal = lambda c: int(max(0, min(255, (c * (1 - mezcla) + gris * mezcla) * oscurecer)))
    return "#{:02x}{:02x}{:02x}".format(canal(r), canal(g), canal(b))


def _calcular_niebla(
    cielo_config: CieloConfig,
    tipo_ambiente: str,
    radio_cilindro: float,
    player_limit: float,
) -> Optional[Dict[str, Any]]:
    """Niebla de horizonte para escenas exteriores (near/far/color), o None si el
    preset no la define y no hay regla de ambiente. El `far` siempre se clampea a
    `far_max` para que el cilindro quede invisible desde el límite del jugador,
    independientemente de si la niebla viene del preset de cielo o de _NIEBLA_AMBIENTE.
    Se calcula ANTES de poblar el ambiente para que los anillos de relleno se
    coloquen coordinados con la rampa (ver `_poblar_ambiente`)."""
    far_max = round(radio_cilindro - player_limit - 2.5, 1)

    if cielo_config.niebla is None:
        # Sin niebla del preset: usar _NIEBLA_AMBIENTE si existe, si no mínimo garantizado
        if tipo_ambiente in _NIEBLA_AMBIENTE:
            near_pct, far_pct = _NIEBLA_AMBIENTE[tipo_ambiente]
            near = round(radio_cilindro * near_pct, 1)
            far  = min(round(radio_cilindro * far_pct, 1), far_max)
        else:
            far  = far_max
            near = round(far_max * 0.45, 1)
        if near >= far:
            near = round(far * 0.65, 1)
        color = _tono_bruma(cielo_config.color_fondo)
        logger.info(f"[Constructor] Niebla añadida (near={near}, far={far})")
        return {"color": color, "near": near, "far": far}

    # El preset ya trae niebla (color hecho a mano) — solo clampear far
    niebla = dict(cielo_config.niebla)
    if niebla["far"] > far_max:
        niebla["far"] = far_max
        if niebla["near"] >= far_max:
            niebla["near"] = round(far_max * 0.65, 1)
        logger.info(f"[Constructor] Niebla del preset clampeada a far={far_max}")
    return niebla

RECETAS_AMBIENTE: dict[str, list[dict]] = {
    # n_ext = anillo lejano   80-95% del radio (horizonte, pegado al cilindro)
    # n_int = anillo medio: 52-68% del radio (profundidad intermedia)
    "bosque": [
        {"keyword": "big tree",  "n_ext": 36, "n_int": 18, "ancho": 2.2, "alto": 4.5},
        {"keyword": "pine",      "n_ext": 28, "n_int": 12, "ancho": 1.8, "alto": 5.0, "ban": ["pine tree", "trees"]},
        {"keyword": "rock",      "n_ext": 10, "n_int":  8, "ancho": 1.2, "alto": 0.9},
        {"keyword": "mushroom",  "n_ext":  0, "n_int": 14, "ancho": 0.4, "alto": 0.5},
    ],
    "ciudad": [
        {"keyword": "building",    "n_ext": 20, "n_int": 0, "ancho": 2.5, "alto": 7.0},
        {"keyword": "car",         "n_ext":  0, "n_int": 2, "ancho": 1.6, "alto": 1.2},
        {"keyword": "street lamp", "n_ext":  8, "n_int": 6, "ancho": 0.3, "alto": 3.0},
    ],
    "pueblo": [
        {"keyword": "house",   "n_ext": 12, "n_int": 0, "ancho": 2.0, "alto": 3.5},
        {"keyword": "Cottage", "n_ext":  8, "n_int": 0, "ancho": 1.8, "alto": 3.0},
        {"keyword": "well",    "n_ext":  0, "n_int": 1, "ancho": 0.8, "alto": 1.0},
        {"keyword": "barrel",  "n_ext":  0, "n_int": 2, "ancho": 0.5, "alto": 0.7},
        {"keyword": "bench",   "n_ext":  0, "n_int": 2, "ancho": 1.0, "alto": 0.8},
    ],
    "campo": [
        {"keyword": "barn",     "n_ext": 10, "n_int":  0, "ancho": 4.0, "alto": 4.0},
        {"keyword": "fence",    "n_ext": 22, "n_int":  0, "ancho": 2.0, "alto": 1.2},
        {"keyword": "tree",     "n_ext": 24, "n_int":  5, "ancho": 2.2, "alto": 3.5},
        {"keyword": "hay bale", "n_ext":  8, "n_int":  6, "ancho": 1.2, "alto": 1.0},
        {"keyword": "flower",   "n_ext": 18, "n_int": 14, "ancho": 0.3, "alto": 0.4},
    ],
    "selva": [
        {"keyword": "palm tree",     "n_ext": 36, "n_int":  8, "ancho": 2.5, "alto": 7.0},
        {"keyword": "Balsa tree",    "n_ext": 26, "n_int":  5, "ancho": 2.5, "alto": 6.0},
        {"keyword": "Macassar tree", "n_ext": 20, "n_int":  4, "ancho": 2.0, "alto": 5.5},
        {"keyword": "fern",          "n_ext": 18, "n_int": 14, "ancho": 1.0, "alto": 0.8},
        {"keyword": "vine",          "n_ext": 22, "n_int":  0, "ancho": 0.5, "alto": 4.0},
    ],
    "sabana": [
        {"keyword": "acacia tree",         "n_ext": 32, "n_int":  8, "ancho": 4.0, "alto": 5.0},
        {"keyword": "boab",                "n_ext": 14, "n_int":  3, "ancho": 3.0, "alto": 4.0},
        {"keyword": "tree from the sabana", "n_ext": 14, "n_int":  3, "ancho": 3.5, "alto": 4.5},
        {"keyword": "grass",               "n_ext": 16, "n_int": 12, "ancho": 0.6, "alto": 0.5},
    ],
    "pradera": [
        {"keyword": "tree",   "n_ext": 34, "n_int":  6, "ancho": 2.0, "alto": 3.5},
        {"keyword": "flower", "n_ext": 22, "n_int": 24, "ancho": 0.3, "alto": 0.4},
        {"keyword": "rock",   "n_ext":  6, "n_int":  4, "ancho": 1.0, "alto": 0.7},
    ],
    "desierto": [
        {"keyword": "cactus",              "n_ext": 12, "n_int": 5, "ancho": 1.5, "alto": 3.0},
        {"keyword": "Prickly pear cactus", "n_ext":  8, "n_int": 4, "ancho": 1.2, "alto": 1.5},
        {"keyword": "barrel cactus",       "n_ext":  6, "n_int": 3, "ancho": 1.0, "alto": 1.2},
        {"keyword": "rock",                "n_ext":  6, "n_int": 2, "ancho": 1.5, "alto": 1.0},
    ],
    "playa": [
        {"keyword": "palm tree",       "n_ext": 28, "n_int": 18, "ancho": 1.8, "alto": 5.5, "ban": ["palm trees"]},
        {"keyword": "Queen Palm Tree", "n_ext": 20, "n_int": 12, "ancho": 2.0, "alto": 6.0, "ban": ["palm trees", "queen palm trees"]},
        {"keyword": "rock",            "n_ext": 16, "n_int": 10, "ancho": 1.5, "alto": 1.0},
        {"keyword": "seashell",        "n_ext":  0, "n_int": 22, "ancho": 0.3, "alto": 0.2},
        {"keyword": "grass",           "n_ext":  0, "n_int": 18, "ancho": 0.6, "alto": 0.5},
    ],
    "montaña": [
        {"keyword": "Rock",     "n_ext": 44, "n_int": 12, "ancho": 2.0, "alto": 1.8},
        {"keyword": "Pine",     "n_ext": 28, "n_int":  7, "ancho": 1.8, "alto": 4.5, "ban": ["pine tree", "trees"]},
        {"keyword": "Fir tree", "n_ext": 24, "n_int":  5, "ancho": 1.5, "alto": 4.0},
    ],
    "cueva": [
        {"keyword": "Stalactites & gems", "n_ext": 22, "n_int":  8, "ancho": 0.6, "alto": 2.5},
        {"keyword": "Gold Rocks",         "n_ext": 14, "n_int":  6, "ancho": 1.0, "alto": 1.0},
        {"keyword": "rock",               "n_ext": 28, "n_int": 10, "ancho": 1.5, "alto": 1.2},
    ],
    "ruinas": [
        {"keyword": "column",     "n_ext": 16, "n_int": 5, "ancho": 1.0, "alto": 4.0},
        {"keyword": "rock",       "n_ext": 20, "n_int": 6, "ancho": 1.5, "alto": 1.0},
        {"keyword": "stone wall", "n_ext": 12, "n_int": 3, "ancho": 2.5, "alto": 2.5},
    ],
    "bajo_el_agua": [
        {"keyword": "coral",        "n_ext": 26, "n_int": 10, "ancho": 1.0, "alto": 1.8},
        {"keyword": "orange coral", "n_ext": 20, "n_int":  8, "ancho": 1.0, "alto": 1.6},
        {"keyword": "kelp",         "n_ext": 26, "n_int": 10, "ancho": 0.5, "alto": 3.5},
        {"keyword": "seaweed",      "n_ext": 16, "n_int":  6, "ancho": 0.5, "alto": 2.5},
        {"keyword": "fish",         "n_ext":  8, "n_int":  8, "ancho": 0.4, "alto": 0.3},
    ],
}


def _keywords_naturaleza(entorno: str, provider: str) -> list[tuple[str, float, float]]:
    """
    Para tipo_ambiente='naturaleza': pregunta al LLM cuáles son los 3 elementos
    naturales más característicos del entorno (árbol concreto, elemento secundario,
    detalle de suelo) y devuelve lista de (keyword, ancho, alto).
    """
    prompt = (
        "You are selecting background 3D objects for a natural outdoor scene.\n"
        f"Scene: \"{entorno}\"\n\n"
        "List exactly 3 keywords for the most characteristic natural background elements, "
        "ordered from most to least prominent:\n"
        "  1. Dominant vegetation (specific tree or plant type visible in the scene)\n"
        "  2. Secondary element (rocks, smaller plants, logs...)\n"
        "  3. Ground detail (flowers, grass, pebbles, lily pads...)\n"
        "Rules: 1-2 word English nouns, suitable for low-poly 3D model search.\n"
        "Reply with ONLY a JSON array. Example: [\"willow tree\", \"rock\", \"flower\"]"
    )
    _FALLBACK = [("tree", 2.0, 3.5), ("rock", 1.2, 0.8), ("flower", 0.3, 0.4)]
    try:
        import json as _json, re as _re
        llm = get_llm(provider)
        resp = llm.invoke(prompt).content.strip()
        match = _re.search(r'\[[\s\S]*?\]', resp)
        if not match:
            return _FALLBACK
        keywords = _json.loads(match.group())
        if not isinstance(keywords, list) or len(keywords) < 2:
            return _FALLBACK

        _PALABRAS_ARBOL  = {"tree", "bush", "shrub", "cactus", "palm", "pine", "oak",
                            "willow", "bamboo", "birch", "maple", "fir", "cypress", "reed"}
        _PALABRAS_ROCA   = {"rock", "stone", "boulder", "log", "stump", "root"}

        result = []
        for kw in keywords[:3]:
            kw = str(kw).lower().strip()
            if any(w in kw for w in _PALABRAS_ARBOL):
                result.append((kw, 2.0, 4.0))
            elif any(w in kw for w in _PALABRAS_ROCA):
                result.append((kw, 1.5, 1.0))
            else:
                result.append((kw, 0.4, 0.5))

        logger.info(f"[Constructor/LLM] Keywords naturaleza extraídas: {[r[0] for r in result]}")
        return result
    except Exception as e:
        logger.warning(f"[Constructor/LLM] Error extrayendo keywords de naturaleza: {e}")
        return _FALLBACK


def _receta_naturaleza(entorno: str, provider: str) -> list[dict]:
    """
    Construye la receta de tipo_ambiente='naturaleza' extrayendo keywords del entorno.
    Estructura fija: vegetación dominante densa + elemento secundario + detalle de suelo.
    """
    keywords = _keywords_naturaleza(entorno, provider)
    # Conteos (ext, int) por posición: dominante → secundario → detalle de suelo
    conteos = [(40, 10), (14, 6), (20, 14)]
    return [
        {"keyword": kw, "n_ext": n_ext, "n_int": n_int, "ancho": ancho, "alto": alto}
        for (kw, ancho, alto), (n_ext, n_int) in zip(keywords, conteos)
    ]


def _color_superficie_planeta(entorno: str, provider: str) -> str:
    """Devuelve un hex color para el suelo de una superficie planetaria según el entorno."""
    prompt = (
        f"You are choosing the ground surface color of a planetary environment for a 3D scene.\n"
        f"Environment: \"{entorno}\"\n"
        f"Examples: moon → #9a9a8a (gray), Mars → #c1440e (rusty red), "
        f"icy moon → #c8dde8 (pale blue-white), volcanic planet → #2a1a0a (dark brown), "
        f"alien world → #4a7a4a (muted green).\n"
        f"Reply with ONLY a single hex color code like #c1440e, nothing else."
    )
    try:
        llm = get_llm(provider)
        raw = llm.invoke(prompt).content.strip()
        import re
        match = re.search(r'#[0-9a-fA-F]{6}', raw)
        if match:
            color = match.group()
            logger.info(f"[Constructor/LLM] Color superficie_planeta: {color}")
            return color
    except Exception as e:
        logger.warning(f"[Constructor/LLM] Error obteniendo color superficie_planeta: {e}")
    return "#9a9a8a"


def _elegir_atmosfera_otro(entorno: str, atmosfera: str, provider: str) -> tuple[Optional[str], Optional[str]]:
    """Solo para tipo_ambiente='otro': decide superficies procedurales especiales del
    SUELO y del TECHO. Devuelve (tipo_suelo, tipo_techo), cualquiera puede ser None:
      - tipo_suelo ∈ {'nubes','agua','lava','cristal'} (None = suelo sólido normal de color).
      - tipo_techo='nubes_bajas' → nubes bajas / niebla espesa ARRIBA que ocultan lo alto:
        algo sube o crece hacia el cielo y no se ve dónde acaba (p.ej. una habichuela
        gigante que se pierde entre las nubes). Son independientes."""
    prompt = (
        "Escena de fantasía. Decide el SUELO y si hay nubes bajas arriba. Responde SOLO con "
        "JSON, sin texto extra:\n"
        '{"suelo": "normal|nubes|agua|lava|cristal", "nubes_altas": true|false}\n\n'
        "SUELO — ¿sobre qué pisa el personaje?\n"
        "- nubes:   camina sobre un mar de nubes (reino del cielo).\n"
        "- agua:    sobre la superficie del agua / suelo inundado.\n"
        "- lava:    suelo volcánico incandescente.\n"
        "- cristal: suelo de cristal o hielo translúcido y brillante.\n"
        "- normal:  suelo sólido corriente (tierra, piedra, hierba, madera, arena...).\n"
        "NUBES_ALTAS — true si algo sube/crece hacia el cielo y NO se ve dónde termina "
        "(un tallo, árbol o torre gigante que se pierde entre nubes bajas o niebla espesa).\n\n"
        f"Entorno: \"{entorno}\"\nAtmósfera: \"{atmosfera}\"\n"
        "Si dudas, suelo='normal' y nubes_altas=false."
    )
    suelo = techo = None
    try:
        import json as _json, re as _re
        raw = get_llm(provider).invoke(prompt).content
        m = _re.search(r'\{.*\}', raw, _re.DOTALL)
        if m:
            d = _json.loads(m.group())
            s = str(d.get("suelo", "normal")).lower().strip()
            if s in ("nubes", "agua", "lava", "cristal"):
                suelo = s
            if d.get("nubes_altas"):
                techo = "nubes_bajas"
            logger.info(f"[Constructor/LLM] Atmósfera 'otro' → suelo={suelo}, techo={techo}")
    except Exception as e:
        logger.warning(f"[Constructor/LLM] Error eligiendo atmósfera 'otro': {e}")
    return suelo, techo


def _pedir_receta_llm(entorno: str, provider: str) -> list[dict]:
    """
    Para tipo_ambiente='otro': pide al LLM una receta de relleno ambiental
    basada en la descripción del entorno. Devuelve lista de dicts con las
    mismas claves que las recetas predefinidas.
    """
    prompt = (
        "You are populating the ambient background of a 3D low-poly scene.\n"
        f"Scene environment: \"{entorno}\"\n\n"
        "Suggest 3-4 types of background objects to fill the scene.\n"
        "For each, provide:\n"
        "  - keyword: 1-2 word English noun for poly.pizza 3D model search\n"
        "  - n_ext: count in outer ring / far background (0-15)\n"
        "  - n_int: count in inner ring / mid background (0-8)\n"
        "  - ancho: width in 3D units (0.3 to 5.0)\n"
        "  - alto: height in 3D units (0.3 to 8.0)\n\n"
        "Reply with ONLY a valid JSON array. Example:\n"
        '[{"keyword": "rock", "n_ext": 10, "n_int": 5, "ancho": 1.5, "alto": 1.0}]'
    )
    try:
        import json as _json
        import re as _re
        llm = get_llm(provider)
        resp = llm.invoke(prompt).content.strip()
        match = _re.search(r'\[[\s\S]*\]', resp)
        if match:
            receta = _json.loads(match.group())
            logger.info(f"[Constructor/LLM] Receta ambiente 'otro': {[r['keyword'] for r in receta]}")
            return receta
    except Exception as e:
        logger.warning(f"[Constructor/LLM] Error generando receta de ambiente: {e}")
    return []


def _receta_ciudad(entorno: str, provider: str) -> list[dict]:
    """
    Para tipo_ambiente='ciudad': pide al LLM los elementos de relleno propios de
    ESTA ciudad concreta, infiriendo su época y carácter del entorno. Prompt neutro
    — no se prohíbe ni se empuja ningún elemento; la ciudad decide qué le pertenece
    (una urbe moderna traerá coches, una del XVIII carruajes, etc.).
    Devuelve [] si falla → el llamador cae a la receta fija de 'ciudad'.
    """
    prompt = (
        "You are populating the ambient background of a 3D low-poly CITY scene.\n"
        f"Scene environment: \"{entorno}\"\n\n"
        "Read this specific city and infer its setting and historical period from the text.\n"
        "Choose 3-4 types of background props that genuinely belong in THIS particular city. "
        "Let the city itself decide what belongs there (its own era and character). Use a varied "
        "mix of types so the scene doesn't look like the same model copy-pasted everywhere.\n\n"
        "RULES:\n"
        "1. ARCHITECTURE first, and dominant: use 1-2 DIFFERENT WHOLE building types of the city's "
        "period (two distinct types make the skyline varied instead of identical clones). They must "
        "be COMPLETE structures — houses, buildings, towers, skyscrapers. NEVER walls, fences, "
        "gates, arches or partial structures: instanced alone they look like random fragments "
        "floating around.\n"
        "2. Buildings must be BIG (they sit far away and must read as a skyline): ancho 3-6, and "
        "alto 8-14 (lower for low houses ~8, tall for towers/skyscrapers up to 14). Make them few "
        "but large: 8-14 buildings TOTAL across the architecture types. Place them MOSTLY in the "
        "far ring (n_ext) PLUS a FEW in the mid ring (n_int 2-3) so some read as medium-close "
        "without ever blocking the player. Architecture is always the most numerous part.\n"
        "3. Then add 1-2 street-level prop types as ACCENTS only (lighting, transport, daily-life "
        "objects of the era). Keep their counts LOW: n_ext 4-8 OR n_int 2-5 each — details, not a "
        "crowd. Prefer simple, solid, recognizable props.\n"
        "4. Use SPECIFIC, unambiguous 2-word English keywords so the 3D model search returns the "
        "right object. A single generic word often returns a wrong/modern model — e.g. 'cart' "
        "returns a SHOPPING cart, 'building' returns a random one. Prefer precise terms that pin "
        "down the period AND the object (e.g. 'medieval house', 'stone tower', 'wooden handcart', "
        "'gas lamp', 'town house', 'office tower'...).\n\n"
        "For each entry provide:\n"
        "  - keyword: specific 2-word English noun for poly.pizza 3D model search\n"
        "  - n_ext: count in outer ring / far background (0-22)\n"
        "  - n_int: count in inner ring / mid background (0-8)\n"
        "  - ancho: width in 3D units (3-6 for buildings, smaller for props)\n"
        "  - alto: height in 3D units (8-14 for buildings, smaller for props)\n\n"
        "Reply with ONLY a valid JSON array. Example (modern city):\n"
        '[{"keyword": "office tower", "n_ext": 9, "n_int": 2, "ancho": 4.0, "alto": 12.0}, '
        '{"keyword": "glass skyscraper", "n_ext": 5, "n_int": 1, "ancho": 3.5, "alto": 14.0}, '
        '{"keyword": "street lamp", "n_ext": 6, "n_int": 4, "ancho": 0.3, "alto": 3.0}]'
    )
    try:
        import json as _json
        import re as _re
        llm = get_llm(provider)
        resp = llm.invoke(prompt).content.strip()
        match = _re.search(r'\[[\s\S]*\]', resp)
        if match:
            receta = _json.loads(match.group())
            logger.info(f"[Constructor/LLM] Receta ciudad: {[r['keyword'] for r in receta]}")
            return receta
    except Exception as e:
        logger.warning(f"[Constructor/LLM] Error generando receta de ciudad: {e}")
    return []


def _poblar_ambiente(
    tipo_ambiente: str,
    entorno: str,
    id_escena: str,
    radio_cilindro: float,
    provider: str,
    api_key: str,
    player_limit: float = 0.0,
    niebla_near: Optional[float] = None,
    niebla_far: Optional[float] = None,
) -> list[NodoEscena]:
    """
    Genera nodos de relleno ambiental (tipo='ambiente') para el fondo de la escena.
    - Usa la receta predefinida para tipos conocidos, o pide una al LLM para 'otro'.
    - Por cada keyword busca UN modelo en poly.pizza y lo instancia N veces.
    - Anillo exterior (r≈80-95%): elementos del horizonte lejano.
    - Anillo interior (r≈48-65%): profundidad intermedia (solo en exterior grande).

    Cuando se conocen las distancias de la niebla (`niebla_near`/`niebla_far`, solo
    exteriores), los anillos se recolocan COORDINADOS con la rampa: el anillo cercano
    vive en la parte clara de la niebla (lo que de verdad enmarca la zona jugable) y
    los anillos medio/lejano se empujan más allá de `niebla_far` (skyline tras la
    niebla). Así ningún objeto de relleno queda pintado al ~90 % del color de niebla
    en reposo para luego 'levantarse' al acercarse el jugador.
    """
    if tipo_ambiente in _AMBIENTES_PROCEDURALES:
        logger.info(f"[Constructor] '{tipo_ambiente}' usa generación procedural en JS — sin nodos de relleno")
        return []

    es_exterior_grande = radio_cilindro > 10.0
    # Escala los counts según el tamaño del cilindro; mínimo 40% para interiores
    escala = max(0.4, radio_cilindro / 24.0)

    if tipo_ambiente == "naturaleza":
        receta = _receta_naturaleza(entorno, provider)
    elif tipo_ambiente == "otro":
        receta = _pedir_receta_llm(entorno, provider)
    elif tipo_ambiente == "ciudad":
        # El LLM elige props acordes a la época/carácter de esta ciudad concreta.
        # Si falla, cae a la receta fija de 'ciudad'.
        receta = _receta_ciudad(entorno, provider) or RECETAS_AMBIENTE.get("ciudad", [])
    else:
        receta = RECETAS_AMBIENTE.get(tipo_ambiente, [])

    if not receta:
        logger.info(f"[Constructor] Sin receta de ambiente para '{tipo_ambiente}'")
        return []

    nodos: list[NodoEscena] = []
    if niebla_near is not None and niebla_far is not None and niebla_far > niebla_near:
        # Anillos coordinados con la niebla (exteriores).
        banda = niebla_far - niebla_near
        # Cercano: justo fuera de la zona transitable y en la parte CLARA de la rampa
        # (niebla ≲45 %), para que enmarque la zona jugable sin leerse como capa plana
        # ni 'levantarse' al acercarse el jugador.
        r_near_min = max(player_limit + 0.8, radio_cilindro * 0.28)
        r_near_max = niebla_near + 0.45 * banda
        if r_near_max < r_near_min + 1.2:
            r_near_max = r_near_min + 1.2
        # Medio y lejano: detrás de niebla_far (skyline), nunca alcanzables hasta
        # despejarse, así que su 'levantado' al acercarse es inapreciable.
        r_mid_min  = max(niebla_far + 0.5, radio_cilindro * 0.62)
        r_mid_max  = radio_cilindro * 0.78
        r_far_min  = radio_cilindro * 0.82
        r_far_max  = radio_cilindro * 0.95
    else:
        # Interior/cueva (sin niebla coordinada): bandas por porcentaje del radio.
        r_far_min  = radio_cilindro * 0.80
        r_far_max  = radio_cilindro * 0.95
        r_mid_min  = radio_cilindro * 0.50
        r_mid_max  = radio_cilindro * 0.65
        # Anillo cercano: justo fuera de la zona transitable (para que enmarque el área
        # jugable sin que el jugador lo atraviese) y dentro de la banda visible (antes de
        # la niebla). Es el anillo que de verdad se ve.
        r_near_min = max(radio_cilindro * 0.30, player_limit + 1.0)
        r_near_max = max(r_near_min + 2.5, radio_cilindro * 0.55)

    for idx, item in enumerate(receta):
        keyword = item["keyword"]
        ancho   = float(item.get("ancho", 1.0))
        alto    = float(item.get("alto",  1.0))
        ban     = item.get("ban", [])
        n_far   = max(0, round(item.get("n_ext", 0) * escala))
        n_int   = max(0, round(item.get("n_int", 0) * escala)) if es_exterior_grande else 0
        # Solo los elementos PEQUEÑOS pueblan el anillo cercano: los grandes (casas,
        # árboles, columnas...) destrozarían la zona jugable, así que se quedan al fondo
        # como skyline. El anillo lejano queda casi siempre TRAS la niebla (invisible),
        # así que de los pequeños traemos parte a la banda cercana visible.
        es_pequeno = (alto <= 1.5 and ancho <= 1.5)
        if es_pequeno:
            n_far_visible = max(0, round(n_far * 0.5))
            extra_near    = n_far - n_far_visible
            n_near  = max(0, round(n_int * 0.6) + extra_near)
            n_mid   = max(0, n_int - round(n_int * 0.6))
            n_far   = n_far_visible
        else:
            n_near  = 0                 # los grandes nunca en el anillo cercano
            n_mid   = n_int             # su "intermedio" va al anillo medio, no al cercano

        if n_far + n_mid + n_near == 0:
            continue

        logger.info(f"[Constructor/Ambiente] '{keyword}' — buscando modelo ({n_far} far + {n_mid} mid + {n_near} near)...")

        # Una sola búsqueda en poly.pizza; el modelo se reutiliza en todas las instancias
        gltf_url = _buscar_polypizza(keyword, api_key, ban=ban)
        if not gltf_url:
            kw_ref = _refinar_keyword_modelo(keyword, "decorado", [keyword], provider)
            gltf_url = _buscar_polypizza(kw_ref, api_key)
            if gltf_url:
                keyword = kw_ref

        # Generar instancias en los tres anillos
        for anillo_idx, (n, r_min, r_max) in enumerate([
            (n_far,  r_far_min,  r_far_max),
            (n_mid,  r_mid_min,  r_mid_max),
            (n_near, r_near_min, r_near_max),
        ]):
            if n == 0:
                continue
            # Desfase por keyword+anillo: proporción áurea para separación máxima entre especies
            phase = ((idx * 3 + anillo_idx) * 0.618033988 * 2 * math.pi) % (2 * math.pi)
            for j in range(n):
                angulo = phase + (j / n) * 2 * math.pi + (_random.random() - 0.5) * (2 * math.pi / max(n, 1))
                r      = r_min + _random.random() * (r_max - r_min)
                _lim   = radio_cilindro * 0.99
                x      = round(max(-_lim, min(_lim, r * math.sin(angulo))), 2)
                z      = round(max(-_lim, min(_lim, r * math.cos(angulo))), 2)
                # Variación de tamaño ±20% para evitar que parezcan clonados
                var    = 1.0 + _random.uniform(-0.2, 0.2)
                nodos.append(NodoEscena(
                    id=f"amb_{idx:02d}_{anillo_idx}_{j:02d}",
                    nombre=keyword,
                    tipo="ambiente",
                    origen=None,
                    posicion=Vector3(x=x, y=round(alto * var / 2, 2), z=z),
                    ancho=round(max(0.1, ancho * var), 2),
                    alto=round(max(0.1, alto  * var), 2),
                    voltear_horizontal=_random.random() > 0.5,
                    capa=1,
                    gltf_url=gltf_url,
                    keyword_busqueda=keyword,
                ))

        time.sleep(0.3)

    logger.info(
        f"[Constructor] Ambiente '{tipo_ambiente}': {len(nodos)} nodos generados "
        f"({len(receta)} keywords × instancias)"
    )
    return nodos


def _es_humanoide(nombre: str, keyword: str, descripcion: str, provider: str) -> bool:
    """
    Pregunta al LLM si el personaje es humano o humanoide (bípedo con cuerpo humano:
    personas, elfos, zombies, brujas, duendes, demonios...) o no
    (animal real, criatura sin forma humana, objeto inanimado).

    Decide SOBRE TODO por la descripción física, no por el nombre/keyword (un personaje
    apodado "Pitbull" o "Tigre" sigue siendo una persona si la física describe a un humano).

    Fallback seguro: True (Quaternius) si el LLM falla.
    """
    prompt = (
        f'Is the character "{nombre}" a human or humanoid?\n'
        f'Physical description: "{descripcion}"\n'
        f'(3D model search keyword: "{keyword}")\n'
        f'Humanoid = human, elf, dwarf, goblin, zombie, witch, demon, orc, '
        f'or any bipedal figure with a human-like body structure and arms.\n'
        f'Non-humanoid = real animal (duck, wolf, horse, bird...), '
        f'creature without human body form, or inanimate object.\n'
        f'IMPORTANT: base your decision on the PHYSICAL DESCRIPTION, which describes the real '
        f'body. The NAME or keyword can be misleading: a person nicknamed "Pitbull", "Tiger" or '
        f'"Lobo" is still a HUMAN if the description depicts a person.\n'
        f'Answer ONLY "yes" (humanoid) or "no" (non-humanoid).'
    )
    try:
        llm = get_llm(provider)
        resp = llm.invoke(prompt).content.strip().lower()
        result = resp.startswith("yes") or resp.startswith("sí") or resp.startswith("si ")
        logger.info(
            f"[Constructor] '{nombre}' (kw: '{keyword}') → "
            f"{'humanoide ✓' if result else 'no-humanoide → poly.pizza'}"
        )
        return result
    except Exception as e:
        logger.warning(f"[Constructor] _es_humanoide error para '{nombre}': {e} — asumiendo humanoide")
        return True  # fallback seguro: Quaternius


def _genero_descripcion(descripcion: str) -> Optional[str]:
    """Detecta el género ('F'/'M') de un personaje a partir de su descripción física,
    o None si es ambiguo. Solo palabras de género inequívocas (evita roles tipo 'mago')."""
    d = (descripcion or "").lower()
    fem = any(w in d for w in (
        "mujer", "niña", "anciana", "chica", "muchacha", "dama", "reina", "señora",
        "abuela", "madre", "hija", "esposa", "female", "woman", "girl",
    ))
    masc = any(w in d for w in (
        "hombre", "niño", "anciano", "chico", "muchacho", "rey", "señor",
        "abuelo", "padre", "hijo", "esposo", "male", "man ", "boy",
    ))
    if fem and not masc:
        return "F"
    if masc and not fem:
        return "M"
    return None


def _elegir_skin_personaje(
    elem: ElementoEscena,
    atmosfera: str,
    provider: str,
) -> SkinPersonaje:
    """
    Llama al LLM para que elija el GLB más adecuado del catálogo Quaternius
    y decida skin_tone y hair_color según la descripción del personaje.
    Python añade clothing_seed (tirada de dado única).

    Devuelve un SkinPersonaje listo para usar.
    """
    import json as _json, re as _re

    # ── Preparar lista de opciones para el LLM ────────────────────────────
    opciones_texto = "\n".join(
        f'{i+1:2}. [{p["id"]}] {p["label"]} — {p["descripcion"]}'
        for i, p in enumerate(PERSONAJES)
    )

    skin_tones_txt  = ", ".join(f'"{t}"' for t in SKIN_TONES)
    hair_colors_txt = ", ".join(f'"{c}"' for c in HAIR_COLORS)
    tallas_txt      = ", ".join(f'"{t}"' for t in TALLAS)

    prompt = (
        "You are casting a character for a 3D narrative scene.\n\n"
        f"Character to cast: \"{elem.nombre}\"\n"
        f"Visual hint: \"{elem.descripcion}\"\n"
        f"Scene atmosphere: \"{atmosfera}\"\n\n"
        "Available character models:\n"
        f"{opciones_texto}\n\n"
        "Choose the best matching character and decide their appearance.\n\n"
        "Rules:\n"
        "- Pick the [id] whose description best fits the character's role and appearance.\n"
        "- ROLE/PROFESSION: match the character's role to the right TYPE of model. Military figures "
        "(soldiers, guards, sentries, officers) → a soldier/knight model; nobles or high-rank people → "
        "an elegant/refined model; workers or common folk → a worker/casual model. Use each model's "
        "label and description to pick the most coherent type.\n"
        "- GENDER (important): match the character's gender to the model. If the visual hint "
        "describes a woman/girl (mujer, niña, chica, anciana, dama, reina...) → pick a model whose "
        "id contains 'Female'. If a man/boy (hombre, niño, chico, anciano, rey...) → a 'Male' model. "
        "Never give a female character a male body or vice versa.\n"
        "- skin_tone: one of " + skin_tones_txt + " — only if the character has human/humanoid skin. "
        "Otherwise null (non-human characters like goblins, zombies, animals have fixed skin).\n"
        "- hair_color: one of " + hair_colors_txt + " — only if the character has visible hair. "
        "Otherwise null.\n"
        "- Be creative but coherent: a wizard elder fits 'blanco' or 'gris' hair; "
        "a young rebel might have 'rojo' or 'azul' fantasy hair.\n"
        "- talla: one of " + tallas_txt + ". "
        "adulto_alto=tall warrior/robed mage, adulto_medio=standard adult, "
        "adulto_bajo=elderly/shorter adult, nino_enano=child/goblin/small creature. "
        "Default by character type unless the narrative says otherwise.\n\n"
        "Respond with ONLY a valid JSON object, no markdown:\n"
        '{"razonamiento": "brief reason", "glb_id": "...", "skin_tone": "..." or null, '
        '"hair_color": "..." or null, "talla": "..."}'
    )

    glb_id     = PERSONAJES[0]["id"]   # fallback
    skin_tone  = "medio"
    hair_color = None
    talla      = None   # se resuelve abajo desde TALLA_DEFECTO si el LLM no responde

    try:
        llm = get_llm(provider)
        resp = llm.invoke(prompt).content.strip()
        match = _re.search(r'\{[\s\S]*\}', resp)
        if match:
            data = _json.loads(match.group())
            raw_id = data.get("glb_id", "")
            if raw_id in CATALOGO:
                glb_id = raw_id
            raw_skin  = data.get("skin_tone")
            raw_hair  = data.get("hair_color")
            raw_talla = data.get("talla")
            skin_tone  = raw_skin  if raw_skin  in SKIN_TONES else None
            hair_color = raw_hair  if raw_hair  in HAIR_COLORS else None
            talla      = raw_talla if raw_talla in TALLAS else None
            logger.info(
                f"[Constructor/Skin] '{elem.nombre}' → [{glb_id}] "
                f"skin={skin_tone} hair={hair_color} talla={talla}  "
                f"({data.get('razonamiento','')})"
            )
    except Exception as e:
        logger.warning(f"[Constructor/Skin] Error eligiendo skin para '{elem.nombre}': {e}")

    # ── Guard de género: si la descripción indica un género y el modelo elegido es del
    #    opuesto, intercambia a la variante del mismo modelo (Casual_Male ↔ Casual_Female)
    #    si existe en el catálogo. Red de seguridad por si el LLM falla el género.
    _genero = _genero_descripcion(elem.descripcion)
    if _genero == "F" and "_Male" in glb_id:
        _alt = glb_id.replace("_Male", "_Female")
        if _alt in CATALOGO:
            logger.info(f"[Constructor/Skin] '{elem.nombre}': género F → {glb_id} ⇒ {_alt}")
            glb_id = _alt
    elif _genero == "M" and "_Female" in glb_id:
        _alt = glb_id.replace("_Female", "_Male")
        if _alt in CATALOGO:
            logger.info(f"[Constructor/Skin] '{elem.nombre}': género M → {glb_id} ⇒ {_alt}")
            glb_id = _alt

    # ── Aplicar restricciones del catálogo ───────────────────────────────
    entrada = CATALOGO.get(glb_id, PERSONAJES[0])

    if not entrada["permite_skin_humana"]:
        skin_tone = None   # skin fija del catálogo

    if not entrada["tiene_hair"]:
        hair_color = None  # sin pelo personalizable

    # ── Calcular hex de piel ─────────────────────────────────────────────
    if skin_tone:
        skin_hex = SKIN_TONE_HEX[skin_tone]
    else:
        skin_hex = entrada.get("skin_defecto_hex") or "#D4956A"

    # Talla: LLM puede proponer, pero TALLA_DEFECTO del catálogo tiene prioridad
    # si el LLM no respondió o el valor no es válido
    talla_final = talla or TALLA_DEFECTO.get(glb_id, "adulto_medio")

    return SkinPersonaje(
        glb_id=glb_id,
        glb_path=f"/sandbox/assets/characters/{glb_id}.gltf",
        skin_tone=skin_tone,
        skin_hex=skin_hex,
        hair_color=hair_color,
        clothing_seed=_random.randint(1, 9999),
        talla=talla_final,
        animacion_idle="Idle",
        animacion_talk=entrada["animacion_talk"],
    )


def _ajustar_coherencia_escena(
    nodos: list,
    *,
    entorno: str,
    radio_cilindro: float,
    provider: str,
) -> int:
    """
    Pase de COHERENCIA DE TAMAÑOS con los modelos ya elegidos. El LLM ve la escena entera
    —cada objeto/decorado con su nombre, modelo y tamaño actual— y reajusta los tamaños
    RELATIVOS para que sean realistas (una mesilla < una cama, una vela ≈ 0.25). NO toca
    posiciones: la colocación (pared vs centro) la decide el Director.

    Por objeto fija 'tam_real' = su dimensión real mayor, que el viewer usa como ancla de
    escala invariante a la orientación. Todo candidato sin 'tam_real' recibe su dimensión
    mayor declarada → así NINGÚN objeto cae al encaje-en-caja viejo, que dejaba enanos los
    modelos con proporciones raras.

    Degradado seguro: ante cualquier fallo conserva los tamaños del Director.
    """
    import json as _json
    candidatos = [n for n in nodos if n.tipo in ("objeto", "decorado")]
    n_aplicados = 0

    if len(candidatos) >= 2:
        items = [
            {"id": n.id, "nombre": n.nombre, "modelo": n.keyword_busqueda or n.nombre,
             "tam": round(max(n.ancho, n.alto), 2)}
            for n in candidatos
        ]
        prompt = (
            "Eres el director artístico de una escena 3D. Los modelos ya están elegidos; "
            "corrige SOLO las incoherencias de TAMAÑO mirando la escena EN CONJUNTO. No "
            "decides posiciones.\n\n"
            f"Entorno: \"{entorno}\"\n\n"
            "Objetos con su tamaño actual (orientativo). 'tam' = dimensión REAL mayor del "
            "objeto en metros (un humano adulto ≈ 1.7):\n"
            f"{_json.dumps(items, ensure_ascii=False)}\n\n"
            "Ajusta 'tam' para que las proporciones RELATIVAS sean realistas (una silla < "
            "una mesa < un armario; una vela ≈ 0.25; una alfombra por su largo ≈ 1.5-2.5; "
            "una cama por su largo ≈ 2.0; un escritorio ≈ 1.2; un libro ≈ 0.3). Cambios "
            "MÍNIMOS: corrige solo lo que chirríe. Responde SOLO con un array JSON de los "
            "ids que CAMBIES: [{\"id\":\"...\",\"tam\":1.4}]. Sin texto adicional, sin markdown."
        )
        try:
            llm = get_llm(provider)
            raw = llm.invoke(prompt).content
            import re as _re
            match = _re.search(r'\[.*\]', raw, _re.DOTALL)
            cambios = _json.loads(match.group()) if match else []
        except Exception as e:
            logger.warning(f"[Constructor/Tamaños] fallo (se conservan los del Director): {e}")
            cambios = []

        if isinstance(cambios, list):
            por_id = {n.id: n for n in candidatos}
            for c in cambios:
                if not isinstance(c, dict):
                    continue
                n = por_id.get(c.get("id"))
                if n is None or c.get("tam") is None:
                    continue
                try:
                    tam = max(0.15, min(float(c["tam"]), radio_cilindro * 0.9, 6.0))
                    base = max(n.ancho, n.alto, 0.01)
                    factor = tam / base
                    n.ancho = round(min(max(n.ancho * factor, 0.1), 50.0), 2)
                    n.alto  = round(min(max(n.alto  * factor, 0.1), 50.0), 2)
                    n.tam_real = round(tam, 2)
                    n.posicion.y = round(n.alto / 2, 2)
                    n_aplicados += 1
                except (TypeError, ValueError):
                    continue

    for n in candidatos:
        if n.tam_real is None:
            n.tam_real = round(max(n.ancho, n.alto), 2)

    if n_aplicados:
        logger.info(f"[Constructor/Tamaños] ✓ {n_aplicados} objeto(s) reajustado(s).")
    return n_aplicados


def ejecutar_constructor(
    salida_director: SalidaDirector,
    cielo: TipoCielo,
    tipo_ambiente: TipoAmbiente,
    entorno: str,
    atmosfera: str,
    provider: str = "mercury",
    scene_graphs_previos: Optional[dict] = None,
    registro_personajes: Optional[dict] = None,
    keywords_objetivo: Optional[dict] = None,
) -> SceneGraph:
    """
    Construye el SceneGraph a partir de la especificación del Director.

    Para fondo y suelo: crea nodos de geometría (sin prompt_imagen — color procedural en JS).
    Para personajes y objetos narrativos:
      - Busca hasta 5 modelos en poly.pizza con keyword_busqueda
      - Usa el LLM para elegir el más adecuado según el nombre del elemento
      - Si skin_ids[elem.id] apunta a una escena anterior, reutiliza su gltf_url
    Para decorados:
      - Usa directamente el primer resultado (sin coste de LLM)
    Si no se encuentra modelo, gltf_url queda en None (fallback de color).
    """
    if scene_graphs_previos  is None:
        scene_graphs_previos  = {}
    if registro_personajes is None:
        registro_personajes = {}
    if keywords_objetivo is None:
        keywords_objetivo = {}

    _reset_estado_poly()  # racha de timeouts limpia por escena (el server es de larga vida)

    # Ablación experimental (evaluación técnica): WW_ABLAR_REUSO=1 desactiva la reutilización
    # entre escenas de skin (Quaternius), modelo (poly.pizza) y tamaño, para medir la
    # degradación en consistencia de personajes recurrentes. En producción nunca está activo.
    _ablar_reuso = os.getenv("WW_ABLAR_REUSO") == "1"

    nodos:             list[NodoEscena]        = []
    registro_escena:   dict[str, SkinPersonaje] = {}   # skins resueltas en esta escena
    api_key = settings.polypizza_api_key

    # superficie_planeta / espacio requieren cielo nocturno-estelar: sin atmósfera,
    # un atardecer o amanecer no tiene sentido y queda muy mal visualmente.
    if tipo_ambiente in ("espacio", "superficie_planeta"):
        cielo = "noche_estrellada"

    # Detectar tipo de escena e importar parámetros geométricos correspondientes
    radio_cilindro, radio_por_fila, arco_por_fila, tipo_escena, player_limit = params_escena(
        cielo, tipo_ambiente
    )
    if tipo_ambiente == "bajo_el_agua":
        radio_cilindro = RADIO_CILINDRO_BAJO_AGUA
    alto_cilindro = 7.0 if tipo_escena == "interior" else 12.0

    # Cilindro de fondo panorámico
    nodos.append(NodoEscena(
        id=f"fondo_{salida_director.id_escena}",
        nombre="Fondo panorámico",
        tipo="fondo",
        posicion=Vector3(x=0.0, y=alto_cilindro / 2, z=0.0),
        ancho=radio_cilindro,
        alto=alto_cilindro,
        capa=0,
        prompt_imagen=None,
    ))

    # Suelo circular — color sólido por bioma en JS; espacio no tiene suelo
    if tipo_ambiente != "espacio":
        nodos.append(NodoEscena(
            id=f"suelo_{salida_director.id_escena}",
            nombre="Suelo",
            tipo="suelo",
            posicion=Vector3(x=0.0, y=0.0, z=0.0),
            ancho=radio_cilindro,
            alto=radio_cilindro,
            capa=0,
        ))

    # Barco: variante (→ radio de cubierta) + clasificación cubierta/agua de cada
    # elemento (LLM, fallback heurístico) + plan de posiciones (rejilla en cubierta,
    # anillos en el agua). Se hace ANTES del bucle para tener las posiciones listas.
    variante_barco = radio_cubierta_barco = plan_barco = None
    if tipo_ambiente == "barco":
        variante_barco = _elegir_variante_barco(salida_director.id_escena)
        radio_cubierta_barco = RADIO_CUBIERTA_BARCO[variante_barco]
        _zonas_barco = _clasificar_zona_barco(
            salida_director.elementos, entorno, atmosfera, provider
        )
        plan_barco = _planificar_barco(
            salida_director.elementos, _zonas_barco, radio_cubierta_barco, player_limit
        )

    # Elementos 3D
    total = len(salida_director.elementos)
    for i, elem in enumerate(salida_director.elementos, 1):
        # Tamaño canónico por skin_id: el mismo personaje/objeto debe medir igual en
        # todas las escenas. El Director redimensiona por escena sin memoria (puede dar
        # 1.9 en una y 0.8 en otra al mismo personaje); aquí fijamos el tamaño de su
        # primera aparición, reutilizando ancho/alto del nodo previo igual que el gltf_url.
        ancho_final, alto_final = elem.ancho, elem.alto
        _sid_tam = elem.skin_id
        if not _ablar_reuso and _sid_tam and _sid_tam != salida_director.id_escena and _sid_tam in scene_graphs_previos:
            _nodo_tam = next(
                (n for n in scene_graphs_previos[_sid_tam].nodos if n.id == elem.id),
                None,
            )
            if _nodo_tam:
                ancho_final, alto_final = _nodo_tam.ancho, _nodo_tam.alto

        # Suelo de visibilidad: un objeto narrativo muy pequeño (pico, cuchillo, pluma...) es
        # casi invisible en escena. Escalamos para que su dimensión mayor llegue a un mínimo,
        # manteniendo la proporción. Solo objetos (no personajes/decorados de fondo).
        if elem.tipo == "objeto":
            _MIN_OBJ = 0.5
            _mayor = max(ancho_final, alto_final)
            if 0 < _mayor < _MIN_OBJ:
                _f = _MIN_OBJ / _mayor
                ancho_final, alto_final = round(ancho_final * _f, 2), round(alto_final * _f, 2)

        if tipo_ambiente == "barco" and plan_barco is not None:
            # Barco: posición del plan (cubierta = rejilla rect dentro de la borda;
            # agua = anillos alrededor del casco). Ignora la rejilla cilíndrica del
            # Director, que dejaba a los narrativos pegados a la borda.
            _p = plan_barco.get(elem.id)
            if _p and _p[0] == "deck":
                # Radio efectivo < cubierta para que ni las celdas de borde toquen la borda.
                posicion = _grid_rect_a_posicion(
                    _p[1], _p[2], alto_final, radio_cubierta_barco * 0.82,
                )
                _seed = zlib.crc32(elem.id.encode())
                posicion.x = round(posicion.x + ((_seed & 0xffff) / 0xffff - 0.5) * 0.3, 2)
                posicion.z = round(posicion.z + (((_seed >> 16) & 0xffff) / 0xffff - 0.5) * 0.3, 2)
                capa = 5
            else:
                # Agua: y=0 (el viewer NO eleva lo que está fuera del radio de cubierta).
                _x, _z = (_p[1], _p[2]) if _p else (0.0, radio_cubierta_barco + 3.0)
                posicion = Vector3(x=_x, y=0.0, z=_z)
                capa = 8
        elif tipo_ambiente in ("habitacion", "interior", "interior_grande"):
            # Interiores construidos → rejilla rectangular del suelo (sin jitter radial)
            posicion = _grid_rect_a_posicion(
                elem.posicion_grid.columna, elem.posicion_grid.fila, alto_final, radio_cilindro,
            )
            # Jitter determinista (pequeño) para romper la cuadrícula sin atravesar la pared.
            _seed = zlib.crc32(elem.id.encode())
            posicion.x = round(posicion.x + ((_seed & 0xffff) / 0xffff - 0.5) * 0.4, 2)
            posicion.z = round(posicion.z + (((_seed >> 16) & 0xffff) / 0xffff - 0.5) * 0.4, 2)
            capa = elem.posicion_grid.fila  # orden de profundidad (z)
        else:
            posicion = _grid_a_posicion(
                elem.posicion_grid.columna, elem.posicion_grid.fila, alto_final,
                radio_por_fila, arco_por_fila,
            )
            posicion = _aplicar_jitter(posicion, elem.id, elem.posicion_grid.fila, arco_por_fila)
            capa = CAPA_POR_FILA.get(elem.posicion_grid.fila, 5)
            # Objetos/personajes GRANDES (un barco, una estatua, un árbol monumental...) se
            # empujan al BORDE de la zona jugable: quedan visibles y alcanzables, pero no
            # bloquean el centro de la escena. (En barco lo gestiona la lógica de cubierta.)
            _UMBRAL_GRANDE = 3.0  # metros (alto o ancho) a partir del cual se considera grande
            if (tipo_ambiente != "barco" and elem.tipo in ("objeto", "personaje")
                    and max(ancho_final, alto_final) >= _UMBRAL_GRANDE):
                _r_borde = max(player_limit - 0.3, 1.0)
                _ang = math.atan2(posicion.x, -posicion.z)
                posicion = Vector3(
                    x=round(_r_borde * math.sin(_ang), 2),
                    y=posicion.y,
                    z=round(-_r_borde * math.cos(_ang), 2),
                )
        # Prioridad de keyword para poly.pizza:
        #  1) Palabra del idioma objetivo (mundos de vocabulario): es el sustantivo inglés EXACTO
        #     ("watermelon", "pear") — el mejor término de búsqueda, evita que el LLM generalice a
        #     "fruit" y acabe eligiendo una naranja. Sin coste de LLM.
        #  2) Keyword fija del Director (mobiliario del filler: "dining set", "bookshelf"...).
        #  3) Derivada con el LLM desde nombre/descripción.
        keyword = keywords_objetivo.get(elem.id) \
            or getattr(elem, "keyword_busqueda", None) \
            or _generar_keyword_inicial(elem.nombre, elem.descripcion, elem.tipo, provider)

        gltf_url = None
        skin: Optional[SkinPersonaje] = None

        # ── PERSONAJES ───────────────────────────────────────────────────────
        if elem.tipo == "personaje":
            sid = elem.skin_id
            escena_actual = salida_director.id_escena
            humanoide = _es_humanoide(elem.nombre, keyword, elem.descripcion or "", provider)

            if humanoide:
                # ── Humano/humanoide → catálogo Quaternius con animaciones ──
                if not _ablar_reuso and sid and sid != escena_actual and elem.id in registro_personajes:
                    skin = registro_personajes[elem.id]
                    logger.info(
                        f"[Constructor] '{elem.id}': skin copiada de escena '{sid}' "
                        f"→ [{skin.glb_id}] skin={skin.skin_tone} hair={skin.hair_color}"
                    )
                else:
                    logger.info(
                        f"[Constructor] [{i}/{total}] '{elem.id}' (personaje humanoide) "
                        f"— eligiendo del catálogo Quaternius..."
                    )
                    skin = _elegir_skin_personaje(elem, atmosfera, provider)
                gltf_url = skin.glb_path
                registro_escena[elem.id] = skin

            else:
                # ── Animal/criatura/objeto → poly.pizza, sin animaciones ──
                logger.info(
                    f"[Constructor] [{i}/{total}] '{elem.id}' (personaje no-humano: '{elem.nombre}') "
                    f"— buscando '{keyword}' en poly.pizza..."
                )
                # Reutilizar de escena anterior si tiene skin_id
                if not _ablar_reuso and sid and sid != escena_actual and sid in scene_graphs_previos:
                    nodo_previo = next(
                        (n for n in scene_graphs_previos[sid].nodos if n.id == elem.id),
                        None,
                    )
                    if nodo_previo and nodo_previo.gltf_url:
                        gltf_url = nodo_previo.gltf_url
                        logger.info(f"[Constructor] '{elem.id}': modelo reutilizado de '{sid}'")

                keywords_usadas = [keyword]
                for intento in range(3) if not gltf_url else []:
                    if intento > 0:
                        keyword = _refinar_keyword_modelo(
                            elem.nombre, elem.tipo, keywords_usadas, provider
                        )
                        keywords_usadas.append(keyword)
                    resultados = _buscar_resultados_polypizza(keyword, api_key)
                    gltf_url = _elegir_mejor_modelo(
                        nombre=elem.nombre, tipo="objeto",
                        resultados=resultados, provider=provider,
                    )
                    if gltf_url:
                        break

                if not gltf_url:
                    logger.warning(
                        f"[Constructor] '{elem.id}': sin modelo en poly.pizza. "
                        f"Sandbox usará fallback de color."
                    )

        # ── OBJETOS Y DECORADOS → poly.pizza ────────────────────────────────
        else:
            logger.info(
                f"[Constructor] [{i}/{total}] '{elem.id}' ({elem.tipo}) "
                f"— buscando '{keyword}' en poly.pizza..."
            )

            # Reutilizar modelo de escena anterior si el elemento mantiene la misma skin
            if elem.tipo == "objeto":
                sid = elem.skin_id
                if sid and sid != salida_director.id_escena and sid in scene_graphs_previos:
                    nodo_previo = next(
                        (n for n in scene_graphs_previos[sid].nodos if n.id == elem.id),
                        None,
                    )
                    if nodo_previo and nodo_previo.gltf_url:
                        gltf_url = nodo_previo.gltf_url
                        logger.info(
                            f"[Constructor] '{elem.id}': modelo objeto reutilizado de '{sid}'"
                        )

            keywords_usadas = [keyword]

            for intento in range(3) if not gltf_url else []:
                if intento > 0:
                    keyword = _refinar_keyword_modelo(
                        elem.nombre, elem.tipo, keywords_usadas, provider
                    )
                    keywords_usadas.append(keyword)
                    logger.info(
                        f"[Constructor] [{i}/{total}] '{elem.id}' reintento {intento}/2 "
                        f"— keyword refinada: '{keyword}'"
                    )

                if elem.tipo == "objeto":
                    resultados = _buscar_resultados_polypizza(keyword, api_key)
                    if resultados:
                        logger.debug(
                            f"[Constructor] '{elem.id}': opciones → "
                            f"{[r.get('Title','?') for r in resultados]}"
                        )
                    gltf_url = _elegir_mejor_modelo(
                        nombre=elem.nombre, tipo=elem.tipo,
                        resultados=resultados, provider=provider,
                    )
                else:
                    gltf_url = _buscar_polypizza(keyword, api_key)

                if gltf_url:
                    break

            if not gltf_url:
                kws = " → ".join(f"'{k}'" for k in keywords_usadas)
                logger.warning(
                    f"[Constructor] '{elem.id}' ('{elem.nombre}'): sin modelo tras "
                    f"{len(keywords_usadas)} intentos. Keywords probadas: {kws}. "
                    f"Sandbox usará fallback de color."
                )

        nodo = NodoEscena(
            id=elem.id,
            nombre=elem.nombre,
            tipo=elem.tipo,
            origen=elem.origen,
            posicion=posicion,
            ancho=ancho_final,
            alto=alto_final,
            capa=capa,
            gltf_url=gltf_url,
            # Personajes humanos usan catálogo Quaternius — no tiene keyword de búsqueda.
            # Personajes no-humanos y el resto van por poly.pizza — guardamos la keyword.
            keyword_busqueda=keyword if (elem.tipo != "personaje" or not skin) else None,
        )
        nodos.append(nodo)

        # (El mobiliario colectivo —varios pupitres/mesas/estanterías— lo emite el DIRECTOR
        # como elementos numerados (pupitre_01, _02...); el Constructor no clona nada.)

        logger.debug(
            f"[Constructor] {elem.id:35} ({elem.tipo:10}) "
            f"grid({elem.posicion_grid.columna},{elem.posicion_grid.fila}) "
            f"→ ({posicion.x:+.2f}, {posicion.y:.2f}, {posicion.z:+.2f}) "
            f"{ancho_final:.1f}×{alto_final:.1f} "
            f"{'✓ ' + (gltf_url[:40] + '...') if gltf_url else '✗ sin modelo'}"
        )

        # Pequeña pausa para no sobrecargar la API
        if i < total:
            time.sleep(0.3)

    # Cielo + niebla — se computan ANTES del relleno ambiental para que los anillos
    # de fondo se coloquen coordinados con la rampa de niebla (ver _poblar_ambiente).
    cielo_config = _generar_cielo(cielo)
    if tipo_escena != "interior":
        cielo_config.niebla = _calcular_niebla(
            cielo_config, tipo_ambiente, radio_cilindro, player_limit
        )
    else:
        # Interiores: qué luz entra por las ventanas, fiel a la hora de la historia.
        cielo_config.luz_exterior = _inferir_luz_exterior(atmosfera, entorno, cielo)

    # Relleno ambiental (solo si hay tipo_ambiente definido y no es interior)
    if tipo_escena != "interior" or tipo_ambiente in ("cueva",):
        niebla_near = cielo_config.niebla["near"] if cielo_config.niebla else None
        niebla_far  = cielo_config.niebla["far"]  if cielo_config.niebla else None
        nodos_ambiente = _poblar_ambiente(
            tipo_ambiente=tipo_ambiente,
            entorno=entorno,
            id_escena=salida_director.id_escena,
            radio_cilindro=radio_cilindro,
            provider=provider,
            api_key=api_key,
            player_limit=player_limit,
            niebla_near=niebla_near,
            niebla_far=niebla_far,
        )
        nodos.extend(nodos_ambiente)

    # Pase de coherencia (director artístico) con los modelos ya elegidos. Corre ANTES
    # de las reparaciones deterministas, que actúan de red de seguridad sobre su salida.
    _ajustar_coherencia_escena(
        nodos, entorno=entorno, radio_cilindro=radio_cilindro, provider=provider,
    )

    _reparar_colisiones_3d(nodos)

    # Garantía dura: narrativos siempre dentro del alcance (clamp radial exterior/barco).
    if tipo_escena == "exterior":
        _clamp_narrativos_alcance(nodos, player_limit)

    encontrados = sum(1 for n in nodos if n.gltf_url)
    elementos = len(nodos) - 2  # sin fondo ni suelo
    logger.info(
        f"[Constructor] ✓ '{salida_director.id_escena}': {len(nodos)} nodos "
        f"({encontrados}/{elementos} modelos 3D encontrados, "
        f"{elementos - encontrados} con fallback)"
    )
    color_suelo = None
    if tipo_ambiente == "superficie_planeta":
        color_suelo = _color_superficie_planeta(entorno, provider)

    tipo_suelo = tipo_techo = None
    if tipo_ambiente == "otro":
        tipo_suelo, tipo_techo = _elegir_atmosfera_otro(entorno, atmosfera, provider)
        # Suelo de nubes → garantiza cielo abierto de día (no interior ni noche) detrás del
        # mar de nubes; si el Organizador eligió un cielo cerrado, lo reemplazamos.
        if tipo_suelo == "nubes" and (cielo.startswith("interior") or cielo.startswith("noche")):
            cielo_config = _generar_cielo("manana_despejada")

    return SceneGraph(
        id_escena=salida_director.id_escena,
        tipo_escena=tipo_escena,
        tipo_ambiente=tipo_ambiente,
        radio_escena=radio_cilindro,
        limite_jugador=player_limit,
        color_suelo=color_suelo,
        tipo_suelo=tipo_suelo,
        tipo_techo=tipo_techo,
        radio_cubierta=radio_cubierta_barco,
        variante_barco=variante_barco,
        nodos=nodos,
        cielo=cielo_config,
        registro_personajes=registro_escena,
    )