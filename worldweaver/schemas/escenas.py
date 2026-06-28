"""
Schema de salida del Agente 1 (Organizador).
Representa el texto dividido en escenas estructuradas.
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Literal, Optional

# ── Alias EN → ES para valores de catálogo ────────────────────────────────────
# El LLM en modo EN puede escribir "beach", "forest", etc.
# field_validator normaliza antes de que Pydantic valide el Literal.

_CIELO_ALIAS: dict[str, str] = {
    "sunrise":            "amanecer",
    "dawn":               "amanecer",
    "clear_morning":      "manana_despejada",
    "clear morning":      "manana_despejada",
    "sunny_morning":      "manana_despejada",
    "cloudy_morning":     "manana_nublada",
    "cloudy morning":     "manana_nublada",
    "overcast_morning":   "manana_nublada",
    "noon":               "mediodia_soleado",
    "midday":             "mediodia_soleado",
    "sunny_noon":         "mediodia_soleado",
    "sunny noon":         "mediodia_soleado",
    "midday_sunny":       "mediodia_soleado",
    "sunset":             "atardecer",
    "dusk":               "atardecer",
    "starry_night":       "noche_estrellada",
    "starry night":       "noche_estrellada",
    "clear_night":        "noche_estrellada",
    "dark_night":         "noche_cerrada",
    "dark night":         "noche_cerrada",
    "moonless_night":     "noche_cerrada",
    "moonless night":     "noche_cerrada",
    "storm":              "tormenta",
    "thunderstorm":       "tormenta",
    "thunder":            "tormenta",
    "light_rain":         "lluvia_suave",
    "gentle_rain":        "lluvia_suave",
    "drizzle":            "lluvia_suave",
    "rain":               "lluvia_suave",
    "dense_fog":          "niebla_densa",
    "thick_fog":          "niebla_densa",
    "fog":                "niebla_densa",
    "mist":               "niebla_densa",
    "snowy_day":          "dia_nevado",
    "snowy day":          "dia_nevado",
    "snow":               "dia_nevado",
    "snowfall":           "dia_nevado",
    "magic_sky":          "cielo_magico",
    "magical_sky":        "cielo_magico",
    "fantasy_sky":        "cielo_magico",
    "magical":            "cielo_magico",
    "warm_interior":      "interior_calido",
    "warm interior":      "interior_calido",
    "cozy_interior":      "interior_calido",
    "cold_interior":      "interior_frio",
    "cold interior":      "interior_frio",
    "bright_interior":    "interior_luminoso",
    "bright interior":    "interior_luminoso",
    "luminous_interior":  "interior_luminoso",
}

_AMBIENTE_ALIAS: dict[str, str] = {
    "city":               "ciudad",
    "urban":              "ciudad",
    "town":               "pueblo",
    "village":            "pueblo",
    "medieval_town":      "pueblo",
    "countryside":        "campo",
    "rural":              "campo",
    "farmland":           "campo",
    "farm":               "campo",
    "nature":             "naturaleza",
    "forest":             "bosque",
    "woodland":           "bosque",
    "woods":              "bosque",
    "jungle":             "selva",
    "rainforest":         "selva",
    "tropical_forest":    "selva",
    "savanna":            "sabana",
    "savannah":           "sabana",
    "meadow":             "pradera",
    "grassland":          "pradera",
    "prairie":            "pradera",
    "desert":             "desierto",
    "beach":              "playa",
    "coast":              "playa",
    "shore":              "playa",
    "coastal":            "playa",
    "mountain":           "montaña",
    "mountains":          "montaña",
    "montagna":           "montaña",
    "cave":               "cueva",
    "cavern":             "cueva",
    "underground":        "cueva",
    "ruins":              "ruinas",
    "ancient_ruins":      "ruinas",
    "space":              "espacio",
    "outer_space":        "espacio",
    "cosmos":             "espacio",
    "planet_surface":     "superficie_planeta",
    "planetary_surface":  "superficie_planeta",
    "surface_planet":     "superficie_planeta",
    "moon_surface":       "superficie_planeta",
    "underwater":         "bajo_el_agua",
    "under_water":        "bajo_el_agua",
    "seabed":             "bajo_el_agua",
    "ocean_floor":        "bajo_el_agua",
    "on_water":           "sobre_agua",
    "on water":           "sobre_agua",
    "water_surface":      "sobre_agua",
    "boat":               "barco",
    "ship":               "barco",
    "aboard_ship":        "barco",
    "large_interior":     "interior_grande",
    "grand_interior":     "interior_grande",
    "cuarto":             "habitacion",
    "dormitorio":         "habitacion",
    "room":               "habitacion",
    "bedroom":            "habitacion",
    "small_room":         "habitacion",
    "small room":         "habitacion",
    "study":              "habitacion",
    "cell":               "habitacion",
    "camarote":           "habitacion",
    "other":              "otro",
}

_ROL_ALIAS: dict[str, str] = {
    "protagonist":  "protagonista",
    "antagonist":   "antagonista",
    "secondary":    "secundario",
    "side":         "secundario",
    "supporting":   "secundario",
}


def _normalizar(valor: str, alias: dict[str, str]) -> str:
    """Devuelve el valor canónico si el input es un alias conocido, si no lo devuelve tal cual."""
    return alias.get(str(valor).strip().lower(), valor)


TipoCielo = Literal[
    "amanecer",
    "manana_despejada",
    "manana_nublada",
    "mediodia_soleado",
    "atardecer",
    "noche_estrellada",
    "noche_cerrada",
    "tormenta",
    "lluvia_suave",
    "niebla_densa",
    "dia_nevado",
    "cielo_magico",
    "interior_calido",
    "interior_frio",
    "interior_luminoso",
]

TipoAmbiente = Literal[
    "ciudad",       # urbano moderno: edificios, coches, farolas
    "pueblo",       # ciudad medieval o aldea con casas de piedra, adoquines, mercado — NO granjas ni campos
    "campo",        # entorno rural y agrícola: graneros, cercas, praderas, árboles dispersos, animales
    "naturaleza",   # espacio natural abierto genérico: el Constructor extrae del entorno el tipo de árbol/planta
    "bosque",       # foresta templada: robles, pinos, rocas, maleza
    "selva",        # tropical densa: palmeras, lianas, fauna
    "sabana",       # árida y abierta: acacias dispersas, hierba alta
    "pradera",      # campo abierto sin árboles ni edificios: flores silvestres, hierba, colinas suaves
    "desierto",     # árido: dunas, cactus o rocas, muy poco
    "playa",        # costa: arena, rocas, palmeras, conchas
    "montaña",      # rocoso y elevado: piedras, pinos, nieve
    "cueva",        # subterráneo natural: estalactitas, rocas, oscuridad
    "ruinas",       # estructuras antiguas degradadas: columnas, piedras
    "espacio",             # exterior cósmico: asteroides, estrellas, vacío
    "superficie_planeta",  # superficie de un planeta o luna: suelo de color decidido por el Organizador + asteroides flotantes
    "bajo_el_agua", # fondo marino: coral, algas, peces, rocas
    "sobre_agua",   # sobre una masa de agua (río/lago/mar): el suelo es agua animada y se camina sobre ella con chapoteos
    "barco",        # a bordo de un barco sobre el mar: cubierta jugable + agua alrededor; se puede desembarcar para caminar sobre el agua
    "habitacion",      # cuarto pequeño de una persona (dormitorio, estudio, despacho pequeño, celda, baño, camarote)
    "interior",        # espacio interior pequeño (cabaña, taberna, salón, bodega)
    "interior_grande", # espacio interior de gran escala (catedral, estadio, restaurante, discoteca, sala de conciertos)
    "otro",            # el Constructor lo construye desde cero con el LLM
]


class Personaje(BaseModel):
    id: str = Field(..., description="Identificador único, ej: 'personaje_caperucita'")
    nombre: str
    fisica: str = Field(
        ...,
        description=(
            "Apariencia visual breve: edad aproximada, rasgos físicos, ropa característica. "
            "NO incluir objetos portados que tengan ID propio en 'objetos'. "
            "Ejemplo: 'Niña de unos 8 años, capa roja con capucha, mejillas sonrosadas.'"
        )
    )
    background: str = Field(
        ...,
        description=(
            "Carácter, personalidad, motivaciones y estado emocional del personaje. "
            "Ejemplo: 'Impulsiva y curiosa, confía demasiado en desconocidos, habla sin filtros.'"
        )
    )
    rol: str = Field(..., description="protagonista | antagonista | secundario")

    @field_validator("rol", mode="before")
    @classmethod
    def _norm_rol(cls, v: str) -> str:
        return _normalizar(v, _ROL_ALIAS)

    skin_id: Optional[str] = Field(
        default=None,
        description=(
            "ID de la escena donde se estableció la apariencia visual actual de este personaje. "
            "Solo se rellena para personajes globales (que aparecen en más de una escena). "
            "Primera aparición: skin_id = id de la escena actual. "
            "Apariciones posteriores sin cambio visual: skin_id = id de su primera aparición. "
            "Cambio visual narrativo explícito: skin_id = id de la escena actual."
        )
    )


class Objeto(BaseModel):
    id: str
    nombre: str
    descripcion: str
    skin_id: Optional[str] = Field(
        default=None,
        description=(
            "ID de la primera escena donde apareció este objeto. "
            "Solo se rellena para objetos globales. Siempre apunta a la primera escena — "
            "los objetos no cambian de apariencia."
        )
    )
    # Nota: la decisión de si un objeto es interactuable la toma el Director, no el Organizador

    # ── Subtipo educativo 'vocabulario' (Tipo A, tangible) ────────────────────
    # Solo se rellenan en mundos de vocabulario. En el resto quedan None.
    nombre_objetivo: Optional[str] = Field(
        default=None,
        description=(
            "Nombre del objeto en el IDIOMA OBJETIVO que se aprende (distinto del idioma "
            "de la UI). El campo 'nombre' queda en idioma UI. Permite mostrar el par "
            "bilingüe en la escena de exposición, p.ej. 'Tenedor' (nombre) / 'Fork' "
            "(nombre_objetivo). Solo en mundos de vocabulario; None en el resto."
        )
    )
    frase_ejemplo: Optional[str] = Field(
        default=None,
        description=(
            "Frase de ejemplo opcional en el idioma objetivo que usa la palabra en contexto "
            "(escena de exposición de vocabulario). Null si no aplica."
        )
    )


class Evento(BaseModel):
    descripcion: str
    personajes_involucrados: List[str] = Field(default_factory=list)
    objetos_involucrados: List[str] = Field(default_factory=list)


class Escena(BaseModel):
    id: str = Field(..., description="Identificador único, ej: 'escena_01'")
    titulo: str
    entorno: str = Field(
        ...,
        description=(
            "Lugar físico concreto y específico donde ocurre la escena. "
            "No usar términos vagos como 'bosque' o 'casa'. "
            "Ejemplo: 'Cocina rústica con chimenea de piedra encendida, "
            "vigas de madera en el techo y ollas de cobre colgadas.'"
        )
    )
    atmosfera: str = Field(
        ...,
        description=(
            "Contexto emocional y narrativo de la escena: qué se siente, "
            "qué momento del día es, qué tensión o emoción hay. "
            "Ejemplo: 'Momento cálido de despedida, luz dorada de mañana, "
            "la madre mezcla ternura con preocupación discreta.'"
        )
    )
    cielo: TipoCielo = Field(
        ...,
        description="Tipo de cielo del catálogo WorldWeaver. Debe ser uno de los valores del Literal."
    )
    tipo_ambiente: TipoAmbiente = Field(
        ...,
        description="Categoría de entorno exterior para poblar el fondo 3D. Elige del catálogo WorldWeaver."
    )

    @field_validator("cielo", mode="before")
    @classmethod
    def _norm_cielo(cls, v: str) -> str:
        return _normalizar(v, _CIELO_ALIAS)

    @field_validator("tipo_ambiente", mode="before")
    @classmethod
    def _norm_ambiente(cls, v: str) -> str:
        return _normalizar(v, _AMBIENTE_ALIAS)
    tiene_intro: bool = Field(
        default=False,
        description=(
            "True si el jugador necesita un texto narrativo antes de explorar la escena. "
            "Obligatorio en la primera escena. Opcional en las demás cuando hay salto no evidente."
        )
    )
    texto_intro: Optional[str] = Field(
        default=None,
        description=(
            "Párrafo breve (2-4 frases) en voz de narrador omnisciente. "
            "Solo si tiene_intro=true. Tiempo pasado, prosa literaria."
        )
    )
    texto_fin: Optional[str] = Field(
        default=None,
        description=(
            "Texto de conclusión narrativa. Solo en la ÚLTIMA escena. "
            "2-4 frases en voz de narrador omnisciente, tiempo pasado, prosa literaria, "
            "que cierren el arco de la historia. Null en todas las demás escenas."
        )
    )
    rol_escena: Optional[Literal["exposicion", "examen"]] = Field(
        default=None,
        description=(
            "Solo en mundos de vocabulario (subtipo educativo 'vocabulario'). "
            "'exposicion' = el jugador conoce el vocabulario de forma pasiva (objetos con "
            "nombre bilingüe visible); 'examen' = el jugador es puesto a prueba (objetos sin "
            "nombre, el guía los pide uno a uno). None en cualquier otro tipo de mundo."
        )
    )
    personajes: List[Personaje]
    objetos: List[Objeto]
    eventos: List[Evento]


class ParVocab(BaseModel):
    """Par concepto↔traducción para mundos de vocabulario. Imprescindible en el subtipo
    CONVERSACIONAL (Tipo B), donde el vocabulario no son objetos: lo usan el Programador (para
    generar preguntas con opciones) y el Examinador (para el quiz)."""
    ui: str = Field(..., description="El concepto/frase en el idioma de la UI (p.ej. 'Buenos días')")
    objetivo: str = Field(..., description="El mismo concepto en el idioma objetivo (p.ej. 'Good morning')")
    nota: Optional[str] = Field(
        default=None,
        description="Nota breve de uso opcional (p.ej. 'saludo de mañana', 'mes nº 1').",
    )


class SalidaOrganizador(BaseModel):
    titulo_historia: str
    escenas: List[Escena]
    vocabulario: List[ParVocab] = Field(
        default_factory=list,
        description=(
            "Pares concepto↔traducción del vocabulario (subtipo vocabulario). Esencial en CONVERSACIONAL "
            "(Tipo B), donde no hay objetos que lo lleven; vacío o redundante en tangible."
        ),
    )
    personajes_globales: List[Personaje] = Field(
        default_factory=list,
        description="Personajes que aparecen en más de una escena"
    )
    objetos_globales: List[Objeto] = Field(
        default_factory=list,
        description="Objetos que aparecen en más de una escena"
    )

    # ── Metadatos de clasificación educativa ─────────────────────────────────
    # Los rellena el código del Organizador tras clasificar (no el LLM). Los leen
    # el validador, el Programador y el Examinador para no reclasificar.
    subtipo_educativo: Optional[str] = Field(
        default=None,
        description="Subtipo detectado en modo educativo: 'historico' | 'taxonomico' | 'vocabulario'. None en modo narrativo.",
    )
    tipo_vocabulario: Optional[str] = Field(
        default=None,
        description="Solo si subtipo_educativo='vocabulario': 'tangible' | 'conversacional'.",
    )
    idioma_objetivo: Optional[str] = Field(
        default=None,
        description="Solo en mundos de vocabulario: idioma que se aprende (p.ej. 'en'), distinto del idioma de la UI.",
    )