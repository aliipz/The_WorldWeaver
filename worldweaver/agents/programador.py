"""
Agente 5 — El Programador (v3)

Tres pasadas:
  P1 (estructural): backbone determinista + LLM decide guias, condicion_avance,
                    interacciones de objetos narrativos y zonas narrativas.
  P2 (diálogos):   LLM genera diálogos por fase para cada personaje con brief
                    de contexto narrativo.
  P3 (ambient):    LLM opcional — anima decorados no narrativos (velas, fuentes,
                    pinturas…) para hacer la escena más viva.

Entrada:  SceneGraph + Escena
Salida:   (SalidaProgramador, mensajes_combinados)
"""

import json
import re
import time
import random
import logging

from langchain_core.messages import SystemMessage, HumanMessage

from config.prompts import get_prompts
from config.llm import get_llm
from pipeline.errors import AgentError
from schemas.escenas import Escena
from schemas.scene_graph import SceneGraph
from schemas.interacciones import SalidaProgramador

logger = logging.getLogger(__name__)

TIPOS_EXCLUIDOS = {"fondo", "suelo", "ambiente"}


def _limpiar_json(texto: str) -> str:
    texto = re.sub(r"```(?:json)?\s*", "", texto)
    return texto.replace("```", "").strip()


def _invoke_con_backoff(llm, messages, *, max_esperas=4, espera_base=20.0):
    """Invoca el LLM reintentando *in situ* ante 429 (rate limit).

    Un 429 no es un error de contenido: regenerar el manifest entero gastaría
    más tokens contra el mismo límite por minuto. Aquí esperamos a que la
    ventana se renueve y reintentamos la MISMA llamada, sin consumir el
    presupuesto de reintentos del grafo. Cualquier otro error se propaga al
    instante, igual que antes.
    """
    for intento in range(max_esperas + 1):
        try:
            return llm.invoke(messages)
        except Exception as e:
            msg = str(e).lower()
            es_429 = "429" in msg or "rate_limit" in msg or "rate limit" in msg
            if not es_429 or intento == max_esperas:
                raise
            espera = espera_base * (intento + 1)  # 20s, 40s, 60s, 80s
            logger.warning(
                f"[Programador] Rate limit (429) — esperando {espera:.0f}s y "
                f"reintentando la misma llamada ({intento + 1}/{max_esperas})"
            )
            time.sleep(espera)


def _reparar_dispara(datos: dict) -> dict:
    """Normaliza el campo `dispara` de personajes y objetos.

    A nivel personaje/objeto, `dispara` es un objeto único (Optional[Disparar]),
    pero el LLM a veces lo devuelve como `{}` o como lista `[{...}]` (confusión
    con AccionPersonaje.dispara, que sí es lista). Coercionamos a un objeto único
    o a null para que no rompa la validación del esquema.
    """
    def _norm(item):
        d = item.get("dispara")
        if d == {} or d == []:
            item["dispara"] = None
        elif isinstance(d, list):
            item["dispara"] = d[0]  # toma el primer objetivo
    for p in datos.get("personajes", []):
        _norm(p)
    for o in datos.get("objetos", []):
        _norm(o)
    return datos


# ─── Backbone determinista ────────────────────────────────────────────────────

def _construir_backbone(escena: Escena, ids_disponibles: set) -> list[dict]:
    """
    Deriva la estructura de fases a partir de eventos[] del Organizador.
    Retorna lista de dicts con id_evento, fase, descripcion, central, secundarios.
    Las fases se numeran consecutivamente desde 0 independientemente de qué
    eventos se salten (evita índices discontinuos que rompen el validador).
    """
    backbone = []
    fase = 0
    for i, evento in enumerate(escena.eventos):
        objetos    = [o for o in evento.objetos_involucrados    if o in ids_disponibles]
        personajes = [p for p in evento.personajes_involucrados if p in ids_disponibles]
        todos = objetos + personajes
        if not todos:
            continue
        backbone.append({
            "id_evento":   f"evento_{i:02d}",
            "fase":        fase,
            "descripcion": evento.descripcion,
            "central":     todos[0],
            "secundarios": todos[1:],
            "todos":       todos,
        })
        fase += 1

    # Fallback: si ningún evento tiene nodos válidos, crear una fase genérica
    if not backbone:
        todos = sorted(ids_disponibles)[:3]
        if todos:
            backbone.append({
                "id_evento":   "evento_00",
                "fase":        0,
                "descripcion": escena.atmosfera,
                "central":     todos[0],
                "secundarios": todos[1:],
                "todos":       todos,
            })

    return backbone


def _formatear_backbone(backbone: list[dict]) -> str:
    lineas = []
    for b in backbone:
        lineas.append(
            f"Fase {b['fase']} ({b['id_evento']}): \"{b['descripcion']}\"\n"
            f"  Central: {b['central']}\n"
            f"  Secundarios: {b['secundarios'] or '(ninguno)'}"
        )
    return "\n\n".join(lineas)


# ─── Brief de personajes para P2 ─────────────────────────────────────────────

