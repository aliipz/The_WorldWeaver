"""
Test del Agente Músico.
Carga la salida del Organizador y busca música en Freesound.

Uso:
    python tests/test_musico.py                    # todas las escenas
    python tests/test_musico.py --escena escena_01
    python tests/test_musico.py --mock             # sin llamadas a API
"""

import sys
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.musico import ejecutar_musico
from schemas.escenas import SalidaOrganizador

OUTPUTS = Path(__file__).parent.parent / "outputs"


def _cargar_escenas():
    archivos = sorted(OUTPUTS.glob("salida_organizador*.json"))
    if not archivos:
        raise FileNotFoundError("No hay salida_organizador*.json en outputs/.")
    datos = json.loads(archivos[0].read_text(encoding="utf-8"))
    return SalidaOrganizador.model_validate(datos).escenas


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--escena", default=None)
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    modo = "mock" if args.mock else "auto"
    escenas = _cargar_escenas()

    if args.escena:
        escenas = [e for e in escenas if e.id == args.escena]
        if not escenas:
            print(f"Escena '{args.escena}' no encontrada.")
            sys.exit(1)

    for escena in escenas:
        print(f"\n[Musico] Escena: {escena.id}")
        print(f"  entorno:   {escena.entorno[:80]}")
        print(f"  atmosfera: {escena.atmosfera[:80]}")

        salida = ejecutar_musico(
            id_escena=escena.id,
            atmosfera=escena.atmosfera,
            entorno=escena.entorno,
            modo=modo,
        )

        print(f"  query usada:  {salida.query_usada}")
        print(f"  pista:        {salida.pista_principal.titulo} — {salida.pista_principal.autor}")
        print(f"  duracion:     {salida.pista_principal.duracion_segundos}s")
        print(f"  url:          {salida.pista_principal.url_preview}")
        if salida.pista_fallback:
            print(f"  fallback:     {salida.pista_fallback.titulo}")

        json_path = OUTPUTS / f"salida_musico_{escena.id}.json"
        json_path.write_text(
            json.dumps(salida.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"  [OK] Guardado: {json_path}")
        print("-" * 60)
