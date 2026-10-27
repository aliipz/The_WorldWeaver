"""
Continúa un mundo ya empezado sin repetir el Organizador (no cambia las escenas).

Uso (desde worldweaver/):
    python scripts/reanudar.py <mundo>                     # sigue desde la primera escena sin preview
    python scripts/reanudar.py <mundo> --escena escena_03  # regenera solo esa escena
    python scripts/reanudar.py <mundo> --desde escena_03   # regenera de esa escena al final
    python scripts/reanudar.py <mundo> --modo educativo --idioma en

Carga de outputs/<mundo>/ la salida del Organizador y los SceneGraph ya generados
(mismos personajes, modelos y tamaños). Modo e idioma se deducen de la marca
_incompleto.json o de los preview existentes si no se indican. Al terminar bien,
quita la marca de mundo incompleto para que vuelva a salir en la galería.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from pipeline.graph import compilar_grafo, estado_desde_disco  # noqa: E402
from runtime_paths import dato  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mundo")
    ap.add_argument("--escena", default=None, help="regenerar solo esta escena (p.ej. escena_03)")
    ap.add_argument("--desde", default=None, help="regenerar desde esta escena hasta el final")
    ap.add_argument("--modo", choices=["narrativo", "educativo"], default=None)
    ap.add_argument("--idioma", choices=["es", "en"], default=None)
    ap.add_argument("--provider", default="mercury")
    args = ap.parse_args()

    out_dir = dato("outputs") / args.mundo
    if not (out_dir / "salida_organizador.json").exists():
        raise SystemExit(f"{out_dir} no tiene salida_organizador.json: no hay nada que reanudar.")

    estado = estado_desde_disco(out_dir, escena=args.escena, desde=args.desde, provider=args.provider,
                                modo=args.modo, idioma=args.idioma)
    compilar_grafo().invoke(estado)

    marca = out_dir / "_incompleto.json"
    pendientes = [p for p in out_dir.glob("scene_graph_*.json")
                  if not (out_dir / p.name.replace("scene_graph_", "preview_").replace(".json", ".html")).exists()]
    if marca.exists() and not pendientes:
        marca.unlink()
        print("Mundo completo: marca de incompleto eliminada.")


if __name__ == "__main__":
    main()