def _formatear_personajes_brief(escena: Escena, backbone: list[dict], humanos: set[str]) -> str:
    # Mapear en qué fases aparece cada personaje
    fases_por_personaje: dict[str, list[dict]] = {}
    for b in backbone:
        for pid in b["todos"]:
            if pid.startswith("personaje_"):
                fases_por_personaje.setdefault(pid, []).append(b)

    # También incluir personajes que no aparecen en eventos pero sí en la escena
    for p in escena.personajes:
        fases_por_personaje.setdefault(p.id, [])

    personajes_dict = {p.id: p for p in escena.personajes}

    lineas = []
    for pid, fases in fases_por_personaje.items():
        p = personajes_dict.get(pid)
        fisica     = (p.fisica     or "") if p else ""
        background = (p.background or "(sin descripción)") if p else "(sin descripción)"
        rol    = p.rol    if p else "secundario"
        nombre = p.nombre if p else pid

        fase_ap = fases[0]["fase"] if fases else 0

        es_humano = pid in humanos
        tipo_anim = ("humano (catálogo Quaternius: Victory/Defeat/RecieveHit/Jump/...)"
                     if es_humano else
                     "criatura no-humana (catálogo procedural: alegria | susto | null)")

        lineas.append(f"─── {pid} ({nombre})")
        if fisica:
            lineas.append(f"  Físico: {fisica}")
        lineas.append(f"  Carácter: {background}")
        lineas.append(f"  Rol: {rol} | fase_aparicion: {fase_ap}")
        lineas.append(f"  Tipo de animación: {tipo_anim}")
        if fases:
            lineas.append("  Aparece en:")
            for b in fases:
                lineas.append(f"    • Fase {b['fase']}: \"{b['descripcion']}\"")
        else:
            lineas.append("  ⚠ SIN EVENTO — DEBES incluirlo igualmente con 1-2 frases de diálogo ambiental coherente con la escena.")
        lineas.append("")

    return "\n".join(lineas)


# ─── Pasada 1: estructura narrativa ──────────────────────────────────────────

def _formatear_vocab_lista(escena: Escena, examen: bool) -> str:
    """Lista de vocabulario para inyectar en los prompts de vocab. En exposición
    muestra el par bilingüe (nombre UI / objetivo); en examen solo la palabra
    objetivo (el nombre UI es neutro y no debe revelarse)."""
    lineas = []
    for o in escena.objetos:
        objetivo = (o.nombre_objetivo or "").strip()
        if not objetivo:
            continue
        lineas.append(f"  · {o.id} — {o.nombre} / {objetivo}")
    return "\n".join(lineas) if lineas else "  (sin vocabulario etiquetado)"


def _es_vocab_tangible(escena: Escena, modo: str, tipo_vocabulario: str | None) -> bool:
    return (
        modo == "educativo"
        and tipo_vocabulario == "tangible"
        and getattr(escena, "rol_escena", None) in ("exposicion", "examen")
    )


def _es_vocab_conversacional(escena: Escena, modo: str, tipo_vocabulario: str | None) -> bool:
    return (
        modo == "educativo"
        and tipo_vocabulario == "conversacional"
        and getattr(escena, "rol_escena", None) in ("exposicion", "examen")
    )


def _formatear_vocabulario_conversacional(vocabulario) -> str:
    """Lista de pares concepto↔traducción (ParVocab o dicts) para inyectar en los
    prompts conversacionales: 'ui = objetivo  (nota)'."""
    lineas = []
    for par in (vocabulario or []):
        ui  = par.get("ui") if isinstance(par, dict) else getattr(par, "ui", "")
        obj = par.get("objetivo") if isinstance(par, dict) else getattr(par, "objetivo", "")
        nota = par.get("nota") if isinstance(par, dict) else getattr(par, "nota", None)
        if not (ui and obj):
            continue
        s = f"  · {ui} = {obj}"
        if nota:
            s += f"  ({nota})"
        lineas.append(s)
    return "\n".join(lineas) if lineas else "  (sin vocabulario)"


def _reparar_una_correcta_opciones(opciones: list[dict]) -> None:
    """Garantiza UNA sola opción con correcta=True en una pregunta de examen conversacional.
    Si hay varias, conserva la primera; si no hay ninguna, marca la primera."""
    if not opciones:
        return
    idx = [i for i, o in enumerate(opciones) if o.get("correcta") is True]
    if len(idx) == 1:
        return
    for o in opciones:
        o.pop("correcta", None)
    opciones[idx[0] if idx else 0]["correcta"] = True


_PRAISE_VOCAB = {
    "es": lambda w: f"¡Correcto! Es '{w}'. ¡Muy bien!",
    "en": lambda w: f"Correct! It's '{w}'. Well done!",
}


def _limpiar_marcas(s: str) -> str:
    """Quita el resaltado educativo ==así== que el LLM a veces mete en campos de datos."""
    return re.sub(r"==(.+?)==", r"\1", s or "").strip()


def _rellenar_dialogos_con_item_vocab(personajes_merged: list[dict], escena: Escena, idioma: str) -> None:
    """En el examen de vocabulario tangible, garantiza que el guía tenga un
    'dialogos_con_item' (consume=true) por cada objeto del vocabulario, para que al
    entregar el objeto correcto el guía lo reciba y felicite. Determinista: rellena
    solo los que el LLM no haya generado, conservando los suyos. La condición de avance
    de fase ya funciona sin esto (se gatea con 'recoger'); esto añade el feedback/entrega."""
    praise = _PRAISE_VOCAB.get(idioma, _PRAISE_VOCAB["es"])
    # Solo los personajes reales de la escena (el guía), no decorados/ambiente.
    ids_personajes = {p.id for p in escena.personajes}
    objetos_vocab = [(o.id, _limpiar_marcas(o.nombre_objetivo))
                     for o in escena.objetos if _limpiar_marcas(o.nombre_objetivo)]
    if not objetos_vocab:
        return
    for pm in personajes_merged:
        if pm["id_nodo"] not in ids_personajes:
            continue
        existentes = pm.get("dialogos_con_item") or []
        cubiertos = {d.get("requiere_objeto") for d in existentes}
        for obj_id, palabra in objetos_vocab:
            if obj_id in cubiertos:
                continue
            existentes.append({
                "requiere_objeto": obj_id,
                "consume": True,
                "puntos": [{"frases": [praise(palabra)], "opciones": []}],
            })
        pm["dialogos_con_item"] = existentes


