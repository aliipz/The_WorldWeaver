"""
Schema de salida del Agente 5 (Programador).
Contiene el código JS generado para Three.js.
"""
from pydantic import BaseModel, Field
from typing import List


class SalidaProgramador(BaseModel):
    id_escena: str
    codigo_js: str = Field(..., description="Código JavaScript para Three.js")
    dependencias: List[str] = Field(
        default_factory=list,
        description="Librerías JS externas necesarias"
    )
    notas: str = Field(default="", description="Observaciones del agente sobre el código generado")
