"""Configuración global del proyecto, cargada desde .env"""
from pydantic_settings import BaseSettings, SettingsConfigDict

from runtime_paths import dato, recurso

# El .env empaquetado viaja como recurso de solo lectura, pero si existe uno
# junto al ejecutable (DATOS/.env) tiene prioridad → permite cambiar las claves
# sin reempaquetar.
_ENV_RECURSO = recurso(".env")
_ENV_EXTERNO = dato(".env")
_ENV_FILE = _ENV_EXTERNO if _ENV_EXTERNO.is_file() else _ENV_RECURSO


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        extra="ignore",
    )

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model_text: str = "minimax-m2.7:cloud"
    ollama_model_code: str = "qwen2.5-coder"

    # Mercury (Inception Labs)
    mercury_base_url: str = "https://api.inceptionlabs.ai/v1/"
    mercury_model: str = "mercury-2"
    mercury_api_key: str = ""

    # Gemini
    gemini_api_key: str = ""

    # fal.ai (generación de imágenes con FLUX)
    fal_api_key: str = ""
    # [PENDIENTE — LoRA] Una vez entrenado el LoRA de estilo, añadir la URL aquí:
    # lora_url: str = ""  # ej: "https://huggingface.co/.../nanobanana_style.safetensors"

    # Poly.pizza (modelos 3D low-poly, gratuito para hobby)
    polypizza_api_key: str = ""

    # Freesound (música y sonido ambiente, Creative Commons)
    freesound_api_key: str = ""

    # Pipeline
    max_retries: int = 3


settings = Settings()