def _pasada_estructural(
    scenegraph: SceneGraph,
    escena: Escena,
    backbone: list[dict],
    llm,
    P,
    errores_previos: list[str] | None = None,
    modo: str = "narrativo",
    tipo_vocabulario: str | None = None,
    idioma_objetivo: str | None = None,
) -> dict:
    # Personajes humanos (catálogo Quaternius) están en registro_personajes; los
    # no-humanos (animales/criaturas de poly.pizza) no. El campo "humano" le dice al
    # LLM qué catálogo de animación usar para cada personaje (ver prompt P1).
    humanos = set(scenegraph.registro_personajes or {})
    nodos_resumen = []
    for n in scenegraph.nodos:
        if n.tipo in TIPOS_EXCLUIDOS:
            continue
        entrada = {"id": n.id, "nombre": n.nombre, "tipo": n.tipo, "origen": n.origen}
        if n.tipo == "personaje":
            entrada["humano"] = n.id in humanos
        nodos_resumen.append(entrada)

    user_prompt = P.PROGRAMADOR_P1_USER.format(
        id_escena=scenegraph.id_escena,
        entorno=escena.entorno,
        atmosfera=escena.atmosfera,
        backbone_json=_formatear_backbone(backbone),
        nodos_json=json.dumps(nodos_resumen, indent=2, ensure_ascii=False),
    )

    # En modo educativo, las descripciones de objetos deben enseñar (informativas),
    # no dramatizar — se añade un bloque de tono al system sin tocar la estructura.
    p1_system = P.PROGRAMADOR_P1_SYSTEM
    if modo == "educativo":
        p1_system = p1_system + "\n\n" + P.PROGRAMADOR_P1_EDUCATIVO_EXTRA \
                              + "\n\n" + P.RESALTADO_EDUCATIVO
        # Vocabulario tangible: instrucciones específicas según el rol de la escena
        # (exposición → examinar bilingüe; examen → recoger sin nombre).
        if _es_vocab_tangible(escena, modo, tipo_vocabulario):
            examen = escena.rol_escena == "examen"
            extra = P.PROGRAMADOR_P1_VOCAB_EXAMEN_EXTRA if examen else P.PROGRAMADOR_P1_VOCAB_EXPOSICION_EXTRA
            p1_system = p1_system + "\n\n" + extra.format(
                idioma_objetivo=idioma_objetivo or "en",
                vocab_lista=_formatear_vocab_lista(escena, examen=examen),
            )

    messages = [SystemMessage(content=p1_system), HumanMessage(content=user_prompt)]

    if errores_previos:
        fb = "\n".join(f"- {e}" for e in errores_previos)
        messages.append(HumanMessage(content=(
            f"La pasada anterior produjo errores:\n{fb}\n\n"
            "Corrige y devuelve SOLO el JSON válido."
        )))

    respuesta = _invoke_con_backoff(llm, messages)
    messages.append(respuesta)

    datos = _reparar_dispara(json.loads(_limpiar_json(respuesta.content)))
    return datos, messages


# ─── Pasada 2: diálogos ───────────────────────────────────────────────────────

def _formatear_items_recogibles(objetos_p1: list[dict]) -> str:
    """Lista de objetos 'recoger' que el jugador puede llevar en el inventario."""
    items = [o for o in objetos_p1 if o.get("interaccion", {}).get("tipo") == "recoger"]
    if not items:
        return ""
    lineas = ["OBJETOS RECOGIBLES EN ESTA ESCENA (el jugador puede llevarlos en el inventario):"]
    for o in items:
        inter = o.get("interaccion", {})
        titulo = inter.get("titulo") or o["id_nodo"]
        lineas.append(f"  · {o['id_nodo']} — '{titulo}'")
    lineas.append(
        "\nSi un personaje conoce alguno de estos objetos, añade 'dialogos_con_item':\n"
        "  · consume: false → el personaje reacciona a ver el objeto, pero el jugador lo conserva.\n"
        "  · consume: true  → el jugador ENTREGA el objeto al personaje (desaparece del inventario).\n"
        "    Usa consume: true cuando la narrativa implique dar o entregar el objeto."
    )
    return "\n".join(lineas)


