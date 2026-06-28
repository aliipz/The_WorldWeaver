"""
Schema de salida del Agente Músico.
"""
from pydantic import BaseModel, Field
from typing import Literal, Optional


class PistaAudio(BaseModel):
    url_preview: str = Field(..., description="URL MP3 directamente reproducible en el browser")
    titulo: str
    autor: str
    duracion_segundos: float
    loop: bool = True
    volumen: float = Field(default=0.6, ge=0.0, le=1.0)


class SalidaMusico(BaseModel):
    id_escena: str
    query_usada: str = Field(..., description="Keywords enviadas a Freesound")
    pista_principal: PistaAudio
    pista_fallback: Optional[PistaAudio] = Field(
        None, description="Segunda opción si la principal falla al cargar"
    )
    fuente: Literal["freesound", "mock", "fallback"]
