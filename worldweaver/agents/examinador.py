"""
Agente Examinador — MODO EDUCATIVO.
Genera un cuestionario tipo test de 8 preguntas sobre el temario recorrido.
"""

import json
import random
import re
import logging

from langchain_core.messages import SystemMessage, HumanMessage

from config.prompts import get_prompts
from config.llm import get_llm
from pipeline.errors import AgentError
from pipeline import metricas
from schemas.quiz import SalidaExaminador
from schemas.escenas import SalidaOrganizador

logger = logging.getLogger(__name__)

_LETRAS = ["a", "b", "c", "d"]

# Prefijo del tipo "La respuesta es b porque " / "The answer is (b) because " que
# el LLM a veces incrusta en la explicación. Tras barajar las opciones la letra
# deja de coincidir con la posición real de la correcta, así que lo eliminamos.
_RE_PREFIJO_LETRA = re.compile(
    r"^\s*(?:la\s+respuesta(?:\s+correcta)?\s+es(?:\s+la)?"
    r"|the\s+(?:correct\s+)?answer\s+is(?:\s+option)?)\s+"
    r"\(?[a-d]\)?[\.\):,]?\s*(?:porque|because)?\s*",
    re.IGNORECASE,
)


def _limpiar_json(texto: str) -> str:
    texto = re.sub(r"```(?:json)?\s*", "", texto)
    return texto.replace("```", "").strip()


def _limpiar_explicacion(texto: str) -> str:
    """Quita una referencia de letra al inicio de la explicación (p.ej.
    "La respuesta es b porque ...") y recapitaliza. Si tras quitarla no
    queda contenido, devuelve el texto original sin tocar."""
    nuevo = _RE_PREFIJO_LETRA.sub("", texto).strip()
    if not nuevo:
        return texto
    return nuevo[0].upper() + nuevo[1:]


def _preguntas_mal_marcadas(salida: SalidaExaminador) -> list[str]:
    """Devuelve descripciones de las preguntas que NO tienen exactamente una opción
    marcada como correcta (0 o >1). Lista vacía = todas correctas."""
    malas = []
    for q in salida.preguntas:
        n = sum(1 for o in q.opciones if o.correcta)
        if n != 1:
            malas.append(
                f"Pregunta {q.numero} ('{q.pregunta[:50]}…'): {n} opciones marcadas como correctas "
                "(debe haber EXACTAMENTE 1)."
            )
    return malas


def _reparar_una_correcta(salida: SalidaExaminador) -> None:
    """Red de seguridad determinista: garantiza UNA sola opción correcta por pregunta.
    Si hay varias marcadas, conserva la primera; si no hay ninguna, marca la primera
    (último recurso, muy raro tras los reintentos)."""
    for q in salida.preguntas:
        idx = [i for i, o in enumerate(q.opciones) if o.correcta]
        if len(idx) == 1:
            continue
        for o in q.opciones:
            o.correcta = False
        if q.opciones:
            q.opciones[idx[0] if idx else 0].correcta = True
        logger.warning(f"[Examinador] Pregunta {q.numero}: marcado corregido ({len(idx)}→1 correcta).")


def _aleatorizar_posiciones(salida: SalidaExaminador) -> None:
    """El LLM suele dejar la respuesta correcta en una posición predecible
    (p.ej. siempre "b"). Baraja el orden de las opciones en cada pregunta
    para que la posición de la opción correcta sea uniforme, sin depender
    del modelo. Además limpia la explicación de cualquier letra incrustada,
    que tras barajar ya no coincidiría con la opción correcta."""
    for pregunta in salida.preguntas:
        random.shuffle(pregunta.opciones)
        for letra, opcion in zip(_LETRAS, pregunta.opciones):
            opcion.letra = letra
        pregunta.explicacion = _limpiar_explicacion(pregunta.explicacion)


