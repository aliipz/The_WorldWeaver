"""
Schema de salida del Agente 5 (Programador) — v2.

El manifest tiene cuatro secciones:
  fases[]            — una por evento: qué nodos brillan + condición para avanzar
  personajes[]       — diálogos por fase para cada personaje
  objetos[]          — interacciones para objetos/decorados (sin fases propias)
  zonas_narrativas[] — texto narrador al entrar en zonas espaciales

interactions.js consume este manifest para gestionar el descubrimiento narrativo.
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Annotated, List, Literal, Optional, Union


# ─── Efectos visuales ─────────────────────────────────────────────────────────

TipoEfecto = Literal["llama", "brillo", "rotar", "pulsar", "desaparecer", "flotar", "sacudir",
                     "aparecer", "abrir", "emitir_particulas", "cambiar_color", "escapar"]


class Disparar(BaseModel):
    id_nodo: str = Field(..., description="ID del nodo destino en el SceneGraph")
    efecto: Optional[TipoEfecto] = Field(
        None,
        description="Efecto visual sobre el nodo destino. Null si solo se quiere triggear animacion."
    )
    color: Optional[str] = Field(
        None,
        description="Color hex opcional para el efecto 'brillo'. Ej: '#4488ff' para luz azul mágica."
    )
    animacion: Optional[str] = Field(
        None,
        description=(
            "Animación que reproduce el personaje destino al triggerear este disparo. "
            "Solo si id_nodo apunta a un personaje. El catálogo depende del tipo del personaje: "
            "HUMANO → Idle | Victory | Defeat | Death | RecieveHit | Punch | SwordSlash | "
            "Jump | SitDown | StandUp | PickUp | Roll | Shoot_OneHanded. "
            "CRIATURA no-humana → solo: alegria | susto | null."
        )
    )


# ─── Fases (estructura narrativa) ─────────────────────────────────────────────

class CondicionAvance(BaseModel):
    nodos: List[str] = Field(
        default_factory=list,
        description="IDs de objetos/decorados con los que el jugador debe haber interactuado"
    )
    personajes: List[str] = Field(
        default_factory=list,
        description="IDs de personajes con los que el jugador debe haber hablado"
    )
    zonas: List[str] = Field(
        default_factory=list,
        description="IDs de zonas_narrativas que el jugador debe haber visitado"
    )


class FaseManifest(BaseModel):
    id_evento: str = Field(..., description="Identificador del evento, ej: 'evento_00'")
    fase: int = Field(..., description="Índice 0-based de la fase")
    texto_objetivo: Optional[str] = Field(
        None,
        description=(
            "Frase narrativa corta (5-10 palabras) que el tracker de objetivos muestra al jugador "
            "como subtítulo de esta fase. Tono literario, sin mencionar IDs. "
            "Ej: 'El mago tiene algo que confesar...' o 'Un secreto yace entre las ruinas...'"
        )
    )
    guias: List[str] = Field(
        ...,
        description=(
            "IDs de nodos que emiten aura dorada en esta fase. "
            "Pueden ser personajes, objetos o decorados que el jugador debería descubrir. "
            "1-3 por fase."
        )
    )
    condicion_avance: CondicionAvance = Field(
        ...,
        description=(
            "Qué debe completar el jugador para considerar este evento 'vivido' "
            "y desbloquear la siguiente fase. Sé razonable: 1-2 condiciones."
        )
    )


# ─── Personajes (diálogos por fase) ───────────────────────────────────────────

class OpcionDialogo(BaseModel):
    etiqueta: str = Field(..., description="Texto del botón, máx ~30 chars")
    respuesta: str = Field(..., description="Respuesta completa del personaje")
    correcta: bool = Field(
        False,
        description=(
            "Solo en exámenes de vocabulario conversacional (examen_opciones): marca la opción CORRECTA. "
            "Elegirla avanza la fase; las demás cuentan como fallo. En diálogos normales se ignora."
        ),
    )


class PuntoDialogo(BaseModel):
    frases: List[str] = Field(
        ...,
        min_length=1,
        max_length=1,
        description=(
            "Exactamente 1 frase en voz del personaje. "
            "Si hay opciones: frase de apertura. Si no hay opciones: monólogo completo."
        )
    )
    opciones: List[OpcionDialogo] = Field(
        default_factory=list,
        max_length=4,
        description=(
            "Vacío → monólogo. "
            "2 opciones → diálogo narrativo (etiqueta = lo que dice el JUGADOR, respuesta = réplica). "
            "3-4 opciones → pregunta de examen conversacional (una con 'correcta': true)."
        )
    )


class DialogoFase(BaseModel):
    fase: int = Field(..., description="Fase a partir de la cual aplica este diálogo")
    animacion: Optional[str] = Field(
        None,
        description=(
            "Animación que reproduce ESTE personaje al abrirse este diálogo. "
            "Usa solo en momentos narrativamente fuertes (derrota, celebración, muerte dramática...). "
            "El catálogo depende del tipo del personaje: "
            "HUMANO → Victory | Defeat | Death | RecieveHit | Punch | SwordSlash | Jump | SitDown | PickUp. "
            "CRIATURA no-humana → solo: alegria | susto | null."
        )
    )
    puntos: List[PuntoDialogo] = Field(
        ...,
        min_length=1,
        max_length=3,
        description=(
            "1-3 puntos de diálogo que rotan en visitas sucesivas al personaje. "
            "El primero es el narrativamente importante (puede desbloquear la fase). "
            "Los siguientes son contenido extra opcional para jugadores que vuelven."
        )
    )
    pista: Optional[PuntoDialogo] = Field(
        None,
        description=(
            "Solo en exámenes de vocabulario: pista que el guía da si el jugador entrega el objeto "
            "equivocado en esta fase. Reformula la petición añadiendo un rasgo descriptivo (color, "
            "forma, característica) SIN revelar la palabra del idioma objetivo. El runtime la muestra "
            "como diálogo al fallar."
        )
    )


class DialogoConItem(BaseModel):
    requiere_objeto: str = Field(
        ...,
        description="id_nodo del objeto que debe estar en el inventario del jugador para activar este diálogo"
    )
    consume: bool = Field(
        False,
        description=(
            "Si True, el objeto se elimina del inventario al activar este diálogo "
            "(el jugador lo entrega al personaje). Úsalo cuando la mecánica es entregar "
            "o dar el objeto, no solo mostrárselo."
        )
    )
    puntos: List[PuntoDialogo] = Field(
        ...,
        min_length=1,
        max_length=2,
        description=(
            "1-2 puntos de diálogo que el personaje dice cuando el jugador lleva este objeto. "
            "El personaje reacciona al objeto específico que el jugador porta."
        )
    )


class AccionPersonaje(BaseModel):
    tecla: str = Field(
        ...,
        description=(
            "Tecla que activa la acción. Usar SOLO: KeyQ | KeyR | KeyT | KeyG | KeyX | KeyZ. "
            "NUNCA usar KeyW/KeyA/KeyS/KeyD (movimiento) ni KeyE (hablar) ni KeyF (modo FPS)."
        )
    )
    etiqueta: str = Field(..., description="Texto del hint. Ej: 'Provocar', 'Agitar', 'Inspeccionar'")
    descripcion: Optional[str] = Field(
        None,
        description=(
            "Texto narrativo (1-2 frases) que se muestra en un panel cuando el jugador ejecuta "
            "la acción. Describe lo que ocurre en escena desde la perspectiva del narrador. "
            "Ej: 'El anciano dobla las rodillas y musita una oración en voz baja.' "
            "Obligatorio si la acción es narrativa; opcional pero recomendado para efectos ambientales."
        )
    )
    animacion: Optional[str] = Field(
        None,
        description=(
            "Animación que reproduce EL PROPIO personaje al ejecutar esta acción. "
            "El catálogo depende del tipo del personaje: "
            "HUMANO → Idle | Victory | Defeat | Death | RecieveHit | Punch | SwordSlash | "
            "Jump | SitDown | StandUp | PickUp | Roll | Shoot_OneHanded. "
            "CRIATURA no-humana → solo: alegria | susto | null."
        )
    )
    narrativa: bool = Field(
        ...,
        description=(
            "True → cuenta para condicion_avance igual que hablar (avanza la historia). "
            "False → efecto ambiental, no avanza nada (encender linterna, agitar árbol...)."
        )
    )
    fase_aparicion: int = Field(0, description="Fase desde la que esta acción está disponible")
    sonido: Optional[Literal[
        "suave", "criatura", "ritual", "esfuerzo", "alegria",
        "vibrar", "rugir", "metal", "agua", "magico",
    ]] = Field(
        None,
        description=(
            "Sonido procedimental que suena al ejecutar la acción. "
            "EXPRESIÓN DEL SER: suave = suspirar, rezar, murmurar; "
            "criatura = ladrar, maullar, gruñir, rugido animal; "
            "ritual = invocar, conjurar, meditar; esfuerzo = golpear, empujar, forcejear; "
            "alegria = reír, celebrar, bailar. "
            "OBJETO/ELEMENTO (cuando la acción acciona algo del mundo): "
            "vibrar = zumbar/vibrar (máquina, cristal, portal); "
            "rugir = retumbo grave (motor, trueno, derrumbe); "
            "metal = golpe metálico (espada, gong, campana, palanca); "
            "agua = chapoteo/líquido (fuente, poción, pozo); "
            "magico = destello/chispa (hechizo, objeto encantado). "
            "Omitir (null) si la acción no produce un sonido claro (examinar, señalar, espiar)."
        )
    )
    dispara: List[Disparar] = Field(
        default_factory=list,
        description=(
            "Lista de efectos/animaciones que se disparan simultáneamente al ejecutar la acción. "
            "Puede apuntar a varios nodos a la vez."
        )
    )


class FichaInfo(BaseModel):
    """Tarjeta de presentación educativa de un personaje (tecla I).

    Solo modo educativo. Texto breve y divulgativo tipo ficha: quién es, su rol y
    1-2 datos clave. No es diálogo en primera persona — es una ficha informativa.
    """
    titulo: str = Field(
        ...,
        description="Nombre + rol en una línea. Ej: 'John F. Kennedy — Presidente de los EE. UU.'"
    )
    texto: str = Field(
        ...,
        description="2-3 frases divulgativas: quién es y por qué es relevante en el tema. Tono ficha, no teatral."
    )


class PersonajeManifest(BaseModel):
    id_nodo: str
    fase_aparicion: int = Field(
        ...,
        description="Fase en la que este personaje se vuelve accesible (0 = desde el inicio)"
    )
    ficha_info: Optional[FichaInfo] = Field(
        None,
        description=(
            "Tarjeta de presentación educativa (tecla I). SOLO modo educativo. "
            "Ficha breve: quién es el personaje, su rol y un dato clave del tema. "
            "Null en modo narrativo."
        )
    )
    dialogos: List[DialogoFase] = Field(
        ...,
        min_length=1,
        description=(
            "Un DialogoFase por cada fase en que el personaje cambia su discurso. "
            "El jugador ve el diálogo de la fase más alta que haya alcanzado."
        )
    )
    dialogos_con_item: List[DialogoConItem] = Field(
        default_factory=list,
        description=(
            "Diálogos alternativos que se activan cuando el jugador lleva un objeto concreto "
            "en el inventario. Tienen prioridad sobre los dialogos normales mientras el item "
            "esté en el inventario. Opcional — solo si aporta valor narrativo real."
        )
    )
    acciones: List[AccionPersonaje] = Field(
        default_factory=list,
        description=(
            "Acciones adicionales sobre este personaje más allá del diálogo. "
            "Máximo 2. Pueden ser narrativas (avanzan historia) o ambientales (efectos sin avance). "
            "Ejemplo: provocar al guardia, agitar al árbol parlante, inspeccionar al sospechoso."
        )
    )
    dispara: Optional[Disparar] = Field(
        None,
        description="Opcional: efecto que se activa en otro nodo cuando el jugador habla con este personaje. "
                    "Ej: hablar con el mago abre una puerta, hablar con el guardia enciende una antorcha."
    )


# ─── Objetos e interacciones ──────────────────────────────────────────────────

class InteraccionExaminar(BaseModel):
    tipo: Literal["examinar"] = "examinar"
    titulo: Optional[str] = None
    descripcion: str = Field(..., description="2-3 frases narrativas: qué es, qué significa en la historia")
    efecto_visual: Optional[TipoEfecto] = Field(
        None,
        description="Opcional: efecto visual que se activa AL MISMO TIEMPO que se muestra el panel. "
                    "Ej: la chimenea se enciende mientras describes qué es."
    )
    color_efecto: Optional[str] = Field(
        None,
        description="Color hex para el efecto 'brillo'. Ej: '#4488ff'. Si null, amarillo cálido por defecto."
    )


class InteraccionActivar(BaseModel):
    tipo: Literal["activar"] = "activar"
    texto_activacion: Optional[str] = Field(None, description="Texto narrativo al activar")
    texto_desactivacion: Optional[str] = Field(None, description="Texto al desactivar, null si es acción única")
    efecto_visual: Optional[TipoEfecto] = None
    color_efecto: Optional[str] = Field(
        None,
        description="Color hex para el efecto 'llama'/'brillo'. Ej: '#ff6010' para fuego, '#4488ff' para luz azul mágica, "
                    "'#ff3300' para fuego vivo, '#00ffcc' para magia verdosa. Si null, amarillo cálido."
    )
    descripcion: Optional[str] = Field(
        None,
        description="Opcional: texto descriptivo adicional que aparece como panel junto al efecto. "
                    "Úsalo cuando el efecto merece una explicación narrativa más larga."
    )


class InteraccionLore(BaseModel):
    tipo: Literal["lore"] = "lore"
    texto: str = Field(..., description="1-2 frases de lore ambiental. Aparece en hover largo.")


class InteraccionRecoger(BaseModel):
    tipo: Literal["recoger"] = "recoger"
    titulo: Optional[str] = Field(
        None,
        description="Nombre del objeto en el inventario. Si null, usa el nombre del nodo."
    )
    descripcion: Optional[str] = Field(
        None,
        description="Texto breve que aparece al recoger el objeto. Si null, solo toast."
    )


class InteraccionUsarCon(BaseModel):
    tipo: Literal["usar_con"] = "usar_con"
    requiere_objeto: str = Field(
        ...,
        description="id_nodo del objeto que debe estar en el inventario del jugador"
    )
    titulo: str
    descripcion: str = Field(..., description="2-3 frases de lo que ocurre al usar el objeto aquí")
    efecto_visual: Optional[TipoEfecto] = None
    color_efecto: Optional[str] = Field(
        None,
        description="Color hex para el efecto 'brillo'. Ej: '#4488ff'. Si null, amarillo cálido por defecto."
    )
    sonido: Optional[Literal["vibrar", "rugir", "metal", "agua", "magico"]] = Field(
        None,
        description=(
            "Sonido del momento de combinar, según el objeto/elemento implicado: "
            "metal = llave en cerradura, mecanismo, reja; agua = verter, sumergir, poción; "
            "magico = activar runa, conjuro, encantamiento; vibrar = máquina/cristal/portal; "
            "rugir = motor, mecanismo pesado. Si null, suena el efecto genérico de 'usar con'."
        )
    )


TipoInteraccionObjeto = Annotated[
    Union[InteraccionExaminar, InteraccionActivar, InteraccionLore,
          InteraccionRecoger, InteraccionUsarCon],
    Field(discriminator="tipo")
]


class ProximidadConfig(BaseModel):
    efecto: TipoEfecto = Field(
        ...,
        description=(
            "Efecto que se activa cuando el jugador se acerca. "
            "Recomendado: 'escapar' (mariposas, pájaros), 'sacudir' (vegetación), "
            "'pulsar' (objetos mágicos), 'flotar' (espíritus)."
        )
    )
    radio: float = Field(
        2.5,
        description="Radio en unidades de escena que activa la reacción (recomendado: 2.0–4.0)."
    )
    una_vez: bool = Field(
        True,
        description="Si true, solo se activa la primera vez que el jugador se acerca."
    )


class AccionObjetoLeer(BaseModel):
    tipo: Literal["leer"] = "leer"
    tecla: str = Field(
        ...,
        description="Tecla que abre la lectura. SOLO: KeyQ | KeyR | KeyT | KeyX | KeyZ."
    )
    etiqueta: str = Field(
        "Leer",
        description="Texto del hint. Ej: 'Leer', 'Descifrar', 'Leer inscripción'"
    )
    titulo: Optional[str] = Field(
        None,
        description="Título del documento en la overlay. Si null, usa el nombre del nodo."
    )
    texto: str = Field(
        ...,
        description="Contenido del documento. 2-5 frases en tono literario y narrativo."
    )
    estilo: Literal["pergamino", "libro", "nota", "inscripcion"] = Field(
        "pergamino",
        description="Estilo visual de la overlay de lectura."
    )


class AccionSecundariaObjeto(BaseModel):
    tipo: Literal["accion"] = "accion"
    tecla: str = Field(
        ...,
        description=(
            "Tecla que activa la acción. SOLO: KeyQ | KeyR | KeyT | KeyG | KeyX | KeyZ. "
            "NUNCA usar KeyW/KeyA/KeyS/KeyD (movimiento) ni KeyE (examinar) ni KeyF (modo FPS)."
        )
    )
    etiqueta: str = Field(..., description="Texto del hint. Ej: 'Avivar llamas', 'Asomarse', 'Agitar'")
    descripcion: Optional[str] = Field(
        None,
        description=(
            "Texto narrativo (1-2 frases) que aparece en un panel al ejecutar la acción. "
            "Si null, solo suena el efecto y se muestra un toast con la etiqueta."
        )
    )
    efecto_visual: Optional[TipoEfecto] = Field(
        None,
        description="Efecto visual que se activa al ejecutar la acción (opcional)."
    )
    sonido: Optional[Literal[
        "suave", "criatura", "ritual", "esfuerzo", "alegria",
        "vibrar", "rugir", "metal", "agua", "magico",
    ]] = Field(
        None,
        description=(
            "Sonido procedimental que suena al ejecutar la acción del objeto. "
            "Prefiere los de OBJETO/ELEMENTO: vibrar = zumbar/vibrar (máquina, cristal, portal); "
            "rugir = retumbo grave (motor, trueno, derrumbe); "
            "metal = golpe metálico (espada, gong, campana, palanca, reja); "
            "agua = chapoteo/líquido (fuente, poción, pozo); "
            "magico = destello/chispa (hechizo, objeto encantado, teletransporte). "
            "Los de SER (suave, criatura, ritual, esfuerzo, alegria) solo para objetos "
            "mágicos/animados. Omitir (null) si la acción no produce un sonido claro."
        )
    )


TipoAccionObjeto = Annotated[
    Union[AccionObjetoLeer, AccionSecundariaObjeto],
    Field(discriminator="tipo")
]


class ObjetoManifest(BaseModel):
    id_nodo: str
    fase_aparicion: int = Field(
        ...,
        description="Fase en la que este objeto/decorado se vuelve accesible e interactuable"
    )
    interaccion: TipoInteraccionObjeto
    acciones: List[TipoAccionObjeto] = Field(
        default_factory=list,
        description=(
            "Acciones extra accesibles con teclas distintas a E. Máximo 2. "
            "tipo 'leer': documentos legibles (pergaminos, cartas, libros, inscripciones). "
            "tipo 'accion': interacción ambiental secundaria (efecto visual, sonido, texto breve). "
            "Úsala en objetos donde una segunda interacción enriquece la escena sin afectar la progresión."
        )
    )
    proximidad: Optional[ProximidadConfig] = Field(
        None,
        description=(
            "Reacción visual automática cuando el jugador se acerca, sin que pulse ninguna tecla. "
            "Úsala para objetos ambientales vivos: mariposas ('escapar'), vegetación ('sacudir'), "
            "objetos mágicos ('pulsar'). NUNCA en objetos narrativos necesarios para avanzar."
        )
    )
    dispara: Optional[Disparar] = Field(
        None,
        description="Efecto encadenado opcional sobre otro nodo al interactuar con este"
    )


# ─── Zonas narrativas ─────────────────────────────────────────────────────────

class ZonaNarrativa(BaseModel):
    id: str = Field(..., description="Identificador único, ej: 'zona_entrada'")
    columnas: List[int] = Field(
        ...,
        description="Columnas del grid (0-4) que forman la zona. Se dispara al entrar."
    )
    texto: str = Field(..., description="Texto narrador al entrar. Tono literario, 1-2 frases.")


# ─── Salida del Programador ───────────────────────────────────────────────────

class SalidaProgramador(BaseModel):
    id_escena: str
    fases: List[FaseManifest] = Field(
        ...,
        min_length=1,
        description="Una fase por evento narrativo, en orden cronológico"
    )
    personajes: List[PersonajeManifest] = Field(
        ...,
        description="Todos los personajes de la escena con sus diálogos por fase"
    )
    objetos: List[ObjetoManifest] = Field(
        default_factory=list,
        description="Objetos y decorados con interacción (excluye fondo, suelo, ambiente)"
    )
    zonas_narrativas: List[ZonaNarrativa] = Field(
        default_factory=list,
        description="0-2 zonas espaciales con texto narrador"
    )
    examen_vocabulario: bool = Field(
        default=False,
        description=(
            "True en una escena de EXAMEN de vocabulario (Tipo A). El viewer cambia a modo "
            "examen-por-entrega: recoger no avanza fase; solo avanza al entregar al guía el "
            "objeto pedido de cada fase; el objeto equivocado suma un fallo (a los 3, recarga)."
        ),
    )
    examen_opciones: bool = Field(
        default=False,
        description=(
            "True en una escena de EXAMEN de vocabulario CONVERSACIONAL (Tipo B). El viewer trata las "
            "opciones de diálogo del guía como un quiz: elegir la opción 'correcta' avanza la fase; "
            "una opción equivocada suma un fallo (a los 3, recarga) y muestra la pista."
        ),
    )
