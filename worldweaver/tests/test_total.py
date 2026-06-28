"""
Pipeline completo de WorldWeaver.

Uso:
    python tests/test_total.py <texto.txt> <nombre_mundo> [opciones]

Ejemplo:
    python tests/test_total.py tests/fixtures/cuento_ejemplo.txt bosque_magico
    python tests/test_total.py texto.txt mi_mundo --provider ollama --dibujante mock
    python tests/test_total.py texto.txt mi_mundo --escena escena_01

Genera en outputs/<nombre_mundo>/:
    salida_organizador.json
    salida_director_<escena>.json
    scene_graph_<escena>.json
    salida_programador_<escena>.json
    salida_musico_<escena>.json
    preview_<escena>.html  ← abrir en el navegador
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.graph import ejecutar_pipeline


def main():
    parser = argparse.ArgumentParser(description="Pipeline completo WorldWeaver")
    parser.add_argument("texto",        help="Ruta al fichero de texto narrativo")
    parser.add_argument("nombre_mundo", help="Nombre del mundo (carpeta de salida)")
    parser.add_argument("--provider",   default="mercury", choices=["mercury", "ollama"])
    parser.add_argument("--dibujante",  default="mock",    choices=["mock", "fal", "gemini", "auto"],
                        help="Modo del Dibujante (default: mock)")
    parser.add_argument("--escena",     default=None,
                        help="Procesar solo esta escena, ej: escena_01")
    parser.add_argument("--modo",       default="narrativo", choices=["narrativo", "educativo"],
                        help="Modo de generación (default: narrativo)")
    parser.add_argument("--idioma",     default="es", choices=["es", "en"],
                        help="Idioma de generación del mundo / UI (default: es)")
    args = parser.parse_args()

    texto_path = Path(args.texto)
    if not texto_path.exists():
        print(f"ERROR: No se encontró '{texto_path}'")
        sys.exit(1)
    texto = texto_path.read_text(encoding="utf-8")

    ejecutar_pipeline(
        texto=texto,
        nombre_mundo=args.nombre_mundo,
        provider=args.provider,
        modo_dibujante=args.dibujante,
        escena_filtro=args.escena,
        modo=args.modo,
        idioma=args.idioma,
    )


if __name__ == "__main__":
    main()
