"""
Resolución de rutas en tiempo de ejecución — funciona igual en desarrollo
y en el ejecutable empaquetado con PyInstaller.

Dos bases distintas:

- RECURSOS (solo lectura): sandbox/, assets/, .env, prompts...
    · dev  → la carpeta del paquete (donde vive este archivo).
    · .exe → la carpeta temporal de extracción de PyInstaller (sys._MEIPASS).

- DATOS (escribible): outputs/ — los mundos generados por el usuario.
    · dev  → la carpeta del paquete.
    · .exe → junto al ejecutable (sys.executable), para que persista entre
             ejecuciones (en modo onefile la extracción temporal se borra al cerrar).

Las semillas (los mundos pre-generados que se reparten) viajan en RECURSOS como
`outputs_semilla/` y el lanzador las copia a DATOS/outputs en el primer arranque.
"""

import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))

# Carpeta del paquete worldweaver/ (donde vive este archivo) en desarrollo.
_PAQUETE = Path(__file__).resolve().parent

if FROZEN:
    RECURSOS = Path(getattr(sys, "_MEIPASS", _PAQUETE))
    DATOS    = Path(sys.executable).resolve().parent
else:
    RECURSOS = _PAQUETE
    DATOS    = _PAQUETE


def recurso(*partes) -> Path:
    """Ruta a un recurso de solo lectura empaquetado (sandbox, assets, .env)."""
    return RECURSOS.joinpath(*partes)


def dato(*partes) -> Path:
    """Ruta a datos escribibles (outputs y mundos generados)."""
    return DATOS.joinpath(*partes)
