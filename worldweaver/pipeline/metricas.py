"""
Sink de instrumentación para la evaluación técnica (capítulo de Evaluación).

Todo el pipeline corre en el mismo proceso y de forma síncrona (`grafo.invoke`),
así que un singleton a nivel de módulo es suficiente: el harness de evaluación
(`scripts/evaluacion_tecnica.py`) llama a `reset()` antes de cada corrida y lee
los acumuladores después. En producción nadie limpia ni lee estos acumuladores
y el coste es despreciable (unas listas que crecen y se descartan con el proceso).

Tres señales que el resto de métricas NO podía obtener a posteriori de los JSON:
  - `llamadas_llm`        — latencia y tokens por llamada al LLM (callback).
  - `reparaciones_director` — cuántas reparaciones deterministas aplicó el Director
                              por escena (proxy de la calidad cruda del LLM).
  - `sesgo_quiz_crudo`    — posición de la respuesta correcta del Examinador ANTES
                              de barajar (el barajado la destruye in-place).
"""
from __future__ import annotations

import time
from typing import Any

# ── Acumuladores de una corrida del pipeline ──────────────────────────────────
llamadas_llm: list[dict] = []          # una fila por llamada al LLM
reparaciones_director: list[dict] = []  # una fila por escena
sesgo_quiz_crudo: list[int] = []        # índice 0=a..3=d de la correcta pre-barajado


def reset() -> None:
    """Vacía los acumuladores. El harness lo llama antes de cada corrida."""
    llamadas_llm.clear()
    reparaciones_director.clear()
    sesgo_quiz_crudo.clear()


def registrar_reparacion_director(
    escena: str, narrativos: int, separacion: int, colisiones: int
) -> None:
    reparaciones_director.append({
        "escena": escena,
        "narrativos_reubicados": narrativos,
        "separacion_ajustes": separacion,
        "colisiones_resueltas": colisiones,
    })


def registrar_sesgo_quiz(indice_correcta: int) -> None:
    """Posición (0=a,1=b,2=c,3=d) de la opción correcta tal como la emitió el LLM,
    antes de `_aleatorizar_posiciones`. Permite medir el sesgo posicional crudo."""
    sesgo_quiz_crudo.append(indice_correcta)


# ── Callback de LangChain: latencia + tokens por llamada al LLM ────────────────
try:
    from langchain_core.callbacks import BaseCallbackHandler
except Exception:  # pragma: no cover — langchain siempre está presente en runtime
    BaseCallbackHandler = object  # type: ignore


class MetricasCallback(BaseCallbackHandler):  # type: ignore[misc]
    """Registra una fila en `llamadas_llm` por cada invocación del LLM, con su
    latencia de pared, los tokens de entrada/salida y, si está disponible, el
    nodo de LangGraph que originó la llamada (para el desglose por agente).

    No mantiene estado fuera del propio handler: empareja start/end por `run_id`.
    Tolerante a fallos — cualquier excepción interna degrada a campos `None` en
    lugar de romper el pipeline.
    """

    def __init__(self) -> None:
        self._pendientes: dict[Any, tuple[float, Any]] = {}

    # LLMs de texto y chat models entran por distintos hooks; cubrimos ambos.
    def on_llm_start(self, serialized, prompts, *, run_id=None, metadata=None, **kwargs):
        self._pendientes[run_id] = (time.perf_counter(), self._nodo(metadata))

    def on_chat_model_start(self, serialized, messages, *, run_id=None, metadata=None, **kwargs):
        self._pendientes[run_id] = (time.perf_counter(), self._nodo(metadata))

    def on_llm_end(self, response, *, run_id=None, **kwargs):
        inicio, nodo = self._pendientes.pop(run_id, (None, None))
        latencia = (time.perf_counter() - inicio) if inicio is not None else None
        entrada, salida = self._extraer_tokens(response)
        llamadas_llm.append({
            "nodo": nodo,
            "latencia_s": latencia,
            "tokens_entrada": entrada,
            "tokens_salida": salida,
        })

    def on_llm_error(self, error, *, run_id=None, **kwargs):
        self._pendientes.pop(run_id, None)

    @staticmethod
    def _nodo(metadata) -> Any:
        if isinstance(metadata, dict):
            return metadata.get("langgraph_node")
        return None

    @staticmethod
    def _extraer_tokens(response):
        """Tokens del modo más portable primero (usage_metadata del mensaje),
        con fallback al token_usage estilo OpenAI. Devuelve (entrada, salida)."""
        try:
            for gen_list in getattr(response, "generations", []) or []:
                for gen in gen_list:
                    um = getattr(getattr(gen, "message", None), "usage_metadata", None)
                    if um:
                        return um.get("input_tokens"), um.get("output_tokens")
        except Exception:
            pass
        try:
            tu = (getattr(response, "llm_output", None) or {}).get("token_usage", {})
            if tu:
                return tu.get("prompt_tokens"), tu.get("completion_tokens")
        except Exception:
            pass
        return None, None