def _pasada_dialogos(
    scenegraph: SceneGraph,
    escena: Escena,
    backbone: list[dict],
    fases_p1: list,
    llm,
    P,
    objetos_p1: list[dict] | None = None,
    errores_previos: list[str] | None = None,
    modo: str = "narrativo",
    tipo_vocabulario: str | None = None,
    idioma_objetivo: str | None = None,
    vocabulario=None,
) -> dict:
    fases_resumen = [
        {
            "fase":        f["fase"] if isinstance(f, dict) else f.fase,
            "id_evento":   f["id_evento"] if isinstance(f, dict) else f.id_evento,
            "descripcion": next(
                (b["descripcion"] for b in backbone
                 if b["id_evento"] == (f["id_evento"] if isinstance(f, dict) else f.id_evento)),
                ""
            ),
        }
        for f in fases_p1
    ]

    items_brief = _formatear_items_recogibles(objetos_p1 or []) if modo != "educativo" else ""

    p2_system = P.PROGRAMADOR_P2_EDUCATIVO_SYSTEM if modo == "educativo" else P.PROGRAMADOR_P2_SYSTEM
    p2_user_tmpl = P.PROGRAMADOR_P2_EDUCATIVO_USER if modo == "educativo" else P.PROGRAMADOR_P2_USER
    if modo == "educativo":
        p2_system = p2_system + "\n\n" + P.RESALTADO_EDUCATIVO  # resaltar datos clave en diálogos
        # Vocabulario tangible: diálogos de exposición (mención bilingüe) o de examen
        # (petición bilingüe + dialogos_con_item de entrega/felicitación).
        if _es_vocab_tangible(escena, modo, tipo_vocabulario):
            examen = escena.rol_escena == "examen"
            extra = P.PROGRAMADOR_P2_VOCAB_EXAMEN_EXTRA if examen else P.PROGRAMADOR_P2_VOCAB_EXPOSICION_EXTRA
            p2_system = p2_system + "\n\n" + extra.format(
                idioma_objetivo=idioma_objetivo or "en",
                vocab_lista=_formatear_vocab_lista(escena, examen=examen),
            )
        # Vocabulario conversacional (Tipo B): usa un prompt DEDICADO (no el de figuras históricas,
        # que confundía al modelo). Base limpia de conversación + extra por rol.
        if _es_vocab_conversacional(escena, modo, tipo_vocabulario):
            examen = escena.rol_escena == "examen"
            extra = P.PROGRAMADOR_P2_CONVERSACIONAL_EXAMEN_EXTRA if examen else P.PROGRAMADOR_P2_CONVERSACIONAL_EXPOSICION_EXTRA
            p2_system = P.PROGRAMADOR_P2_CONVERSACIONAL_SYSTEM + "\n\n" + extra.format(
                idioma_objetivo=idioma_objetivo or "en",
                vocab_lista=_formatear_vocabulario_conversacional(vocabulario),
            )
            p2_user_tmpl = P.PROGRAMADOR_P2_CONVERSACIONAL_USER

    humanos = set(scenegraph.registro_personajes or {})
    user_prompt = p2_user_tmpl.format(
        id_escena=scenegraph.id_escena,
        atmosfera=escena.atmosfera or "neutra",
        fases_json=json.dumps(fases_resumen, indent=2, ensure_ascii=False),
        personajes_brief=_formatear_personajes_brief(escena, backbone, humanos),
        items_brief=items_brief,
    )

    messages = [SystemMessage(content=p2_system), HumanMessage(content=user_prompt)]

    if errores_previos:
        fb = "\n".join(f"- {e}" for e in errores_previos)
        messages.append(HumanMessage(content=(
            f"La pasada anterior produjo errores:\n{fb}\n\n"
            "Corrige y devuelve SOLO el JSON válido."
        )))

    # Reintento dirigido: validamos los diálogos nada más generarlos y, si hay huecos
    # que la recuperación fiel no puede rellenar, pedimos al modelo SOLO esa corrección
    # (sin re-ejecutar P1/P3). El feedback es legible, no el volcado de Pydantic.
    _MAX_P2 = 2
    datos = {}
    for intento in range(_MAX_P2 + 1):
        respuesta = _invoke_con_backoff(llm, messages)
        messages.append(respuesta)
        datos = _reparar_dispara(json.loads(_limpiar_json(respuesta.content)))
        errs = _validar_dialogos_p2(datos)
        if not errs or intento == _MAX_P2:
            if errs:
                logger.warning(f"[Programador P2] persisten {len(errs)} avisos tras reintentos: {errs[:3]}")
            break
        fb = "\n".join(f"- {e}" for e in errs[:8])
        logger.info(f"[Programador P2] reintento {intento + 1}: {len(errs)} diálogos a corregir")
        messages.append(HumanMessage(content=(
            "Hay diálogos con problemas de ESTRUCTURA que debes corregir:\n" + fb +
            "\n\nRecordatorio de la forma EXACTA: cada diálogo lleva una lista 'puntos'; "
            "cada punto lleva 'frases' (exactamente 1 frase) y 'opciones' (0, o 2 con "
            "'etiqueta' Y 'respuesta' cada una). Devuelve SOLO el JSON corregido y completo."
        )))
    return datos, messages


# ─── Pasada 3: decorados ambientales (opcional) ───────────────────────────────

def _pasada_decorados(
    scenegraph: SceneGraph,
    escena: Escena,
    ids_ya_en_manifest: set[str],
    llm,
    P,
) -> list[dict]:
    """
    P3 opcional: el LLM decide qué decorados (no cubiertos por P1) merecen una
    interacción ambiental. Retorna lista de dicts compatibles con ObjetoManifest.
    Si no hay candidatos o el LLM devuelve [], no se genera ningún LLM call.
    Los errores se capturan silenciosamente — P3 es aditivo, nunca bloquea.
    """
    # Zona jugable para candidatos P3: anillo cercano al jugador. El relleno de
    # ambiente se coloca a partir de ~0.30×radio (fuera del límite estricto del
    # jugador), así que usamos un radio generoso (~0.55×radio) que capta los
    # decorados jugables y el anillo de ambiente más próximo, excluyendo el fondo
    # medio/lejano que el jugador nunca ve de cerca.
    umbral_zona = scenegraph.radio_escena * 0.55

    def _en_zona_jugable(n) -> bool:
        return (n.posicion.x ** 2 + n.posicion.z ** 2) ** 0.5 <= umbral_zona

    # Candidatos: decorados + nodos de relleno de ambiente cercanos. Los 'ambiente'
    # sin gltf_url no se renderizan (scene_loader los omite sin billboard), así que
    # se excluyen: animar algo invisible no tiene sentido.
    ids_validos_p3 = {
        n.id for n in scenegraph.nodos
        if n.id not in ids_ya_en_manifest and _en_zona_jugable(n) and (
            n.tipo == "decorado" or (n.tipo == "ambiente" and n.gltf_url)
        )
    }
    candidatos = [
        {
            "id":      n.id,
            "nombre":  n.nombre,
            "keyword": n.keyword_busqueda or "",
        }
        for n in scenegraph.nodos
        if n.id in ids_validos_p3
    ]

    if not candidatos:
        return []

    user_prompt = P.PROGRAMADOR_P3_USER.format(
        id_escena=scenegraph.id_escena,
        entorno=escena.entorno,
        atmosfera=escena.atmosfera,
        decorados_json=json.dumps(candidatos, indent=2, ensure_ascii=False),
    )

    try:
        messages  = [SystemMessage(content=P.PROGRAMADOR_P3_SYSTEM), HumanMessage(content=user_prompt)]
        respuesta = _invoke_con_backoff(llm, messages)
        datos     = json.loads(_limpiar_json(respuesta.content))

        # Garantías de seguridad: solo decorados válidos del SceneGraph, fase 0, sin dispara
        resultado = []
        for entry in datos:
            nid = entry.get("id_nodo", "")
            if nid not in ids_validos_p3:
                continue
            entry["fase_aparicion"] = 0
            entry["dispara"]        = None
            resultado.append(entry)

        logger.info(f"[Programador P3] '{scenegraph.id_escena}': {len(resultado)} decorados animados")
        return resultado

    except Exception as e:
        logger.warning(f"[Programador P3] Omitido por error: {e}")
        return []


