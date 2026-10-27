"""
Pipeline LangGraph de WorldWeaver.

Grafo:
  START
    → organizador → validar_organizador ─[ok]──→ director ←──────────────────┐
                                        ─[falla]→ organizador                 │
                                                      ↓                       │
                                             validar_director ─[ok]──→ constructor
                                                              ─[falla]────────┘
                                                                   ↓
                                                        validar_constructor
                                                                   ↓ [ok — determinístico, sin retry]
                                                              programador ←──────────────┐
                                                                   ↓                     │
                                                        validar_programador ─[falla]─────┘
                                                                   ↓ [ok]
                                                                músico
                                                                   ↓
                                                              ensamblador
                                                                   ↓
                                              [más escenas?] ──→ director (siguiente escena)
                                              [fin]          ──→ END

Los fondos y suelos se renderizan proceduralmente en Three.js — no hay agente
de generación de imágenes en el pipeline.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

# El pipeline imprime banners y errores de validación con caracteres Unicode (✗ ✓ ═ → •).
# En una consola Windows con codificación heredada (cp1252) un print de esos lanza
# UnicodeEncodeError y tumba TODO el pipeline justo al reportar un error de validación.
# Forzamos UTF-8 en stdout/stderr una sola vez. Guardado: si el stream no existe
# (exe en modo ventana) o ya está configurado, se ignora silenciosamente.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

from agents.organizador import ejecutar_organizador
from agents.director import ejecutar_director
from agents.constructor import ejecutar_constructor
from agents.programador import ejecutar_programador
from agents.musico import ejecutar_musico
from agents.examinador import ejecutar_examinador
from pipeline.ensamblador import ensamblar, generar_quiz_html
from pipeline.errors import AgentError, SinNarrativa
from pipeline.state import WorldWeaverState
from config.settings import settings
from pipeline.validators import (
    validar_organizador,
    validar_director,
    validar_constructor,
    validar_programador,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = settings.max_retries   # reintentos por agente LLM (.env: MAX_RETRIES)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _guardar(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"   [OK] {path.name}")


def _slug(texto: str, fallback: str = "historia") -> str:
    """Convierte un título en un nombre de fichero seguro (ej: 'El Patito Feo' → 'el_patito_feo')."""
    s = (texto or "").strip().lower()
    # Reemplazar acentos comunes para legibilidad del nombre de fichero
    for a, b in zip("áàäâéèëêíìïîóòöôúùüûñ", "aaaaeeeeiiiioooouuuun"):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return (s[:60] or fallback)


def _escena_activa(state: WorldWeaverState):
    """Devuelve la Escena que se está procesando ahora."""
    idx = state.get("escena_activa", 0)
    return state["salida_organizador"].escenas[idx]


def _feedback_error(errores: list[str]) -> HumanMessage:
    """Mensaje de feedback que se añade al historial para el siguiente reintento."""
    texto = "\n".join(f"- {e}" for e in errores)
    return HumanMessage(
        content=(
            f"Tu respuesta anterior produjo los siguientes errores de validación:\n"
            f"{texto}\n\n"
            "Corrígela y devuelve SOLO el JSON válido, sin texto adicional."
        )
    )


def _incrementar_reintento(state: WorldWeaverState, agente: str) -> dict:
    reintentos = dict(state.get("reintentos", {}))
    reintentos[agente] = reintentos.get(agente, 0) + 1
    return reintentos


# ─── Nodos agente ─────────────────────────────────────────────────────────────

def nodo_organizador(state: WorldWeaverState) -> dict:
    print("\n--- [1/5] Organizador ---")
    # Reanudación / regeneración de una escena: la salida del Organizador ya viene del
    # disco (ver estado_desde_disco). Volver a llamarlo podría reescribir las escenas.
    if state.get("salida_organizador") is not None and not state.get("errores_organizador"):
        print("   (salida cargada del disco — sin llamada al LLM)")
        return {"errores_organizador": []}
    provider = state.get("provider", "mercury")
    mensajes = state.get("mensajes_organizador") or []

    # En reintento: añadir feedback de error al historial
    errores_prev = state.get("errores_organizador", [])
    if errores_prev and mensajes:
        mensajes = mensajes + [_feedback_error(errores_prev)]
        n = state.get("reintentos", {}).get("organizador", 0)
        print(f"   [Reintento {n}/{MAX_RETRIES}] Errores previos: {errores_prev}")

    try:
        salida, mensajes_nuevos = ejecutar_organizador(
            state["texto_original"],
            provider=provider,
            mensajes_previos=mensajes or None,
            modo=state.get("modo", "narrativo"),
            idioma=state.get("idioma", "es"),
        )
        print(f"   {len(salida.escenas)} escenas: {[e.id for e in salida.escenas]}")
        primera = salida.escenas[0]
        print(f"\n{'='*55}")
        print(f"  Escena inicial: {primera.id} — {primera.titulo}")
        print(f"{'='*55}")
        # Clasificación educativa: solo se calcula en el primer intento (salida la trae
        # poblada). En reintentos viene None → la restauramos desde el estado para que
        # Programador y Examinador la sigan viendo. También la copiamos a la salida.
        subtipo = salida.subtipo_educativo or state.get("subtipo_educativo")
        tipo_vocab = salida.tipo_vocabulario or state.get("tipo_vocabulario")
        idioma_obj = salida.idioma_objetivo or state.get("idioma_objetivo")
        salida.subtipo_educativo = subtipo
        salida.tipo_vocabulario = tipo_vocab
        salida.idioma_objetivo = idioma_obj
        return {
            "salida_organizador": salida,
            "mensajes_organizador": mensajes_nuevos,
            "errores_organizador": [],
            "subtipo_educativo": subtipo,
            "tipo_vocabulario": tipo_vocab,
            "idioma_objetivo": idioma_obj,
        }
    except SinNarrativa:
        raise  # texto sin historia: fallar rápido (sin reintentos) hacia el servidor
    except AgentError as e:
        logger.warning(f"[Organizador] Error: {e}")
        update = {
            "mensajes_organizador": e.messages,  # incluye la respuesta fallida del LLM
            "errores_organizador": [str(e)],
        }
        # Persistir la clasificación educativa aunque este intento falle: se calculó antes
        # de la llamada principal y los reintentos no reclasifican (la perderían a None).
        meta = getattr(e, "meta", None)
        if meta:
            update["subtipo_educativo"] = meta.get("subtipo_educativo")
            update["tipo_vocabulario"] = meta.get("tipo_vocabulario")
            update["idioma_objetivo"] = meta.get("idioma_objetivo")
        return update
    except Exception as e:
        logger.warning(f"[Organizador] Error irrecuperable: {e}")
        return {
            "mensajes_organizador": mensajes,
            "errores_organizador": [str(e)],
        }


def nodo_director(state: WorldWeaverState) -> dict:
    escena = _escena_activa(state)
    idx = state.get("escena_activa", 0)
    total = len(state["salida_organizador"].escenas)
    print(f"\n--- [2/5] Director — {escena.id} ({idx+1}/{total}) ---")

    provider = state.get("provider", "mercury")
    mensajes = state.get("mensajes_director") or []

    errores_prev = state.get("errores_director", [])
    if errores_prev and mensajes:
        mensajes = mensajes + [_feedback_error(errores_prev)]
        n = state.get("reintentos", {}).get("director", 0)
        print(f"   [Reintento {n}/{MAX_RETRIES}] Errores previos:")
        for e in errores_prev:
            print(f"     ✗ {e}")

    try:
        salida, mensajes_nuevos = ejecutar_director(
            escena,
            provider=provider,
            mensajes_previos=mensajes or None,
            idioma=state.get("idioma", "es"),
        )
        return {
            "salida_director": salida,
            "mensajes_director": mensajes_nuevos,
            "errores_director": [],
        }
    except AgentError as e:
        logger.warning(f"[Director] Error: {e}")
        return {
            "mensajes_director": e.messages,  # incluye la respuesta fallida del LLM
            "errores_director": [str(e)],
        }
    except Exception as e:
        logger.warning(f"[Director] Error irrecuperable: {e}")
        return {
            "mensajes_director": mensajes,
            "errores_director": [str(e)],
        }


def nodo_constructor(state: WorldWeaverState) -> dict:
    print("\n--- [3/5] Constructor ---")
    provider           = state.get("provider", "mercury")
    sg_previos         = state.get("scene_graphs_previos", {})
    registro_previo    = state.get("registro_personajes", {})
    escena             = _escena_activa(state)

    # Mundos de vocabulario: el nombre en el idioma objetivo (inglés) es el término EXACTO
    # de búsqueda en poly.pizza para ese objeto ("watermelon", "pear"). Se lo damos al
    # Constructor para que no derive una keyword genérica con el LLM (que confundía sandía→naranja).
    import re as _re
    keywords_objetivo = {
        o.id: _re.sub(r"==(.+?)==", r"\1", o.nombre_objetivo).strip()
        for o in escena.objetos
        if (o.nombre_objetivo or "").strip()
    }

    sg = ejecutar_constructor(
        state["salida_director"],
        cielo=escena.cielo,
        tipo_ambiente=escena.tipo_ambiente,
        entorno=escena.entorno,
        atmosfera=escena.atmosfera,
        provider=provider,
        scene_graphs_previos=sg_previos,
        registro_personajes=registro_previo,
        keywords_objetivo=keywords_objetivo,
    )

    # Idiomas conversacional (Tipo B): los personajes conversan → que se miren entre sí en el viewer.
    if (state.get("tipo_vocabulario") == "conversacional"
            and getattr(escena, "rol_escena", None) == "exposicion"):
        sg.escena_conversacion = True

    encontrados = sum(1 for n in sg.nodos if n.gltf_url)
    total_elem  = sum(1 for n in sg.nodos if n.tipo not in ("fondo", "suelo"))
    n_personajes = sum(1 for n in sg.nodos if n.tipo == "personaje")
    print(f"   {encontrados}/{total_elem} modelos 3D encontrados ({n_personajes} del catálogo)")

    out_dir = Path(state["out_dir"])
    eid = sg.id_escena
    _guardar(sg, out_dir / f"scene_graph_{eid}.json")

    # Acumular scene_graphs y registro_personajes para escenas futuras
    sg_previos_nuevo       = {**sg_previos, eid: sg}
    registro_nuevo         = {**registro_previo, **sg.registro_personajes}

    return {
        "scene_graph":           sg,
        "scene_graphs_previos":  sg_previos_nuevo,
        "registro_personajes":   registro_nuevo,
        "errores_constructor":   [],
    }


def nodo_programador(state: WorldWeaverState) -> dict:
    print("\n--- [4/5] Programador ---")
    provider = state.get("provider", "mercury")
    escena = _escena_activa(state)
    mensajes = state.get("mensajes_programador") or []

    errores_prev = state.get("errores_programador", [])
    if errores_prev and mensajes:
        mensajes = mensajes + [_feedback_error(errores_prev)]
        n = state.get("reintentos", {}).get("programador", 0)
        print(f"   [Reintento {n}/{MAX_RETRIES}] Errores previos:")
        for e in errores_prev:
            print(f"     ✗ {e}")

    try:
        salida, mensajes_nuevos = ejecutar_programador(
            state["scene_graph"],
            escena,
            provider=provider,
            mensajes_previos=mensajes or None,
            errores_previos=errores_prev or None,
            modo=state.get("modo", "narrativo"),
            idioma=state.get("idioma", "es"),
            tipo_vocabulario=state.get("tipo_vocabulario"),
            idioma_objetivo=state.get("idioma_objetivo"),
            vocabulario=getattr(state.get("salida_organizador"), "vocabulario", None),
        )
        print(f"   {len(salida.fases)} fases, "
              f"{len(salida.personajes)} personajes, "
              f"{len(salida.objetos)} objetos, "
              f"{len(salida.zonas_narrativas)} zonas narrativas")
        return {
            "salida_programador": salida,
            "mensajes_programador": mensajes_nuevos,
            "errores_programador": [],
        }
    except AgentError as e:
        logger.warning(f"[Programador] Error: {e}")
        return {
            "mensajes_programador": e.messages,  # incluye la respuesta fallida del LLM
            "errores_programador": [str(e)],
        }
    except Exception as e:
        logger.warning(f"[Programador] Error irrecuperable: {e}")
        return {
            "mensajes_programador": mensajes,
            "errores_programador": [str(e)],
        }


def nodo_musico(state: WorldWeaverState) -> dict:
    print("\n--- [5/5] Músico ---")
    eid = state["scene_graph"].id_escena
    escena = state["salida_organizador"].escenas[state["escena_activa"]]
    provider = state.get("provider", "mercury")

    salida = ejecutar_musico(eid, atmosfera=escena.atmosfera, entorno=escena.entorno,
                             modo="auto", provider=provider, tipo_ambiente=escena.tipo_ambiente)
    print(f"   '{salida.pista_principal.titulo}' ({salida.fuente})")

    out_dir = Path(state["out_dir"])
    _guardar(salida, out_dir / f"salida_musico_{eid}.json")

    return {"salida_musico": salida}


def nodo_ensamblador(state: WorldWeaverState) -> dict:
    print("\n--- Ensamblador ---")
    eid = state["scene_graph"].id_escena
    out_dir = Path(state["out_dir"])
    modo = state.get("modo", "narrativo")

    idx = state.get("escena_activa", 0)
    escenas = state["salida_organizador"].escenas
    # Con escena_filtro solo se genera esta escena, pero su portal y su cierre deben ser
    # los de su posición real en la historia (si no, al regenerar la última perdía el fin).
    es_ultima = idx + 1 >= len(escenas)

    # URL del portal: siguiente escena, quiz (educativo final) o ninguno
    next_scene_url = None
    portal_label = None
    if idx + 1 < len(escenas):
        next_eid = escenas[idx + 1].id
        next_scene_url = f"preview_{next_eid}.html"
    elif es_ultima and modo == "educativo":
        next_scene_url = "quiz.html"
        portal_label = "final quiz" if state.get("idioma") == "en" else "cuestionario final"

    # Datos de fin: última escena con texto_fin (narrativo → botón "volver al inicio";
    # educativo → mismo overlay, botón "ir al cuestionario", lo decide el viewer por la URL).
    escena_obj = _escena_activa(state)
    texto_fin  = None
    escenas_cielo = None
    if es_ultima and escena_obj and escena_obj.texto_fin:
        texto_fin = escena_obj.texto_fin
        sg_previos  = state.get("scene_graphs_previos", {})
        titulo_por_id = {e.id: e.titulo for e in escenas}
        escenas_cielo = []
        for esc_id, sg in sg_previos.items():
            escenas_cielo.append({
                "titulo":          titulo_por_id.get(esc_id, esc_id),
                "color_fondo":     sg.cielo.color_fondo,
                "color_sol":       sg.cielo.color_sol,
                "color_ambiente":  sg.cielo.color_ambiente,
            })
        sg_actual = state["scene_graph"]
        escenas_cielo.append({
            "titulo":         escena_obj.titulo,
            "color_fondo":    sg_actual.cielo.color_fondo,
            "color_sol":      sg_actual.cielo.color_sol,
            "color_ambiente": sg_actual.cielo.color_ambiente,
        })

    html_path = out_dir / f"preview_{eid}.html"
    ensamblar(
        state["scene_graph"],
        manifest=state.get("salida_programador"),
        musico=state.get("salida_musico"),
        escena=escena_obj,
        next_scene_url=next_scene_url,
        portal_label=portal_label,
        texto_fin=texto_fin,
        escenas_cielo=escenas_cielo,
        output_path=html_path,
        idioma=state.get("idioma", "es"),
        modo=state.get("modo", "narrativo"),
    )
    print(f"   [HTML] preview_{eid}.html")
    return {}


# ─── Nodos validadores ────────────────────────────────────────────────────────

def nodo_validar_organizador(state: WorldWeaverState) -> dict:
    # Si ya hubo error de parseo en el agente, lo propagamos directamente
    if state.get("errores_organizador"):
        return {}

    errores = validar_organizador(state["salida_organizador"], modo=state.get("modo", "narrativo"))
    if errores:
        print("   [Validador Organizador] Errores:")
        for e in errores:
            print(f"     ✗ {e}")
        return {"errores_organizador": errores}

    print("   [Validador Organizador] OK")
    out_dir = Path(state["out_dir"])
    _guardar(state["salida_organizador"], out_dir / "salida_organizador.json")

    # Guardar el texto fuente nombrado con el título de la historia (ya conocido tras
    # el Organizador). Antes se guardaba como 'fuente.txt'/'texto_original.txt' genérico.
    titulo = state["salida_organizador"].titulo_historia
    fuente_path = out_dir / f"{_slug(titulo, state['nombre_mundo'])}.txt"
    fuente_path.write_text(state.get("texto_original", "") or "", encoding="utf-8")
    print(f"   [OK] {fuente_path.name} (texto fuente)")

    result: dict = {"errores_organizador": []}
    filtro = state.get("escena_filtro")
    if filtro:
        ids = [e.id for e in state["salida_organizador"].escenas]
        if filtro not in ids:
            raise RuntimeError(
                f"Escena '{filtro}' no encontrada. "
                f"Disponibles: {ids}"
            )
        idx = ids.index(filtro)
        result["escena_activa"] = idx
        print(f"   [Filtro] Solo se procesará: {filtro} (índice {idx})")

    return result


def nodo_validar_director(state: WorldWeaverState) -> dict:
    if state.get("errores_director"):
        return {}

    escena = _escena_activa(state)
    errores = validar_director(state["salida_director"], escena)

    if errores:
        print("   [Validador Director] Errores:")
        for e in errores:
            print(f"     ✗ {e}")
    else:
        print("   [Validador Director] OK")

    if not errores:
        out_dir = Path(state["out_dir"])
        eid = escena.id
        _guardar(state["salida_director"], out_dir / f"salida_director_{eid}.json")

    return {"errores_director": errores}


def nodo_validar_constructor(state: WorldWeaverState) -> dict:
    errores = validar_constructor(state["scene_graph"])
    if errores:
        print("   [Validador Constructor] Errores:")
        for e in errores:
            print(f"     ✗ {e}")
    else:
        print("   [Validador Constructor] OK")
    return {"errores_constructor": errores}


def nodo_validar_programador(state: WorldWeaverState) -> dict:
    if state.get("errores_programador"):
        return {}

    errores = validar_programador(state["salida_programador"], state["scene_graph"], _escena_activa(state))
    if errores:
        print("   [Validador Programador] Errores:")
        for e in errores:
            print(f"     ✗ {e}")
    else:
        print("   [Validador Programador] OK")

    if not errores:
        out_dir = Path(state["out_dir"])
        eid = state["scene_graph"].id_escena
        _guardar(state["salida_programador"], out_dir / f"salida_programador_{eid}.json")

    return {"errores_programador": errores}


# ─── Aristas condicionales ────────────────────────────────────────────────────

def _route_organizador(state: WorldWeaverState) -> str:
    if not state.get("errores_organizador"):
        return "director"
    n = state.get("reintentos", {}).get("organizador", 0)
    if n < MAX_RETRIES:
        return "organizador_retry"
    raise RuntimeError(
        f"[Organizador] Falló tras {MAX_RETRIES} reintentos. "
        f"Último error: {state['errores_organizador']}"
    )


def _route_director(state: WorldWeaverState) -> str:
    if not state.get("errores_director"):
        return "constructor"
    n = state.get("reintentos", {}).get("director", 0)
    if n < MAX_RETRIES:
        return "director_retry"
    raise RuntimeError(
        f"[Director] Falló tras {MAX_RETRIES} reintentos. "
        f"Último error: {state['errores_director']}"
    )


def _route_constructor(state: WorldWeaverState) -> str:
    if not state.get("errores_constructor"):
        return "programador"
    # Constructor es determinístico — si falla es un bug, no un error del LLM
    raise RuntimeError(
        f"[Constructor] Error inesperado: {state['errores_constructor']}"
    )


def _route_programador(state: WorldWeaverState) -> str:
    if not state.get("errores_programador"):
        return "musico"
    n = state.get("reintentos", {}).get("programador", 0)
    if n < MAX_RETRIES:
        return "programador_retry"
    raise RuntimeError(
        f"[Programador] Falló tras {MAX_RETRIES} reintentos. "
        f"Último error: {state['errores_programador']}"
    )


def _route_ensamblador(state: WorldWeaverState) -> str:
    """Después de ensamblar: siguiente escena, examinador (educativo) o fin."""
    if state.get("escena_filtro"):
        return END
    escenas = state["salida_organizador"].escenas
    idx_actual = state.get("escena_activa", 0)
    if idx_actual + 1 < len(escenas):
        return "siguiente_escena"
    if state.get("modo") == "educativo":
        return "examinador"
    return END


# ─── Nodo de transición entre escenas ────────────────────────────────────────

def nodo_siguiente_escena(state: WorldWeaverState) -> dict:
    """Avanza al índice de la siguiente escena y resetea el estado por-escena."""
    idx_nuevo = state.get("escena_activa", 0) + 1
    escena_nueva = state["salida_organizador"].escenas[idx_nuevo]
    print(f"\n{'='*55}")
    print(f"  Escena siguiente: {escena_nueva.id} — {escena_nueva.titulo}")
    print(f"{'='*55}")
    return {
        "escena_activa": idx_nuevo,
        # Resetear outputs por-escena
        "salida_director": None,
        "scene_graph": None,
        "salida_programador": None,
        "salida_musico": None,
        # Resetear historial de mensajes por agente
        "mensajes_director": [],
        "mensajes_programador": [],
        # Resetear errores y reintentos de agentes por-escena
        "errores_director": [],
        "errores_constructor": [],
        "errores_programador": [],
        "reintentos": {
            **state.get("reintentos", {}),
            "director": 0,
            "programador": 0,
        },
    }


def nodo_examinador(state: WorldWeaverState) -> dict:
    """Genera el cuestionario final tipo test (solo modo educativo)."""
    print("\n--- [7] Examinador ---")
    provider = state.get("provider", "mercury")
    out_dir = Path(state["out_dir"])

    try:
        salida = ejecutar_examinador(
            state["salida_organizador"],
            state["texto_original"],
            state.get("nombre_mundo", ""),
            provider=provider,
            idioma=state.get("idioma", "es"),
            subtipo=state.get("subtipo_educativo"),
            idioma_objetivo=state.get("idioma_objetivo"),
        )
        print(f"   {len(salida.preguntas)} preguntas generadas")
        _guardar(salida, out_dir / "salida_examinador.json")
        generar_quiz_html(salida, out_dir / "quiz.html", idioma=state.get("idioma", "es"))
        print(f"   [HTML] quiz.html")
        return {"salida_examinador": salida}
    except Exception as e:
        logger.warning(f"[Examinador] Error (no bloquea el pipeline): {e}")
        return {}


# ─── Nodos de reintento (incrementan contador antes de volver al agente) ──────

def nodo_organizador_retry(state: WorldWeaverState) -> dict:
    return {"reintentos": _incrementar_reintento(state, "organizador")}


def nodo_director_retry(state: WorldWeaverState) -> dict:
    return {"reintentos": _incrementar_reintento(state, "director")}


def nodo_programador_retry(state: WorldWeaverState) -> dict:
    return {"reintentos": _incrementar_reintento(state, "programador")}


# ─── Construcción del grafo ───────────────────────────────────────────────────

def compilar_grafo() -> StateGraph:
    workflow = StateGraph(WorldWeaverState)

    # Nodos principales
    workflow.add_node("organizador",          nodo_organizador)
    workflow.add_node("validar_organizador",  nodo_validar_organizador)
    workflow.add_node("director",             nodo_director)
    workflow.add_node("validar_director",     nodo_validar_director)
    workflow.add_node("constructor",          nodo_constructor)
    workflow.add_node("validar_constructor",  nodo_validar_constructor)
    workflow.add_node("programador",          nodo_programador)
    workflow.add_node("validar_programador",  nodo_validar_programador)
    workflow.add_node("musico",               nodo_musico)
    workflow.add_node("ensamblador",          nodo_ensamblador)
    workflow.add_node("siguiente_escena",     nodo_siguiente_escena)

    # Nodos de reintento (solo incrementan contador, luego vuelven al agente)
    workflow.add_node("organizador_retry",    nodo_organizador_retry)
    workflow.add_node("director_retry",       nodo_director_retry)
    workflow.add_node("programador_retry",    nodo_programador_retry)

    # Examinador: cuestionario final en modo educativo
    workflow.add_node("examinador",           nodo_examinador)

    # Punto de entrada
    workflow.set_entry_point("organizador")

    # Aristas lineales
    workflow.add_edge("organizador",         "validar_organizador")
    workflow.add_edge("director",            "validar_director")
    workflow.add_edge("constructor",         "validar_constructor")
    workflow.add_edge("programador",         "validar_programador")
    workflow.add_edge("musico",              "ensamblador")
    workflow.add_edge("siguiente_escena",    "director")

    # Aristas de reintento → vuelven al agente
    workflow.add_edge("organizador_retry",   "organizador")
    workflow.add_edge("director_retry",      "director")
    workflow.add_edge("programador_retry",   "programador")

    # Aristas condicionales
    workflow.add_conditional_edges(
        "validar_organizador",
        _route_organizador,
        {"director": "director", "organizador_retry": "organizador_retry"},
    )
    workflow.add_conditional_edges(
        "validar_director",
        _route_director,
        {"constructor": "constructor", "director_retry": "director_retry"},
    )
    workflow.add_conditional_edges(
        "validar_constructor",
        _route_constructor,
        {"programador": "programador"},
    )
    workflow.add_conditional_edges(
        "validar_programador",
        _route_programador,
        {"musico": "musico", "programador_retry": "programador_retry"},
    )
    workflow.add_conditional_edges(
        "ensamblador",
        _route_ensamblador,
        {"siguiente_escena": "siguiente_escena", "examinador": "examinador", END: END},
    )
    workflow.add_edge("examinador", END)

    return workflow.compile()


# ─── Punto de entrada público ─────────────────────────────────────────────────

def estado_inicial(
    texto: str,
    nombre_mundo: str,
    out_dir: Path,
    provider: str = "mercury",
    modo: str = "narrativo",
    idioma: str = "es",
    escena_filtro: str | None = None,
) -> WorldWeaverState:
    """Estado inicial del grafo. Fuente única para ejecutar_pipeline, el servidor y la
    reanudación (antes cada uno construía el suyo y divergían)."""
    return {
        "nombre_mundo":         nombre_mundo,
        "provider":             provider,
        "modo":                 modo,
        "idioma":               idioma,
        "out_dir":              str(out_dir),
        "max_retries":          MAX_RETRIES,
        "texto_original":       texto,
        "escena_activa":        0,
        "escena_filtro":        escena_filtro,
        "scene_graphs_previos": {},
        "registro_personajes":  {},
        "salida_organizador":   None,
        "salida_director":      None,
        "scene_graph":          None,
        "salida_programador":   None,
        "salida_musico":        None,
        "salida_examinador":    None,
        "mensajes_organizador": [],
        "mensajes_director":    [],
        "mensajes_programador": [],
        "errores_organizador":  [],
        "errores_director":     [],
        "errores_constructor":  [],
        "errores_programador":  [],
        "reintentos":           {},
    }


def estado_desde_disco(
    out_dir: Path,
    escena: str | None = None,
    desde: str | None = None,
    provider: str = "mercury",
    modo: str | None = None,
    idioma: str | None = None,
) -> WorldWeaverState:
    """Estado para continuar un mundo ya empezado sin repetir el Organizador.

    - escena=None → reanuda en la primera escena sin preview_*.html y sigue hasta el final.
    - escena="escena_03" → regenera solo esa escena (con su portal y cierre correctos).
      Ojo: si en ella se establece el aspecto de un personaje recurrente, las escenas
      posteriores conservan el aspecto antiguo; para eso usa `desde`.
    - desde="escena_03" → regenera desde esa escena hasta el final.
    Carga la salida del Organizador y los SceneGraph ya generados (consistencia de
    personajes, modelos y tamaños entre escenas). Modo e idioma se leen de la marca
    de mundo incompleto o del preview existente si no se indican.
    """
    from schemas.escenas import SalidaOrganizador
    from schemas.scene_graph import SceneGraph

    org = SalidaOrganizador.model_validate_json(
        (out_dir / "salida_organizador.json").read_text(encoding="utf-8"))
    ids = [e.id for e in org.escenas]

    marca = out_dir / "_incompleto.json"
    meta = json.loads(marca.read_text(encoding="utf-8")) if marca.exists() else {}
    if idioma is None or modo is None:
        for prev in sorted(out_dir.glob("preview_escena_*.html")):
            m = re.search(r'const IDIOMA = "(\w+)"; const MODO = "(\w+)"',
                          prev.read_text(encoding="utf-8"))
            if m:
                meta.setdefault("idioma", m.group(1)); meta.setdefault("modo", m.group(2))
                break
    idioma = idioma or meta.get("idioma", "es")
    modo = modo or meta.get("modo", "narrativo")

    objetivo = escena or desde
    if objetivo:
        if objetivo not in ids:
            raise ValueError(f"Escena '{objetivo}' no existe. Disponibles: {ids}")
        idx = ids.index(objetivo)
    else:
        pendientes = [i for i, eid in enumerate(ids)
                      if not (out_dir / f"preview_{eid}.html").exists()]
        if not pendientes:
            raise ValueError("Todas las escenas ya tienen preview: no hay nada que reanudar.")
        idx = pendientes[0]

    sg_previos, registro = {}, {}
    for i, eid in enumerate(ids):
        f = out_dir / f"scene_graph_{eid}.json"
        # Solo escena suelta: se cargan todas las demás (el cierre usa sus cielos).
        # Reanudar / desde: solo las anteriores (las siguientes se regeneran).
        if i == idx or (not escena and i > idx) or not f.exists():
            continue
        sg = SceneGraph.model_validate_json(f.read_text(encoding="utf-8"))
        sg_previos[eid] = sg
        registro.update(sg.registro_personajes)

    fuente = out_dir / f"{_slug(org.titulo_historia, out_dir.name)}.txt"
    texto = fuente.read_text(encoding="utf-8") if fuente.exists() else ""

    estado = estado_inicial(texto, out_dir.name, out_dir, provider=provider, modo=modo,
                            idioma=idioma, escena_filtro=escena)
    estado.update({
        "salida_organizador":   org,
        "escena_activa":        idx,
        "scene_graphs_previos": sg_previos,
        "registro_personajes":  registro,
        "subtipo_educativo":    org.subtipo_educativo,
        "tipo_vocabulario":     org.tipo_vocabulario,
        "idioma_objetivo":      org.idioma_objetivo,
    })
    print(f"   Reanudando '{out_dir.name}' en {ids[idx]} ({idx + 1}/{len(ids)})"
          f"{' — solo esta escena' if escena else ''} · modo={modo} idioma={idioma}")
    return estado


def ejecutar_pipeline(
    texto: str,
    nombre_mundo: str,
    provider: str = "mercury",
    escena_filtro: str | None = None,
    modo: str = "narrativo",
    idioma: str = "es",
) -> WorldWeaverState:
    """
    Ejecuta el pipeline completo WorldWeaver para el texto dado.

    Args:
        texto: Texto narrativo de entrada.
        nombre_mundo: Nombre del mundo (subcarpeta en outputs/).
        provider: "mercury" | "ollama"
        escena_filtro: Si se indica, solo procesa esa escena (ej: "escena_01").

    Returns:
        Estado final del pipeline (WorldWeaverState).
    """
    from runtime_paths import dato

    OUTPUTS_BASE = dato("outputs")
    out_dir = OUTPUTS_BASE / nombre_mundo
    out_dir.mkdir(parents=True, exist_ok=True)

    # El texto fuente se guarda nombrado con el título de la historia en
    # nodo_validar_organizador (cuando ya se conoce el título).

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    print(f"\n=== WorldWeaver: '{nombre_mundo}' ===")
    print(f"    Salida: {out_dir}\n")

    grafo = compilar_grafo()

    estado = estado_inicial(texto, nombre_mundo, out_dir, provider=provider, modo=modo,
                            idioma=idioma, escena_filtro=escena_filtro)

    estado_final = grafo.invoke(estado)

    escenas = estado_final["salida_organizador"].escenas
    if escena_filtro:
        procesadas = [e.id for e in escenas if e.id == escena_filtro]
    else:
        procesadas = [e.id for e in escenas]
    print(f"\n{'='*55}")
    print(f"  Pipeline completado. Escenas procesadas: {procesadas}")
    print(f"  HTMLs en: {out_dir}")
    print(f"{'='*55}\n")

    return estado_final
