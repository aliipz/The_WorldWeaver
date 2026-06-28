"""
Estado compartido del pipeline LangGraph.

Cada nodo agente escribe su salida en el campo correspondiente.
Cada nodo validador escribe los errores en el campo errores_<agente>.
Las aristas condicionales leen esos errores para decidir si reintentar o avanzar.
"""
from __future__ import annotations
from typing import Optional, TypedDict

from schemas.escenas import SalidaOrganizador
from schemas.especificacion import SalidaDirector
from schemas.scene_graph import SceneGraph
from schemas.assets import SalidaDibujante
from schemas.interacciones import SalidaProgramador
from schemas.audio import SalidaMusico
from schemas.quiz import SalidaExaminador


class WorldWeaverState(TypedDict, total=False):

    # ── Configuración del pipeline ────────────────────────────────────────────
    nombre_mundo: str
    provider: str           # "mercury" | "ollama"
    modo: str               # "narrativo" | "educativo"
    idioma: str             # "es" | "en" — idioma de GENERACIÓN del mundo (UI/andamiaje)
    # ── Clasificación educativa (rellenada por el Organizador) ────────────────
    subtipo_educativo: Optional[str]   # "historico" | "taxonomico" | "vocabulario"
    tipo_vocabulario: Optional[str]    # "tangible" | "conversacional" (solo subtipo vocabulario)
    idioma_objetivo: Optional[str]     # idioma que se aprende (solo vocabulario), p.ej. "en"
    modo_dibujante: str     # "mock" | "fal" | "gemini" | "auto"
    out_dir: str            # ruta absoluta a outputs/<nombre_mundo>/
    max_retries: int

    # ── Input ─────────────────────────────────────────────────────────────────
    texto_original: str
    escena_activa: int                   # índice de la escena que se procesa ahora
    escena_filtro: Optional[str]         # si se indica, solo procesa esa escena
    scene_graphs_previos: dict           # {id_escena: SceneGraph} para reutilizar skin_id
    registro_personajes: dict            # {personaje_id: SkinPersonaje} acumulado entre escenas

    # ── Outputs (se resetean entre escenas excepto salida_organizador) ────────
    salida_organizador: Optional[SalidaOrganizador]
    salida_director: Optional[SalidaDirector]
    scene_graph: Optional[SceneGraph]
    salida_dibujante: Optional[SalidaDibujante]
    salida_programador: Optional[SalidaProgramador]
    salida_musico: Optional[SalidaMusico]
    salida_examinador: Optional[SalidaExaminador]

    # ── Historial de conversación por agente LLM (para feedback de error) ─────
    # Cada lista es la secuencia de mensajes acumulada incluidos los de error.
    # Se preserva entre reintentos para que el LLM reciba contexto del fallo.
    mensajes_organizador: list
    mensajes_director: list
    mensajes_programador: list

    # ── Errores del último intento (vacío = éxito) ────────────────────────────
    errores_organizador: list[str]
    errores_director: list[str]
    errores_constructor: list[str]
    errores_programador: list[str]

    # ── Contadores de reintentos por agente ───────────────────────────────────
    # {"organizador": 0, "director": 2, "programador": 1}
    reintentos: dict[str, int]