# ─── Saneado defensivo de la salida del LLM ──────────────────────────────────
# Con modelos pequeños, el P2 (diálogos) y las acciones de P1 a veces llegan con
# campos requeridos ausentes (omiten 'puntos', 'respuesta', 'tecla'...). En vez de
# tumbar todo el manifiesto (y, tras 3 reintentos, el pipeline entero), reparamos o
# descartamos la subestructura inválida — degradación elegante como en Constructor/Músico.

_TECLAS_ACCION = {"KeyQ", "KeyR", "KeyT", "KeyG", "KeyX", "KeyZ"}


# Claves alternativas que los modelos pequeños usan a veces en vez de las del schema.
# Solo se recupera contenido REAL que el modelo escribió — nunca se inventa nada.
_ALT_ETIQUETA  = ("etiqueta", "opcion", "pregunta")
_ALT_RESPUESTA = ("respuesta", "replica", "respuesta_personaje", "texto_respuesta")


def _primer_str(d, claves):
    for k in claves:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _sanear_opcion(o):
    if not isinstance(o, dict):
        return None
    et   = _primer_str(o, _ALT_ETIQUETA)
    resp = _primer_str(o, _ALT_RESPUESTA)
    if et and resp:
        op = {"etiqueta": et, "respuesta": resp}
        if o.get("correcta") is True:   # examen conversacional: marca de respuesta correcta
            op["correcta"] = True
        return op
    return None


def _sanear_punto(pt):
    if isinstance(pt, str):           # el modelo escribió el punto como string suelto
        pt = {"frases": [pt]}
    if not isinstance(pt, dict):
        return None
    frases = pt.get("frases")
    if isinstance(frases, str):
        frases = [frases]
    if not isinstance(frases, list):
        return None
    frases = [f for f in frases if isinstance(f, str) and f.strip()]
    if not frases:
        return None
    ops = pt.get("opciones") or []
    ops_ok = [x for x in (_sanear_opcion(o) for o in ops) if x] if isinstance(ops, list) else []
    # Diseño: monólogo (0 opciones) o disyuntiva narrativa (2). El examen conversacional usa
    # 3-4 opciones (quiz), así que conservamos hasta 4. Una sola opción suelta → monólogo.
    return {"frases": [frases[0].strip()], "opciones": ops_ok[:4] if len(ops_ok) >= 2 else []}


def _sanear_puntos(puntos, maximo=3):
    if not isinstance(puntos, list):
        return []
    return [x for x in (_sanear_punto(p) for p in puntos) if x][:maximo]


def _sanear_dialogos(dialogos):
    out = []
    if not isinstance(dialogos, list):
        return out
    for d in dialogos:
        if not isinstance(d, dict):
            continue
        puntos_raw = d.get("puntos")
        # Recuperación de aplanamiento: el modelo metió 'frases'/'opciones' directamente
        # en el diálogo, saltándose el envoltorio 'puntos'. Re-envolvemos SU contenido.
        if not isinstance(puntos_raw, list) or not puntos_raw:
            if "frases" in d or "opciones" in d:
                puntos_raw = [{"frases": d.get("frases"), "opciones": d.get("opciones")}]
            else:
                continue
        puntos = _sanear_puntos(puntos_raw, 3)
        if not puntos:
            continue
        try:
            fase = int(d.get("fase", 0))
        except (TypeError, ValueError):
            fase = 0
        nd = {"fase": fase, "puntos": puntos}
        anim = d.get("animacion")
        if isinstance(anim, str) and anim.strip():
            nd["animacion"] = anim.strip()
        # Preservar la pista (examen de vocabulario): un PuntoDialogo opcional que el
        # runtime muestra al entregar el objeto equivocado.
        pista_raw = d.get("pista")
        if isinstance(pista_raw, dict):
            pista_saneada = _sanear_puntos([pista_raw], 1)
            if pista_saneada:
                nd["pista"] = pista_saneada[0]
        out.append(nd)
    return out


def _validar_dialogos_p2(datos):
    """
    Detecta problemas que la recuperación fiel NO puede arreglar (contenido genuinamente
    ausente) y devuelve mensajes legibles para que el modelo los corrija en el reintento.
    Lista vacía = los diálogos son recuperables a una estructura válida.
    """
    errs = []
    for p in datos.get("personajes", []) if isinstance(datos, dict) else []:
        pid = p.get("id_nodo", "?")
        saneados = _sanear_dialogos(p.get("dialogos"))
        if not saneados:
            errs.append(f"'{pid}': no tiene ningún diálogo válido. Cada personaje necesita al "
                        f"menos un diálogo con 'puntos': [{{'frases': ['...'], 'opciones': []}}].")
            continue
        # Opciones presentes pero incompletas (se perdieron al sanear → faltaba 'respuesta')
        for d in (p.get("dialogos") or []):
            for pt in (_extraer_puntos_raw(d)):
                ops = pt.get("opciones") if isinstance(pt, dict) else None
                if isinstance(ops, list) and ops:
                    if sum(1 for o in ops if _sanear_opcion(o)) < 2:
                        errs.append(f"'{pid}': una opción está incompleta. CADA opción necesita "
                                    f"'etiqueta' Y 'respuesta' (ambas), y deben ir de 2 en 2.")
                        break
    return errs


def _extraer_puntos_raw(d):
    if not isinstance(d, dict):
        return []
    pts = d.get("puntos")
    if isinstance(pts, list) and pts:
        return [p for p in pts if isinstance(p, dict)]
    if "frases" in d or "opciones" in d:   # aplanado
        return [d]
    return []


def _sanear_dialogos_con_item(lista):
    out = []
    if not isinstance(lista, list):
        return out
    for d in lista:
        if not isinstance(d, dict):
            continue
        req = d.get("requiere_objeto")
        puntos = _sanear_puntos(d.get("puntos"), 2)
        if not (isinstance(req, str) and req.strip()) or not puntos:
            continue
        out.append({"requiere_objeto": req.strip(),
                    "consume": bool(d.get("consume", False)),
                    "puntos": puntos})
    return out


