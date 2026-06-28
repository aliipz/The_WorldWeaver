"""
Schema de salida del Agente 2 (Director).

El Director produce dos cosas:
  - posicionamiento: posición + tamaño de cada narrativo del Organizador
  - decorados: objetos ambientales inventados por el Director (nombre, descripcion, posición, tamaño)

El resto de campos de los narrativos (nombre, tipo, descripcion, skin_id) los rellena Python
copiándolos del Organizador — el LLM no los genera.

El fondo y el suelo los genera el Constructor automáticamente a partir de cielo y tipo_ambiente,
que lee directamente del Organizador vía el estado.
"""
from pydantic import BaseModel, Field
from typing import List, Literal, Optional


class PosicionGrid(BaseModel):
    columna: int = Field(..., ge=0, le=8, description="0=izquierda extremo; máximo varía por fila (N_COLS_POR_FILA)")
    fila: int = Field(..., ge=0, le=6, description="0=horizonte/pared, 6=primer plano")


class ElementoEscena(BaseModel):
    id:     str
    nombre: str
    tipo:   Literal["personaje", "objeto", "decorado"]
    origen: Literal["narrativo", "añadido"]
    skin_id: Optional[str] = Field(default=None)
    posicion_grid: PosicionGrid
    ancho: float = Field(..., ge=0.2, le=6.0,  description="Ancho en unidades 3D (1.0 ≈ anchura de persona adulta)")
    alto:  float = Field(..., ge=0.2, le=10.0, description="Alto en unidades 3D (1.0 ≈ altura de persona adulta)")
    descripcion: str
    # Keyword de búsqueda en poly.pizza fijada explícitamente (p.ej. mobiliario del filler
    # determinista: "dining set", "bookshelf"...). Si es None, el Constructor la deriva con
    # el LLM desde nombre/descripción.
    keyword_busqueda: Optional[str] = Field(default=None)


class SalidaDirector(BaseModel):
    id_escena: str
    elementos: List[ElementoEscena] = Field(
        ...,
        description="Personajes, objetos y decorados. El fondo y suelo NO van aquí."
    )
