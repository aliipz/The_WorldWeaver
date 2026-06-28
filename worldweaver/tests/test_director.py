"""
Test del Agente 2 — Director.
Ejecuta el pipeline Organizador → Director sobre el cuento de Caperucita.

Uso:
    pytest tests/test_director.py -v -s
    python tests/test_director.py                    # usa mercury por defecto
    python tests/test_director.py --provider ollama   # usa ollama
    python tests/test_director.py --provider mercury  # usa mercury
    python tests/test_director.py --desde-json worldweaver/outputs/salida_organizador.json
"""

import sys
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.llm import provider_name
from agents.organizador import ejecutar_organizador
from agents.director import ejecutar_director
from schemas.especificacion import SalidaDirector

FIXTURE = Path(__file__).parent / "fixtures" / "cuento_ejemplo.txt"
OUTPUTS = Path(__file__).parent.parent / "outputs"


def test_director_primera_escena():
    """El Director debe planificar correctamente la primera escena del cuento."""
    texto = FIXTURE.read_text(encoding="utf-8")
    salida_org = ejecutar_organizador(texto)
    primera_escena = salida_org.escenas[0]

    salida_dir = ejecutar_director(primera_escena)

    assert salida_dir.id_escena == primera_escena.id
    assert salida_dir.entorno,   "El Director debe devolver el campo 'entorno'"
    assert salida_dir.atmosfera, "El Director debe devolver el campo 'atmosfera'"
    assert len(salida_dir.elementos) >= 2, "Debe haber al menos 1 personaje + 1 decorado"

    tipos = {e.tipo for e in salida_dir.elementos}
    assert "personaje" in tipos, "Debe existir al menos un personaje"
    assert "decorado"  in tipos, "Debe existir al menos un elemento de decorado"


def test_director_ids_narrativos_preservados():
    """Los IDs de personajes y objetos narrativos deben coincidir con los del Organizador."""
    texto = FIXTURE.read_text(encoding="utf-8")
    salida_org = ejecutar_organizador(texto)
    escena = salida_org.escenas[0]

    ids_org = {p.id for p in escena.personajes} | {o.id for o in escena.objetos}
    salida_dir = ejecutar_director(escena)

    ids_narrativos_dir = {e.id for e in salida_dir.elementos if e.origen == "narrativo"}
    assert ids_narrativos_dir <= ids_org, (
        f"IDs narrativos del Director que no existen en el Organizador: "
        f"{ids_narrativos_dir - ids_org}"
    )


def test_director_sin_colisiones_grid():
    """No puede haber dos elementos en la misma celda del grid."""
    texto = FIXTURE.read_text(encoding="utf-8")
    salida_org = ejecutar_organizador(texto)
    salida_dir = ejecutar_director(salida_org.escenas[0])

    celdas = [(e.posicion_grid.columna, e.posicion_grid.fila) for e in salida_dir.elementos]
    assert len(celdas) == len(set(celdas)), f"Colisiones de grid detectadas: {celdas}"


# --- Ejecución directa con pretty print ---
if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--provider", type=str, default="mercury",
        choices=["mercury", "ollama"],
        help="Provider de LLM a utilizar (default: mercury)"
    )
    parser.add_argument(
        "--desde-json", type=str, default=None,
        help="Ruta a un salida_organizador.json previo. "
             "Si no se indica, corre el Organizador completo."
    )
    args = parser.parse_args()

    if args.desde_json:
        from schemas.escenas import SalidaOrganizador
        datos = json.loads(Path(args.desde_json).read_text(encoding="utf-8"))
        salida_org = SalidaOrganizador.model_validate(datos)
        print(f"\n📂 Cargado desde: {args.desde_json}")
    else:
        texto = FIXTURE.read_text(encoding="utf-8")
        print("\n🎬 Ejecutando Organizador...")
        salida_org = ejecutar_organizador(texto, provider=args.provider)

    OUTPUTS.mkdir(parents=True, exist_ok=True)

    for escena in salida_org.escenas:
        print(f"\n🎨 Director planificando escena: '{escena.titulo}'...")
        salida_dir, _ = ejecutar_director(escena, provider=args.provider)

        print(json.dumps(salida_dir.model_dump(), indent=2, ensure_ascii=False))

        por_tipo = {}
        for e in salida_dir.elementos:
            por_tipo[e.tipo] = por_tipo.get(e.tipo, 0) + 1
        print(f"\n📊 Resumen '{escena.id}':", " | ".join(f"{t}: {n}" for t, n in por_tipo.items()))

        modelo = provider_name(args.provider)
        json_path = OUTPUTS / f"salida_director_{escena.id}_{modelo}.json"
        json_path.write_text(
            json.dumps(salida_dir.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"   💾 Guardado: {json_path}")
        print("-" * 60)