"""
Schema de salida del Agente 4 (Dibujante).
Registro de los assets generados y sus rutas.
"""
from pydantic import BaseModel, Field
from typing import List, Optional


class AssetGenerado(BaseModel):
    id_elemento: str
    ruta_png: str = Field(..., description="Ruta relativa al PNG con fondo transparente")
    ancho_px: int
    alto_px: int
    prompt_usado: str
    intentos: int = Field(default=1, description="Nº de intentos hasta aprobación del verificador")


class SalidaDibujante(BaseModel):
    id_escena: str
    assets: List[AssetGenerado]
