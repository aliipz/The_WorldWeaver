"""
Agente 1 — El Organizador
Entrada:  texto libre (str) + historial de mensajes (para reintentos)
Salida:   (SalidaOrganizador, mensajes_actualizados)

Una sola llamada al LLM — sin bucle de reintentos interno.
El reintento y el feedback de error los gestiona el grafo LangGraph
a través del nodo validador y las aristas condicionales.
"""

import json
import re
import logging

from langchain_core.messages import SystemMessage, HumanMessage

from config.prompts import get_prompts
from config.llm import get_llm
from pipeline.errors import AgentError, SinNarrativa
from schemas import SalidaOrganizador

logger = logging.getLogger(__name__)


def _clasificar_contenido(texto: str, llm, P) -> str:
    """Primera pasada (modo educativo): detecta el subtipo del contenido.
    Devuelve 'historico' | 'taxonomico' | 'vocabulario'."""
    msgs = [
        SystemMessage(content=P.ORGANIZADOR_CLASIFICADOR_SYSTEM),
        HumanMessage(content=P.ORGANIZADOR_CLASIFICADOR_USER.format(texto=texto[:2000])),
    ]
    try:
        respuesta = llm.invoke(msgs)
        tipo = respuesta.content.strip().lower()
        if "vocabulario" in tipo or "vocabulary" in tipo:
            resultado = "vocabulario"
        elif "taxonomico" in tipo or "taxonómico" in tipo:
            resultado = "taxonomico"
        else:
            resultado = "historico"
    except Exception:
        resultado = "historico"
    logger.info(f"[Organizador] Subtipo educativo: {resultado}")
    print(f"   [Clasificador] Subtipo educativo detectado: {resultado}")
    return resultado


def _clasificar_vocabulario(texto: str, llm, P) -> dict:
    """Segunda pasada (subtipo vocabulario): detecta tipo (tangible/conversacional),
    idioma objetivo, lista de palabras y espacio (mono/multi). Tolerante a fallos:
    ante cualquier error devuelve un default razonable (tangible / en / mono)."""
    default = {"tipo": "tangible", "idioma_objetivo": "en", "palabras": [], "espacio": "mono"}
    msgs = [
        SystemMessage(content=P.ORGANIZADOR_VOCABULARIO_CLASIFICADOR_SYSTEM),
        HumanMessage(content=P.ORGANIZADOR_VOCABULARIO_CLASIFICADOR_USER.format(texto=texto[:2000])),
    ]
    try:
        respuesta = llm.invoke(msgs)
        datos = json.loads(_limpiar_json(respuesta.content))
        tipo = str(datos.get("tipo", "tangible")).strip().lower()
        if tipo not in ("tangible", "conversacional"):
            tipo = "tangible"
        idioma_obj = str(datos.get("idioma_objetivo") or "en").strip().lower()[:5] or "en"
        palabras = datos.get("palabras") or []
        if not isinstance(palabras, list):
            palabras = []
        palabras = [str(w).strip() for w in palabras if str(w).strip()][:10]
        espacio = str(datos.get("espacio") or "mono").strip().lower()
        if espacio not in ("mono", "multi"):
            espacio = "mono"
        resultado = {"tipo": tipo, "idioma_objetivo": idioma_obj, "palabras": palabras, "espacio": espacio}
    except Exception:
        resultado = default
    logger.info(f"[Organizador] Vocabulario: {resultado['tipo']} / {resultado['idioma_objetivo']} / {resultado['espacio']} / {len(resultado['palabras'])} palabras")
    print(f"   [Clasificador vocab] tipo={resultado['tipo']} idioma_objetivo={resultado['idioma_objetivo']} espacio={resultado['espacio']} ({len(resultado['palabras'])} palabras)")
    return resultado


def _limpiar_json(texto: str) -> str:
    texto = re.sub(r"```(?:json)?\s*", "", texto)
    return texto.replace("```", "").strip()


def _con_meta(err: AgentError, meta: dict | None) -> AgentError:
    """Adjunta la clasificación educativa (subtipo/tipo/idioma objetivo) al AgentError para que
    el grafo la persista aunque ESTE intento falle. Si no, la meta —calculada antes de la llamada
    principal— se perdería y los reintentos (sin reclasificar) la dejarían en None aguas abajo."""
    if meta is not None:
        err.meta = meta
    return err


