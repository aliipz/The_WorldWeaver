"""Helper para crear instancias de LLM según el provider."""

from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from config.settings import settings


# ── Callbacks globales (instrumentación de evaluación) ────────────────────────
# Vacío en producción → no-op. El harness de evaluación técnica registra aquí su
# MetricasCallback para capturar latencia y tokens de toda llamada al LLM sin
# tener que tocar cada agente.
_CALLBACKS: list = []


def registrar_callback(cb) -> None:
    if cb not in _CALLBACKS:
        _CALLBACKS.append(cb)


def limpiar_callbacks() -> None:
    _CALLBACKS.clear()


def get_llm(provider: str = "mercury") -> ChatOpenAI | ChatOllama:
    """
    Factory que devuelve el LLM correspondiente al provider indicado.

    Args:
        provider: "mercury" (default) o "ollama"

    Returns:
        Instancia de ChatOpenAI (mercury) o ChatOllama (ollama)
    """
    if provider == "ollama":
        return ChatOllama(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model_text,
            temperature=0.2,
            format="json",
            callbacks=list(_CALLBACKS),
        )

    # mercury (default)
    api_key = settings.mercury_api_key
    if not api_key:
        raise ValueError(
            "MERCURY_API_KEY no está configurada en el archivo .env. "
            "Usa --provider ollama si quieres usar Ollama local."
        )
    return ChatOpenAI(
        model=settings.mercury_model,
        base_url=settings.mercury_base_url,
        api_key=api_key,
        temperature=0.2,
        callbacks=list(_CALLBACKS),
    )


def provider_name(provider: str) -> str:
    """Devuelve el nombre corto del modelo para usar en paths."""
    if provider == "ollama":
        return settings.ollama_model_text.split(":")[0]
    return settings.mercury_model
