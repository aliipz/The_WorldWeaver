"""
Test del Agente 1 — Organizador.
Ejecuta el agente contra el cuento de Caperucita y valida la salida.

Uso:
    pytest tests/test_organizador.py -v -s
    python tests/test_organizador.py                    # usa mercury por defecto
    python tests/test_organizador.py --provider ollama   # usa ollama
    python tests/test_organizador.py --provider mercury   # usa mercury
"""

import sys
import json
from pathlib import Path

# Permite importar desde la raíz del proyecto sin instalar el paquete
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.llm import provider_name
from agents.organizador import ejecutar_organizador


FIXTURE = Path(__file__).parent / "fixtures" / "cuento_ejemplo.txt"
OUTPUTS = Path(__file__).parent.parent / "outputs"


def test_organizador_devuelve_escenas():
    """El organizador debe extraer al menos 2 escenas del cuento de Caperucita."""
    texto = FIXTURE.read_text(encoding="utf-8")
    salida = ejecutar_organizador(texto)

    assert salida.titulo_historia, "El título no puede estar vacío"
    assert len(salida.escenas) >= 2, f"Se esperaban ≥2 escenas, se obtuvieron {len(salida.escenas)}"

    for escena in salida.escenas:
        assert escena.id.startswith("escena_"), f"ID de escena mal formado: {escena.id}"
        assert escena.titulo
        assert escena.entorno,    f"Escena '{escena.id}' sin entorno"
        assert escena.atmosfera,  f"Escena '{escena.id}' sin atmosfera"
        assert len(escena.personajes) >= 1, f"Escena '{escena.id}' sin personajes"

        for p in escena.personajes:
            assert p.rol in ("protagonista", "antagonista", "secundario"), \
                f"Rol inválido '{p.rol}' en personaje '{p.id}'"
            assert "_" in p.id, f"ID de personaje sin guion bajo: {p.id}"


def test_organizador_personajes_globales():
    """Caperucita debe aparecer como personaje global (está en más de una escena)."""
    texto = FIXTURE.read_text(encoding="utf-8")
    salida = ejecutar_organizador(texto)

    ids_globales = [p.id for p in salida.personajes_globales]
    nombres_globales = [p.nombre.lower() for p in salida.personajes_globales]

    assert any("caperucita" in n for n in nombres_globales), \
        f"Caperucita debería estar en personajes_globales. Se obtuvieron: {nombres_globales}"


# --- Ejecución directa con pretty print ---
if __name__ == "__main__":
    import argparse
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--provider", type=str, default="mercury",
        choices=["mercury", "ollama"],
        help="Provider de LLM a utilizar (default: mercury)"
    )
    args = parser.parse_args()

    texto = FIXTURE.read_text(encoding="utf-8")
    print("\n📖 Texto de entrada:\n", texto[:200], "...\n")

    salida = ejecutar_organizador(texto, provider=args.provider)

    print("\n✅ Salida del Organizador:\n")
    print(json.dumps(salida.model_dump(), indent=2, ensure_ascii=False))
    print(f"\n📊 Resumen: {len(salida.escenas)} escenas, "
          f"{len(salida.personajes_globales)} personaje(s) global(es)")

    OUTPUTS.mkdir(parents=True, exist_ok=True)
    modelo = provider_name(args.provider)
    json_path = OUTPUTS / f"salida_organizador_{modelo}.json"
    json_path.write_text(
        json.dumps(salida.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"\n💾 Guardado: {json_path}")