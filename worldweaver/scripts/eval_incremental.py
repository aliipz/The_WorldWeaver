"""
Evaluación técnica con guardado INCREMENTAL y REANUDABLE.

Envuelve a `evaluacion_tecnica.py` (reutiliza su CORPUS, correr_una y métricas) pero, en vez
de escribir los CSV solo al final, los reescribe (de forma atómica: temp + rename) DESPUÉS DE
CADA corrida. Así:
  · si Mercury se queda sin crédito a mitad, basta cambiar la clave en el .env y relanzar el
    MISMO comando: las corridas ya completadas con éxito se saltan y continúa por donde iba;
  · una corrida FALLIDA (excepción / API caída) NO cuenta como hecha → se reintenta al relanzar
    (su fila fallida se sobrescribe con la buena).

Uso:
    python scripts/eval_incremental.py                     # mercury, K=5, todo el corpus
    python scripts/eval_incremental.py --textos T1,E1 --k 2
    python scripts/eval_incremental.py --providers mercury --out outputs/_evaluacion/mercury_k5

Los CSV (abribles en Excel) quedan en --out:
    resultados_corridas.csv   (una fila por corrida: métricas estructurales, coste, reintentos…)
    llamadas_llm.csv          (una fila por llamada al LLM: latencia, tokens, nodo)
"""
import sys
import os
import csv
import shutil
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))   # para importar pipeline/, config/ como hace el harness
sys.path.insert(0, str(HERE))   # para importar el harness hermano

import evaluacion_tecnica as ev  # noqa: E402


def _es_fallo(valor) -> bool:
    return str(valor).strip().lower() in ("true", "1")


def _cargar_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _escribir_atomico(path: Path, filas: list[dict]) -> None:
    """Reescribe el CSV completo vía temp + os.replace (rename atómico): si el proceso
    muere durante la escritura, el CSV anterior queda intacto."""
    if not filas:
        return
    tmp = path.with_suffix(path.suffix + ".tmp")
    ev._escribir_csv(tmp, filas)          # crea el parent y vuelca todas las filas
    os.replace(tmp, path)


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluación técnica incremental y reanudable.")
    ap.add_argument("--providers", default="mercury", help="Lista separada por comas.")
    ap.add_argument("--k", type=int, default=5, help="Repeticiones por (modelo x texto).")
    ap.add_argument("--textos", default="", help="IDs del corpus (T1,T2,...). Vacío = todos.")
    ap.add_argument("--modo-dibujante", default="mock")
    ap.add_argument("--out", default=str(ev.OUTPUTS / "_evaluacion" / "mercury_k5"),
                    help="Carpeta destino de los CSV.")
    args = ap.parse_args()

    out = Path(args.out)
    res_csv = out / "resultados_corridas.csv"
    llm_csv = out / "llamadas_llm.csv"

    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    filtro = {t.strip() for t in args.textos.split(",") if t.strip()}
    corpus = [c for c in ev.CORPUS if (not filtro or c["id"] in filtro)]
    disponibles = [c for c in corpus if (ev.FIXTURES / c["fixture"]).exists()]
    for c in corpus:
        if c not in disponibles:
            print(f"  [aviso] {c['id']}: falta fixture '{c['fixture']}' — se salta.")
    if not disponibles:
        print("No hay textos disponibles.")
        return

    # Estado previo (para reanudar). Indexado por 'corrida' para sobrescribir reintentos.
    resultados = {r["corrida"]: r for r in _cargar_csv(res_csv)}
    llamadas: dict[str, list[dict]] = {}
    for fila in _cargar_csv(llm_csv):
        llamadas.setdefault(fila.get("corrida", ""), []).append(fila)
    hechas = {c for c, r in resultados.items() if not _es_fallo(r.get("fallo_terminal"))}

    plan = [(prov, item, k)
            for prov in providers
            for item in disponibles
            for k in range(1, args.k + 1)]
    pendientes = [(p, it, k) for (p, it, k) in plan
                  if f"{it['id']}_{p}_k{k}" not in hechas]

    print(f"\n=== Evaluación incremental → {out}")
    print(f"    Plan {len(plan)} corridas · ya OK {len(plan) - len(pendientes)} · "
          f"pendientes {len(pendientes)} ===\n", flush=True)

    def _volcar():
        _escribir_atomico(res_csv, list(resultados.values()))
        todas_llm = [f for filas in llamadas.values() for f in filas]
        _escribir_atomico(llm_csv, todas_llm)

    for n, (prov, item, k) in enumerate(pendientes, 1):
        corrida = f"{item['id']}_{prov}_k{k}"
        print(f"[{n}/{len(pendientes)}] {corrida} ...", flush=True)
        # Carpeta limpia antes de generar: evita escenas huérfanas de un intento anterior
        # (p.ej. al reanudar tras un fallo, o si el nombre coincide con una corrida vieja).
        shutil.rmtree(ev.OUTPUTS / f"eval_{corrida}", ignore_errors=True)
        fila, filas_llm = ev.correr_una(prov, item, k, args.modo_dibujante)
        resultados[corrida] = fila
        llamadas[corrida] = filas_llm
        _volcar()   # guardado tras CADA corrida
        estado = "FALLO" if fila.get("fallo_terminal") else "ok"
        print(f"        {estado} · {fila.get('tiempo_total_s')}s · "
              f"{fila.get('n_escenas')} escenas · {fila.get('llamadas_llm')} llamadas LLM · "
              f"guardado ✓", flush=True)

    vals = list(resultados.values())
    n_fallos = sum(1 for r in vals if _es_fallo(r.get("fallo_terminal")))
    print(f"\n=== Hecho. {len(vals)} corridas acumuladas ({n_fallos} con fallo terminal). ===")
    print(f"    {res_csv}")
    print(f"    {llm_csv}")
    if n_fallos:
        print("    (Relanza el MISMO comando tras cambiar la clave para reintentar los fallos.)")


if __name__ == "__main__":
    main()
