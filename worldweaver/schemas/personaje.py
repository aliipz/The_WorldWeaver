"""
Schema de apariencia visual de un personaje del catálogo Quaternius.

Generado por el Constructor cuando procesa un nodo de tipo "personaje".
Se persiste en WorldWeaverState.registro_personajes y se serializa
dentro de SceneGraph.registro_personajes para que scene_loader.js
pueda aplicar skin/pelo/variante al cargar el GLB.
"""
from pydantic import BaseModel, Field
from typing import Optional


class SkinPersonaje(BaseModel):
    # ── Modelo 3D ───────────────────────────────────────────────────────────
    glb_id:   str   # clave en CATALOGO, e.g. "Wizard"
    glb_path: str   # ruta servida, e.g. "/sandbox/assets/characters/Wizard.gltf"

    # ── Tono de piel ────────────────────────────────────────────────────────
    # Para personajes humanos/élfico: uno de SKIN_TONES ("muy_claro", "medio"...)
    # Para monstruos/animales: None (se usa skin_hex directamente)
    skin_tone: Optional[str] = None
    # Hex real que se pasa al visor (ya sea del preset o del skin_defecto del catálogo)
    skin_hex:  str = "#D4956A"

    # ── Color de pelo ────────────────────────────────────────────────────────
    # None si el personaje no tiene material Hair (calvo, casco, etc.)
    hair_color: Optional[str] = None  # clave de HAIR_COLORS, e.g. "rubio"

    # ── Variación de ropa ────────────────────────────────────────────────────
    # Seed determinista 1-9999; distinto en cada instancia para que dos personajes
    # con el mismo GLB tengan ropa ligeramente diferente.
    clothing_seed: int = Field(default=1, ge=1, le=9999)

    # ── Talla ────────────────────────────────────────────────────────────────
    # Define la altura real en unidades 3D, anulando el valor del Director.
    # Opciones: "adulto_alto" | "adulto_medio" | "adulto_bajo" | "nino_enano"
    talla: str = "adulto_medio"

    # ── Animaciones ─────────────────────────────────────────────────────────
    animacion_idle: str = "Idle"
    animacion_talk: str = "Victory"   # se sobreescribe con "Idle" si Victory no existe