def _sanear_acciones_personaje(acciones):
    out = []
    if not isinstance(acciones, list):
        return out
    for a in acciones:
        if not isinstance(a, dict):
            continue
        if a.get("tecla") not in _TECLAS_ACCION:
            continue
        if not (isinstance(a.get("etiqueta"), str) and a["etiqueta"].strip()):
            continue
        a.setdefault("narrativa", False)  # requerido por el schema; default seguro
        out.append(a)
    return out[:2]


# ─── Punto de entrada público ─────────────────────────────────────────────────

def ejecutar_programador(
    scenegraph: SceneGraph,
    escena: Escena,
    provider: str = "mercury",
    mensajes_previos: list | None = None,
    errores_previos: list[str] | None = None,
    modo: str = "narrativo",
    idioma: str = "es",
    tipo_vocabulario: str | None = None,
    idioma_objetivo: str | None = None,
    vocabulario=None,
) -> tuple[SalidaProgramador, list]:
    """
    Ejecuta las tres pasadas del Programador para generar el manifest de interacciones.
    P3 (decorados ambientales) es opcional y no bloquea si falla.

    Returns:
        (SalidaProgramador, mensajes_combinados)
    """
    llm = get_llm(provider)
    P = get_prompts(idioma)

    # Backbone determinista
    ids_disponibles = {
        n.id for n in scenegraph.nodos if n.tipo not in TIPOS_EXCLUIDOS
    }
    backbone = _construir_backbone(escena, ids_disponibles)

    try:
        # Pasada 1 — estructura
        datos_p1, msgs_p1 = _pasada_estructural(
            scenegraph, escena, backbone, llm, P,
            errores_previos=errores_previos,
            modo=modo,
            tipo_vocabulario=tipo_vocabulario,
            idioma_objetivo=idioma_objetivo,
        )

        # Condición de avance y guías: ambas deterministas desde el Organizador.
        # guías = condicion_avance = TODOS los participantes del evento (objetos +
        # personajes), incluso si un objeto ya apareció en una fase anterior. La
        # condición es fiel al evento; quien evita re-exigir lo ya hecho es el RUNTIME:
        # interactions.js NO resetea nodosCompletados al avanzar de fase, así que un
        # objeto ya completado entra a la nueva fase pre-marcado (el tracker lo muestra
        # hecho y su aura no se enciende). Para los 'activar', nodosCompletados refleja
        # su estado on/off real, de modo que solo cuentan como hechos si siguen activos.
        backbone_by_evento = {b["id_evento"]: b for b in backbone}
        for fm in datos_p1.get("fases", []):
            b = backbone_by_evento.get(fm.get("id_evento", ""), {})
            todos = b.get("todos", [])
            nodos_cond = [x for x in todos if not x.startswith("personaje_")]
            pers_cond  = [x for x in todos if x.startswith("personaje_")]
            fm["condicion_avance"] = {"nodos": nodos_cond, "personajes": pers_cond, "zonas": []}
            fm["guias"]            = todos

        # ── Repair: detectar deadlocks usar_con ──────────────────────────────
        # Un objeto usar_con no puede estar en condicion_avance de una fase
        # anterior a aquella donde aparece su requiere_objeto.
        # Si lo está, lo movemos a la primera fase donde ambos están disponibles.
        objetos_map = {o["id_nodo"]: o for o in datos_p1.get("objetos", [])}
        fases_list  = datos_p1.get("fases", [])

        # ── Repair: el requiere_objeto de un usar_con DEBE ser 'recoger' ─────
        # Si un objeto es exigido por un usar_con pero no es recogible, el jugador
        # nunca podría tenerlo en el inventario para usarlo → la interacción queda
        # rota (etiqueta "examinar" sin opción de guardar). Forzamos 'recoger',
        # conservando título y descripción. Si el requerido es de otra escena
        # (no está en este mapa) se ignora: ya se recogió antes.
        for _o in datos_p1.get("objetos", []):
            _inter = _o.get("interaccion") or {}   # 'or {}' tolera interaccion: null del LLM
            if _inter.get("tipo") != "usar_con":
                continue
            _tgt = objetos_map.get(_inter.get("requiere_objeto", ""))
            if _tgt is None:
                continue
            _ti = _tgt.get("interaccion") or {}
            if _ti.get("tipo") != "recoger":
                logger.warning(
                    f"[Programador/Repair] '{_tgt['id_nodo']}' es requerido por usar_con "
                    f"'{_o['id_nodo']}' pero era '{_ti.get('tipo')}' — convertido a 'recoger'."
                )
                _titulo = _ti.get("titulo") or _tgt["id_nodo"].replace("objeto_", "").replace("_", " ").capitalize()
                _tgt["interaccion"] = {
                    "tipo": "recoger",
                    "titulo": _titulo,
                    "descripcion": _ti.get("descripcion"),
                }

        # Calcular fase mínima de aparición de cada nodo
        def _fase_min(nodo_id: str) -> int:
            obj = objetos_map.get(nodo_id)
            return obj.get("fase_aparicion", 0) if obj else 0

        for i, fm in enumerate(fases_list):
            ca = fm["condicion_avance"]
            nodos_ok, nodos_mover = [], []
            for nid in ca["nodos"]:
                obj = objetos_map.get(nid)
                if not obj:
                    nodos_ok.append(nid)
                    continue
                inter = obj.get("interaccion", {})
                if inter.get("tipo") == "usar_con":
                    req = inter.get("requiere_objeto", "")
                    # Si el requiere_objeto no está disponible en esta fase o antes, mover
                    if _fase_min(req) > fm["fase"]:
                        nodos_mover.append((nid, req))
                        logger.warning(
                            f"[Programador/Repair] '{nid}' (usar_con '{req}') en fase {fm['fase']} "
                            f"pero '{req}' no aparece hasta fase {_fase_min(req)} — moviendo."
                        )
                    else:
                        nodos_ok.append(nid)
                else:
                    nodos_ok.append(nid)

            if nodos_mover:
                ca["nodos"] = nodos_ok
                fm["guias"] = [x for x in fm["guias"] if x not in [n for n, _ in nodos_mover]]
                # Mover a la primera fase posterior donde el requiere_objeto ya está disponible
                for nid, req in nodos_mover:
                    fase_target = _fase_min(req)
                    colocado = False
                    for fm2 in fases_list[i + 1:]:
                        if fm2["fase"] >= fase_target:
                            fm2["condicion_avance"]["nodos"].append(nid)
                            if nid not in fm2["guias"]:
                                fm2["guias"].append(nid)
                            colocado = True
                            logger.info(
                                f"[Programador/Repair] '{nid}' reubicado en fase {fm2['fase']}."
                            )
                            break
                    if not colocado:
                        # Sin fase posterior disponible: añadir a la última fase
                        last = fases_list[-1]
                        last["condicion_avance"]["nodos"].append(nid)
                        if nid not in last["guias"]:
                            last["guias"].append(nid)

        logger.info(
            f"[Programador P1] '{scenegraph.id_escena}': "
            f"{len(datos_p1.get('fases', []))} fases, "
            f"{len(datos_p1.get('objetos', []))} objetos, "
            f"{len(datos_p1.get('personajes', []))} personajes (acciones)"
        )

        # Pasada 2 — diálogos
        datos_p2, msgs_p2 = _pasada_dialogos(
            scenegraph, escena, backbone, datos_p1.get("fases", []), llm, P,
            objetos_p1=datos_p1.get("objetos", []),
            errores_previos=errores_previos,
            modo=modo,
            tipo_vocabulario=tipo_vocabulario,
            idioma_objetivo=idioma_objetivo,
            vocabulario=vocabulario,
        )
        logger.info(
            f"[Programador P2] '{scenegraph.id_escena}': "
            f"{len(datos_p2.get('personajes', []))} personajes"
        )

        # Pasada 3 — decorados ambientales (opcional, no bloquea)
        ids_en_manifest = {o["id_nodo"] for o in datos_p1.get("objetos", [])}
        objetos_p3 = _pasada_decorados(scenegraph, escena, ids_en_manifest, llm, P)
        objetos_final = datos_p1.get("objetos", []) + objetos_p3

        # Fallback: añadir determinísticamente cualquier personaje del SceneGraph
        # que el LLM haya omitido (ocurre cuando no participa en ningún evento).
        personajes_p2_ids = {p["id_nodo"] for p in datos_p2.get("personajes", [])}
        personajes_dict_local = {p.id: p for p in escena.personajes}
        personajes_extra = []
        for nodo in scenegraph.nodos:
            if nodo.tipo != "personaje" or nodo.id in personajes_p2_ids:
                continue
            p = personajes_dict_local.get(nodo.id)
            fisica = (p.fisica or nodo.nombre)[:120] if p else nodo.nombre
            personajes_extra.append({
                "id_nodo":        nodo.id,
                "fase_aparicion": 0,
                "dialogos": [{"fase": 0, "animacion": None, "puntos": [{"frases": [fisica], "opciones": []}]}],
                "dispara":        None,
            })
            logger.warning(f"[Programador] '{nodo.id}' omitido por el LLM — añadido con diálogo por defecto.")

        # Mergear acciones/dispara de P1 en los personajes de P2.
        # P1 decide la estructura (acciones, dispara); P2 decide los diálogos.
        # acciones siempre viene de P1 — P2 no las genera y si las incluye por error se ignoran.
        p1_pers = {p["id_nodo"]: p for p in datos_p1.get("personajes", [])}
        personajes_merged = []
        for p2_pers in datos_p2.get("personajes", []) + personajes_extra:
            p1 = p1_pers.get(p2_pers["id_nodo"], {})
            merged = {**p2_pers}
            merged["acciones"] = p1.get("acciones", [])
            if merged.get("dispara") is None and p1.get("dispara"):
                merged["dispara"] = p1["dispara"]
            personajes_merged.append(merged)

        # Vocabulario tangible (examen): asegura el dialogos_con_item de entrega/felicitación
        # del guía de forma determinista (el LLM lo omite a menudo).
        if _es_vocab_tangible(escena, modo, tipo_vocabulario) and escena.rol_escena == "examen":
            _rellenar_dialogos_con_item_vocab(personajes_merged, escena, idioma)

        # ── Recuperación fiel: re-anidar/limpiar lo que el modelo escribió mal ──
        # NO inventa contenido: re-envuelve puntos aplanados, mapea claves alternativas
        # y descarta solo subestructuras genuinamente vacías. El reintento dirigido de
        # P2 ya intentó que el modelo rellenara los huecos reales antes de llegar aquí.
        for p in personajes_merged:
            p["dialogos"] = _sanear_dialogos(p.get("dialogos"))
            if p.get("dialogos_con_item"):
                p["dialogos_con_item"] = _sanear_dialogos_con_item(p["dialogos_con_item"])
            p["acciones"] = _sanear_acciones_personaje(p.get("acciones"))

        # ── Repair: fase_aparicion ≤ primera fase donde el nodo es requerido ──
        # interactions.js bloquea la interacción si fase_aparicion > faseActual;
        # un participante de condicion_avance con fase_aparicion posterior a su
        # fase sería ininteractuable → deadlock. Se clampea sobre las fases ya
        # reparadas (post-reubicación usar_con).
        primera_fase_req: dict[str, int] = {}
        for fm in datos_p1.get("fases", []):
            ca = fm.get("condicion_avance", {})
            for nid in ca.get("nodos", []) + ca.get("personajes", []):
                f = fm.get("fase", 0)
                if nid not in primera_fase_req or f < primera_fase_req[nid]:
                    primera_fase_req[nid] = f

        for item in objetos_final + personajes_merged:
            nid   = item.get("id_nodo", "")
            f_req = primera_fase_req.get(nid)
            if f_req is not None and item.get("fase_aparicion", 0) > f_req:
                logger.warning(
                    f"[Programador/Repair] '{nid}': fase_aparicion="
                    f"{item.get('fase_aparicion')} pero es requerido en fase {f_req} "
                    f"— clampeado para evitar deadlock."
                )
                item["fase_aparicion"] = f_req

        # ── Repair: descartar entradas de manifest que referencian nodos
        # inexistentes en el SceneGraph. El LLM a veces alucina una interacción
        # con un objeto narrativamente prominente que NO es nodo de esta escena
        # (p.ej. "objeto_habichuelas_magicas" cuando la prosa de un evento
        # menciona el tallo de habichuelas, pero las habichuelas no aparecen
        # como nodo aquí). El reintento dirigido no lo disuade (el objeto es
        # demasiado prominente en el texto), así que sin este filtro el validador
        # falla idéntico 3 veces y tumba TODO el pipeline. Filosofía igual que
        # Constructor/Músico: degradar la escena, nunca abortar la generación.
        ids_todos = {n.id for n in scenegraph.nodos}

        def _filtrar_inexistentes(entradas: list[dict], etiqueta: str) -> list[dict]:
            limpias = []
            for it in entradas:
                nid = it.get("id_nodo", "")
                if nid not in ids_disponibles:
                    logger.warning(
                        f"[Programador/Repair] {etiqueta} '{nid}' no existe en el "
                        f"SceneGraph de '{scenegraph.id_escena}' — descartado "
                        f"(alucinación del LLM)."
                    )
                    continue
                disp = it.get("dispara")
                if disp and disp.get("id_nodo") not in ids_todos:
                    logger.warning(
                        f"[Programador/Repair] {etiqueta} '{nid}'.dispara apunta a "
                        f"'{disp.get('id_nodo')}' (inexistente) — anulado."
                    )
                    it["dispara"] = None
                limpias.append(it)
            return limpias

        objetos_final     = _filtrar_inexistentes(objetos_final, "objeto")
        personajes_merged = _filtrar_inexistentes(personajes_merged, "personaje")

        # ── Examen de vocabulario tangible: ajustes para el modo examen-por-entrega ──
        # El viewer (con examen_vocabulario=true) gatea el avance por ENTREGA al guía, no
        # por recoger. Aquí: (1) todos los objetos del vocabulario son interactuables desde
        # el inicio (coger todo libremente) — anula el clamp de fase de arriba; (2) los
        # objetos NO llevan aura (no deben delatar la respuesta): las guías quedan solo en
        # el guía. La mecánica de entrega/fallos/recarga la implementa interactions.js.
        es_examen_vocab = (
            _es_vocab_tangible(escena, modo, tipo_vocabulario)
            and escena.rol_escena == "examen"
        )
        if es_examen_vocab:
            ids_vocab = {o.id for o in escena.objetos}
            # Etiqueta visible del objeto = su nombre en el idioma de la UI (p.ej. "naranja").
            # El nombre en el idioma objetivo NO se muestra: es la respuesta que pide el guía.
            nombre_ui = {o.id: o.nombre for o in escena.objetos}
            for it in objetos_final:
                if it.get("id_nodo") in ids_vocab:
                    it["fase_aparicion"] = 0
                    inter = it.get("interaccion") or {}
                    if inter.get("tipo") == "recoger" and nombre_ui.get(it["id_nodo"]):
                        inter["titulo"] = nombre_ui[it["id_nodo"]]
                        it["interaccion"] = inter
            for fm in datos_p1.get("fases", []):
                fm["guias"] = [g for g in fm.get("guias", []) if g.startswith("personaje_")]
            # En el examen, el diálogo del guía es SOLO la petición: un único punto por fase.
            # Los puntos secundarios (que rotan al volver a hablar) suelen dar pistas o nombrar
            # el animal → revelarían la respuesta. Los recortamos determinísticamente.
            ids_personajes = {p.id for p in escena.personajes}
            for pm in personajes_merged:
                if pm.get("id_nodo") in ids_personajes:
                    for d in pm.get("dialogos", []):
                        if d.get("puntos"):
                            d["puntos"] = d["puntos"][:1]

        # ── Examen de vocabulario CONVERSACIONAL (Tipo B): preguntas con opciones ──────
        # El guía hace una pregunta por fase; el viewer avanza con la opción correcta.
        # Garantizamos UNA sola opción correcta por pregunta (red de seguridad determinista).
        es_examen_conversacional = (
            _es_vocab_conversacional(escena, modo, tipo_vocabulario)
            and escena.rol_escena == "examen"
        )
        if es_examen_conversacional:
            ids_personajes = {p.id for p in escena.personajes}
            for pm in personajes_merged:
                if pm.get("id_nodo") not in ids_personajes:
                    continue
                for d in pm.get("dialogos", []):
                    for pt in (d.get("puntos") or []):
                        if pt.get("opciones"):
                            _reparar_una_correcta_opciones(pt["opciones"])
                            random.shuffle(pt["opciones"])  # la correcta no siempre primera

        # Combinar en SalidaProgramador
        salida = SalidaProgramador.model_validate({
            "id_escena":        scenegraph.id_escena,
            "fases":            datos_p1.get("fases", []),
            "personajes":       personajes_merged,
            "objetos":          objetos_final,
            "zonas_narrativas": datos_p1.get("zonas_narrativas", []),
            "examen_vocabulario": es_examen_vocab,
            "examen_opciones":  es_examen_conversacional,
        })

        mensajes_combinados = msgs_p1 + msgs_p2
        return salida, mensajes_combinados

    except json.JSONDecodeError as e:
        raise AgentError(f"JSON inválido: {e}", mensajes_previos or []) from e
    except Exception as e:
        error_str = str(e)
        if any(k in error_str for k in ["memory", "status code: 5", "Connection refused"]):
            raise RuntimeError(f"[Programador] Error irrecuperable: {error_str}") from e
        raise AgentError(f"Schema inválido: {e}", mensajes_previos or []) from e