def ejecutar_examinador(
    salida_organizador: SalidaOrganizador,
    texto_original: str,
    nombre_mundo: str,
    provider: str = "mercury",
    idioma: str = "es",
    subtipo: str | None = None,
    idioma_objetivo: str | None = None,
) -> SalidaExaminador:
    """
    Genera un cuestionario tipo test de 8 preguntas sobre el temario.

    En subtipo 'vocabulario' usa prompts específicos (traducción / uso en contexto /
    identificación) en lugar de los de comprensión histórica.

    Raises:
        AgentError: Si el LLM no devuelve JSON válido.
    """
    llm = get_llm(provider)
    P = get_prompts(idioma)

    # El subtipo puede venir explícito o leerse de la salida del Organizador.
    subtipo = subtipo or salida_organizador.subtipo_educativo
    idioma_objetivo = idioma_objetivo or salida_organizador.idioma_objetivo or "en"
    es_vocab = subtipo == "vocabulario"

    escenas_resumen = []
    for esc in salida_organizador.escenas:
        personajes = ", ".join(p.nombre for p in esc.personajes) if esc.personajes else "ninguno"
        eventos = "; ".join(e.descripcion for e in esc.eventos) if esc.eventos else "ninguno"
        # En vocabulario, lo que importa es el par de palabras: lo añadimos al resumen.
        if es_vocab:
            # Par bilingüe COMPLETO (UI = objetivo). Tangible: lo llevan los objetos
            # (nombre/nombre_objetivo). Conversacional: no hay objetos → se toma de
            # salida_organizador.vocabulario (pares ui/objetivo).
            pares = [f"{o.nombre} = {o.nombre_objetivo}"
                     for o in esc.objetos if (o.nombre_objetivo or "").strip()]
            if not pares and getattr(salida_organizador, "vocabulario", None):
                pares = [f"{p.ui} = {p.objetivo}"
                         for p in salida_organizador.vocabulario if p.ui and p.objetivo]
            vocab = "; ".join(pares) or "ninguno"
            escenas_resumen.append(
                f"- {esc.titulo} ({esc.rol_escena or 'escena'}): {esc.atmosfera}\n"
                f"  Vocabulario (español = idioma objetivo): {vocab}"
            )
        else:
            escenas_resumen.append(
                f"- {esc.titulo}: {esc.atmosfera}\n"
                f"  Personajes: {personajes}\n"
                f"  Eventos clave: {eventos}"
            )

    texto_truncado = texto_original[:3000] if len(texto_original) > 3000 else texto_original

    if es_vocab:
        messages = [
            SystemMessage(content=P.EXAMINADOR_VOCABULARIO_SYSTEM),
            HumanMessage(content=P.EXAMINADOR_VOCABULARIO_USER.format(
                nombre_mundo=nombre_mundo,
                idioma_objetivo=idioma_objetivo,
                escenas_resumen="\n".join(escenas_resumen),
                texto=texto_truncado,
            )),
        ]
    else:
        messages = [
            SystemMessage(content=P.EXAMINADOR_SYSTEM),
            HumanMessage(content=P.EXAMINADOR_USER.format(
                nombre_mundo=nombre_mundo,
                escenas_resumen="\n".join(escenas_resumen),
                texto=texto_truncado,
            )),
        ]

    # Bucle con reintento dirigido: cada pregunta debe tener EXACTAMENTE una opción
    # correcta (ni 0 ni varias). Si el LLM marca mal alguna, se le pide corregir solo eso.
    _MAX = 2
    salida = None
    for intento in range(_MAX + 1):
        respuesta = llm.invoke(messages)
        contenido = respuesta.content
        logger.debug(f"[Examinador] JSON crudo:\n{contenido[:300]}")
        try:
            datos = json.loads(_limpiar_json(contenido))
            salida = SalidaExaminador.model_validate(datos)
        except json.JSONDecodeError as e:
            if intento == _MAX:
                raise AgentError(f"Examinador JSON inválido: {e}", messages) from e
            messages = messages + [respuesta, HumanMessage(content="JSON inválido. Devuelve SOLO el JSON correcto.")]
            continue
        except Exception as e:
            if intento == _MAX:
                raise AgentError(f"Examinador schema inválido: {e}", messages) from e
            messages = messages + [respuesta, HumanMessage(content=f"Schema inválido: {e}. Devuelve SOLO el JSON correcto.")]
            continue

        malas = _preguntas_mal_marcadas(salida)
        if not malas or intento == _MAX:
            break
        fb = "\n".join(f"- {m}" for m in malas)
        messages = messages + [respuesta, HumanMessage(content=(
            "Cada pregunta debe tener EXACTAMENTE UNA opción con \"correcta\": true; las otras tres, false, "
            "y deben ser inequívocamente INCORRECTAS (ningún distractor puede ser también una respuesta válida). "
            f"Corrige estas preguntas y devuelve el JSON COMPLETO de nuevo:\n{fb}"
        ))]
        logger.info(f"[Examinador] reintento {intento + 1}: {len(malas)} pregunta(s) con marcado incorrecto")

    # Red de seguridad determinista: garantiza exactamente una correcta por pregunta.
    _reparar_una_correcta(salida)
    # Sesgo posicional CRUDO: posición de la correcta tal como la emitió el LLM,
    # antes de que _aleatorizar_posiciones la destruya barajando in-place.
    for pregunta in salida.preguntas:
        for idx, opcion in enumerate(pregunta.opciones):
            if opcion.correcta:
                metricas.registrar_sesgo_quiz(idx)
                break
    _aleatorizar_posiciones(salida)
    logger.info(f"[Examinador] {len(salida.preguntas)} preguntas generadas.")
    return salida
