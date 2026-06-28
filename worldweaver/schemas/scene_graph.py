"""
Schema de salida del Agente 3 (Constructor).

Modelo de escenario cilíndrico inmersivo:
  - Eje X: izquierda (-7) → derecha (+7)
  - Eje Y: suelo (0) → techo (+8)
  - Eje Z: frontal (-6) ↔ trasero (+6)  [cámara en z=0, mira hacia z negativo]

Tipos de nodo:
  - "fondo":    cilindro panorámico — textura 2D, cargada por el Dibujante
  - "suelo":    círculo horizontal  — textura 2D, cargada por el Dibujante
  - "personaje" / "objeto" / "decorado": modelos 3D cargados desde poly.pizza
    · gltf_url:          URL del modelo glTF (si se encontró en poly.pizza)
    · keyword_busqueda:  keyword usada para la búsqueda (para trazabilidad)
    · prompt_imagen:     None (no se usa para estos tipos)

Si gltf_url es None (poly.pizza no encontró modelo), el sandbox usa un billboard
de color como fallback para no romper el pipeline.
"""
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Literal, Optional

from schemas.personaje import SkinPersonaje


class CieloConfig(BaseModel):
    tipo:                 str    # "dia_soleado" | "dia_nublado" | "atardecer" | "noche" | "lluvia" | "interior_calido" | "interior_frio"
    color_fondo:          str    # hex, p.ej. "#87ceeb"
    color_ambiente:       str
    intensidad_ambiente:  float
    color_sol:            str
    intensidad_sol:       float
    pos_sol:              Dict[str, float]          # {"x": 1, "y": 3, "z": -1}
    niebla:               Optional[Dict[str, Any]] = None  # {"color": "#...", "near": 8, "far": 20}
    # Solo interiores: qué luz entra por las ventanas — "dia" | "tarde" | "noche".
    # La infiere el Constructor de la atmósfera/entorno de la escena (fiel a la hora que
    # cuenta la historia); el viewer la usa para teñir el cristal y el haz de luz.
    luz_exterior:         Optional[str] = None


class Vector3(BaseModel):
    x: float = Field(..., ge=-25.0, le=25.0)
    y: float = Field(..., ge=0.0,   le=20.0)
    z: float = Field(..., ge=-25.0, le=25.0)


class NodoEscena(BaseModel):
    id:     str
    nombre: str
    tipo:   Literal["personaje", "objeto", "decorado", "fondo", "suelo", "ambiente"]
    origen: Optional[Literal["narrativo", "añadido"]] = None  # None para fondo/suelo
    posicion: Vector3
    ancho:  float = Field(..., ge=0.1, le=50.0)
    alto:   float = Field(..., ge=0.1, le=50.0)
    # Dimensión real MAYOR del objeto (la fija el pase de coherencia del Constructor).
    # Si está presente, el viewer escala invariante a la orientación: lleva el eje más
    # largo del modelo a este valor, preservando proporciones (un palo mide igual tumbado
    # o de pie). Si es None, el viewer usa el encaje clásico en la caja ancho×alto.
    tam_real: Optional[float] = None
    voltear_horizontal: bool = False
    capa:   int = Field(..., ge=0, le=12)
    # Fondo y suelo: prompt para generación de textura 2D
    prompt_imagen: Optional[str] = None
    # Personaje, objeto, decorado: modelo 3D de poly.pizza
    gltf_url: Optional[str] = None
    keyword_busqueda: Optional[str] = None


class SceneGraph(BaseModel):
    id_escena:    str
    tipo_escena:  Literal["interior", "exterior"] = "exterior"
    tipo_ambiente: Optional[str] = None  # para uso del JS en generación procedural
    radio_escena: float = Field(7.0, description="Radio del cilindro de fondo en unidades 3D")
    limite_jugador: float = Field(6.5, description="Radio máximo al que puede llegar el jugador")
    color_suelo:  Optional[str] = None  # hex color override para superficie_planeta (ej: "#c1440e")
    tipo_suelo:   Optional[str] = None  # superficie procedural especial del suelo (nubes|agua|lava|cristal); solo 'otro'
    tipo_techo:   Optional[str] = None  # nubes bajas que ocultan lo alto (ej: "nubes_bajas"); solo 'otro'
    radio_cubierta: Optional[float] = None  # solo barco: radio de la cubierta (el viewer eleva a cubierta dentro de él)
    variante_barco: Optional[str] = None    # solo barco: balsa|barco|galeon (el viewer usa la misma variante)
    escena_conversacion: bool = False       # idiomas conversacional: los personajes se miran entre sí (conversan)
    nodos:        List[NodoEscena]
    cielo:        CieloConfig = Field(
        default_factory=lambda: CieloConfig(
            tipo="dia_soleado",
            color_fondo="#87ceeb",
            color_ambiente="#ffffff",
            intensidad_ambiente=0.6,
            color_sol="#fff5e0",
            intensidad_sol=1.8,
            pos_sol={"x": 1.0, "y": 3.0, "z": -1.0},
            niebla=None,
        )
    )
    camara: dict = Field(
        default={
            "posicion":  {"x": 0, "y": 1.8, "z": 0},
            "mirar_a":   {"x": 0, "y": 1.8, "z": -3},
            "fov": 55
        }
    )
    # Apariencias de personajes del catálogo Quaternius.
    # Clave: id del NodoEscena (= id del personaje del Organizador).
    # Valor: SkinPersonaje con GLB, skin/pelo/variante.
    # scene_loader.js lo lee para aplicar los colores al cargar el GLB.
    registro_personajes: Dict[str, SkinPersonaje] = Field(default_factory=dict)