def ejecutar_organizador(
    texto: str,
    provider: str = "mercury",
    mensajes_previos: list | None = None,
    modo: str = "narrativo",
    idioma: str = "es",
) -> tuple[SalidaOrganizador, list]:
    """
    Ejecuta una llamada al LLM del Organizador.

    Args:
        texto: Texto narrativo de entrada.
        provider: "mercury" | "ollama"
        mensajes_previos: Historial de mensajes de intentos anteriores
                          (incluye el feedback de error del validador).
                          None en el primer intento.

    Returns:
        (SalidaOrganizador, mensajes_completos)

    Raises:
        ValueError: Si el JSON o el schema de Pydantic no son válidos.
        RuntimeError: En errores irrecuperables de infraestructura.
    """
    llm = get_llm(provider)
    P = get_prompts(idioma)

    # meta: clasificación educativa de ESTE intento. Solo se calcula en el primer
    # intento (no en reintentos, que reutilizan mensajes_previos). El grafo la
    # conserva entre reintentos. None = no calculada en este intento.
    meta = None

    if mensajes_previos:
        messages = mensajes_previos
    else:
        if modo == "educativo":
            subtipo = _clasificar_contenido(texto, llm, P)
            meta = {"subtipo_educativo": subtipo, "tipo_vocabulario": None, "idioma_objetivo": None}
            if subtipo == "taxonomico":
                system_prompt = P.ORGANIZADOR_EDUCATIVO_TAXONOMICO_SYSTEM
                user_content = P.ORGANIZADOR_EDUCATIVO_TAXONOMICO_USER.format(texto=texto)
            elif subtipo == "vocabulario":
                voc = _clasificar_vocabulario(texto, llm, P)
                if voc["tipo"] == "tangible" and voc["espacio"] == "mono":
                    system_prompt = P.ORGANIZADOR_VOCABULARIO_TANGIBLE_SYSTEM
                    user_content = P.ORGANIZADOR_VOCABULARIO_TANGIBLE_USER.format(
                        idioma_objetivo=voc["idioma_objetivo"],
                        palabras=", ".join(voc["palabras"]) or "(infiérelas del texto)",
                        texto=texto,
                    )
                    meta["tipo_vocabulario"] = "tangible"
                    meta["idioma_objetivo"] = voc["idioma_objetivo"]
                elif voc["tipo"] == "conversacional":
                    # Tipo B: situacional (saludos, profesiones) o abstracto (meses, números...).
                    system_prompt = P.ORGANIZADOR_VOCABULARIO_CONVERSACIONAL_SYSTEM
                    user_content = P.ORGANIZADOR_VOCABULARIO_CONVERSACIONAL_USER.format(
                        idioma_objetivo=voc["idioma_objetivo"],
                        palabras=", ".join(voc["palabras"]) or "(infiérelas del texto)",
                        texto=texto,
                    )
                    meta["tipo_vocabulario"] = "conversacional"
                    meta["idioma_objetivo"] = voc["idioma_objetivo"]
                else:
                    # Tangible MULTI-espacio aún no soportado → se degrada con aviso a la rama
                    # educativa histórica para no romper el pipeline.
                    logger.warning(
                        f"[Organizador] Vocabulario {voc['tipo']}/{voc['espacio']} aún no soportado; "
                        "degradando a subtipo histórico."
                    )
                    print(f"   [Organizador] Vocabulario {voc['tipo']}/{voc['espacio']} no soportado todavía → uso rama histórica.")
                    meta["subtipo_educativo"] = "historico"
                    system_prompt = P.ORGANIZADOR_EDUCATIVO_SYSTEM
                    user_content = P.ORGANIZADOR_EDUCATIVO_USER.format(texto=texto)
            else:  # historico
                system_prompt = P.ORGANIZADOR_EDUCATIVO_SYSTEM
                user_content = P.ORGANIZADOR_EDUCATIVO_USER.format(texto=texto)
            # Resaltado de datos clave (intros, cierres, descripciones).
            system_prompt = system_prompt + "\n\n" + P.RESALTADO_EDUCATIVO
        else:
            system_prompt = P.ORGANIZADOR_SYSTEM
            user_content = P.ORGANIZADOR_USER.format(texto=texto)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ]

    respuesta = llm.invoke(messages)
    messages = messages + [respuesta]

    contenido = respuesta.content
    logger.debug(f"[Organizador] JSON crudo:\n{contenido[:300]}")

    try:
        json_limpio = _limpiar_json(contenido)
        datos = json.loads(json_limpio)
        salida = SalidaOrganizador.model_validate(datos)
        # Anota la clasificación educativa de este intento en la salida (el LLM no la
        # emite). En reintentos meta=None y el nodo del grafo la restaura desde el estado.
        if meta is not None:
            salida.subtipo_educativo = meta["subtipo_educativo"]
            salida.tipo_vocabulario = meta["tipo_vocabulario"]
            salida.idioma_objetivo = meta["idioma_objetivo"]
            # El LLM a veces aplica el resaltado ==así== a campos de datos del vocabulario
            # (nombre_objetivo). Es markup de presentación, no debe vivir en un dato → se limpia.
            if meta["subtipo_educativo"] == "vocabulario":
                for esc in salida.escenas:
                    for o in esc.objetos:
                        if o.nombre_objetivo:
                            o.nombre_objetivo = re.sub(r"==(.+?)==", r"\1", o.nombre_objetivo).strip()
        # 0 escenas no debe reventar aguas abajo (escenas[0]) — es un fallo claro
        # del modelo. Lo convertimos en AgentError con la respuesta cruda para que
        # el grafo reintente con feedback y para diagnosticar (texto vacío/basura).
        if not salida.escenas:
            # Texto sin historia (p. ej. "probando probando"): reintentar es inútil,
            # el texto es el problema. Fallamos rápido con un mensaje amigable.
            snippet = (contenido or "").strip()[:200] or "(respuesta vacía)"
            print(f"   [Organizador] El modelo devolvió 0 escenas. Respuesta cruda: {snippet!r}")
            _MSG = {
                "es": "El texto no parece contener una historia. Escribe un relato con "
                      "personajes y acontecimientos (al menos unos párrafos).",
                "en": "The text doesn't seem to contain a story. Provide a narrative with "
                      "characters and events (at least a few paragraphs).",
            }
            raise SinNarrativa(_MSG.get(idioma, _MSG["es"]))
        logger.info(f"[Organizador] {len(salida.escenas)} escena(s) extraída(s).")
        return salida, messages

    except json.JSONDecodeError as e:
        raise _con_meta(AgentError(f"JSON inválido: {e}", messages), meta) from e
    except (AgentError, SinNarrativa):
        raise
    except Exception as e:
        error_str = str(e)
        if any(k in error_str for k in ["memory", "status code: 5", "Connection refused"]):
            raise RuntimeError(f"[Organizador] Error irrecuperable: {error_str}") from e
        raise _con_meta(AgentError(f"Schema inválido: {e}", messages), meta) from e