"""
Fidelidad de extracción narrativa (Tabla tab:fidelidad de la memoria).

Métrica SEMI-OBJETIVA: compara la anotación manual de referencia (scripts/gold/*.json:
entidades esperadas + nº de escenas razonable) con lo que el pipeline produjo realmente en
cada corrida del modelo.

Para no leer carpetas obsoletas, se ATA AL CSV de la corrida (resultados_corridas.csv en --out):
solo cuenta las corridas marcadas ahí como exitosas y cuyo 'fixture' coincide con el del gold.
De cada corrida válida lee el mundo generado en outputs/eval_<corrida>/ y compara contra:
  · los personajes/objetos extraídos por el Organizador, y
  · los nodos del scene graph (personaje/objeto/decorado: nombre + keyword de búsqueda),
de modo que una entidad que aparece como decorado (p.ej. 'faro') también cuenta.

Por cada texto:
  · cobertura de entidades (%) = fracción de entidades esperadas presentes, promedio sobre K;
  · escenas esperadas vs obtenidas (segmentación), promedio sobre K.
El emparejamiento es tolerante (minúsculas, sin acentos, subcadena en ambos sentidos o token
significativo compartido) y LISTA las entidades no encontradas para revisión manual.

Uso:
    python scripts/fidelidad.py
    python scripts/fidelidad.py --provider mercury --out outputs/_evaluacion/mercury_k5
"""
import csv
import json
import glob
import argparse
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
GOLD_DIR = HERE / "gold"
OUTPUTS = ROOT / "outputs"

_STOP = {"de", "del", "la", "el", "los", "las", "un", "una", "y", "con", "oro"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return s.lower().strip()


def _candidatos(entidad: str) -> list[str]:
    base = _norm(entidad)
    cands = [base]
    if "(" in base and ")" in base:
        fuera = base[:base.index("(")].strip()
        dentro = base[base.index("(") + 1:base.index(")")].strip()
        cands += [c for c in (fuera, dentro) if c]
    return [c for c in cands if c]


def _tokens(s: str) -> set[str]:
    return {w for w in _norm(s).replace("(", " ").replace(")", " ").split()
            if len(w) >= 4 and w not in _STOP}


def _empareja(cands: list[str], extr_norm: list[str], extr_tok: list[set]) -> bool:
    for c in cands:
        ct = _tokens(c)
        for e, et in zip(extr_norm, extr_tok):
            if c and (c in e or e in c):
                return True
            if ct & et:
                return True
    return False


def _entidades_mundo(run_dir: Path) -> list[str]:
    """Todo lo que el mundo generado contiene: personajes/objetos del Organizador +
    nodos narrativos del scene graph (incluidos decorados)."""
    nombres = []
    org_path = run_dir / "salida_organizador.json"
    if org_path.exists():
        org = json.loads(org_path.read_text(encoding="utf-8"))
        bloques = list(org.get("escenas", []) or [])
        for esc in bloques:
            for p in esc.get("personajes", []) or []:
                if p.get("nombre"):
                    nombres.append(p["nombre"])
            for o in esc.get("objetos", []) or []:
                if o.get("nombre"):
                    nombres.append(o["nombre"])
        for p in org.get("personajes_globales", []) or []:
            if p.get("nombre"):
                nombres.append(p["nombre"])
        for o in org.get("objetos_globales", []) or []:
            if o.get("nombre"):
                nombres.append(o["nombre"])
    for f in glob.glob(str(run_dir / "scene_graph_escena_*.json")):
        sg = json.loads(Path(f).read_text(encoding="utf-8"))
        for n in sg.get("nodos", []) or []:
            if n.get("tipo") in ("personaje", "objeto", "decorado"):
                for campo in ("nombre", "keyword_busqueda"):
                    if n.get(campo):
                        nombres.append(n[campo])
    return list(dict.fromkeys(nombres))


def _n_escenas(run_dir: Path) -> int:
    org_path = run_dir / "salida_organizador.json"
    if org_path.exists():
        org = json.loads(org_path.read_text(encoding="utf-8"))
        return len(org.get("escenas", []) or [])
    return len(glob.glob(str(run_dir / "scene_graph_escena_*.json")))


def _corridas_validas(out: Path, provider: str) -> dict:
    """Lee resultados_corridas.csv y devuelve {corrida: fixture} de las corridas EXITOSAS
    del proveedor pedido. Garantiza no leer carpetas obsoletas o de otro texto."""
    res = out / "resultados_corridas.csv"
    validas = {}
    if not res.exists():
        return validas
    with res.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("provider") != provider:
                continue
            if str(r.get("fallo_terminal", "")).strip().lower() in ("true", "1"):
                continue
            validas[r["corrida"]] = r.get("fixture", "")
    return validas


def main() -> None:
    ap = argparse.ArgumentParser(description="Fidelidad de extracción narrativa (tab:fidelidad).")
    ap.add_argument("--provider", default="mercury")
    ap.add_argument("--out", default=str(OUTPUTS / "_evaluacion" / "mercury_k5"))
    args = ap.parse_args()

    out = Path(args.out)
    golds = [json.loads(Path(p).read_text(encoding="utf-8"))
             for p in sorted(glob.glob(str(GOLD_DIR / "*.json")))]
    if not golds:
        print("No hay anotaciones gold en scripts/gold/.")
        return

    validas = _corridas_validas(out, args.provider)   # {corrida: fixture}

    filas = []
    print(f"\n=== Fidelidad de extraccion narrativa | modelo {args.provider} ===\n")
    for g in golds:
        gid = g["id"]
        esperadas = (g.get("personajes_esperados", []) or []) + (g.get("objetos_esperados", []) or [])
        n_esp = len(esperadas)
        cands_esp = {e: _candidatos(e) for e in esperadas}

        # Solo corridas exitosas de ESTE texto (fixture coincide) presentes en el CSV.
        corridas = sorted(c for c, fx in validas.items()
                          if c.startswith(f"{gid}_{args.provider}_k") and fx == g.get("fixture"))

        coberturas, escenas_obt = [], []
        faltas = {e: 0 for e in esperadas}
        n_runs = 0
        for c in corridas:
            run_dir = OUTPUTS / f"eval_{c}"
            if not run_dir.exists():
                continue
            extr = _entidades_mundo(run_dir)
            extr_norm = [_norm(e) for e in extr]
            extr_tok = [_tokens(e) for e in extr]
            cubiertas = 0
            for e in esperadas:
                if _empareja(cands_esp[e], extr_norm, extr_tok):
                    cubiertas += 1
                else:
                    faltas[e] += 1
            coberturas.append(100.0 * cubiertas / n_esp if n_esp else 0.0)
            escenas_obt.append(_n_escenas(run_dir))
            n_runs += 1

        cobertura = round(sum(coberturas) / len(coberturas), 1) if coberturas else None
        esc_obt = round(sum(escenas_obt) / len(escenas_obt), 1) if escenas_obt else None
        no_encontradas = [e for e, n in faltas.items() if n_runs and n > n_runs / 2]

        filas.append({
            "id": gid, "titulo": g.get("titulo", ""),
            "entidades_esp": n_esp,
            "cobertura_pct": cobertura,
            "escenas_esp": g.get("escenas_esperadas"),
            "escenas_obt": esc_obt,
            "n_corridas": n_runs,
            "entidades_no_encontradas": "; ".join(no_encontradas),
        })
        cobs = f"{cobertura}%" if cobertura is not None else "-"
        print(f"  {gid} {g.get('titulo','')[:32]:32s} ent={n_esp:2d}  "
              f"cobertura={cobs:6s}  escenas esp/obt={g.get('escenas_esperadas')}/{esc_obt}  (K={n_runs})")
        if no_encontradas:
            print(f"       [revisar - no encontradas] {', '.join(no_encontradas)}")

    out.mkdir(parents=True, exist_ok=True)
    dest = out / "fidelidad.csv"
    with dest.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    print(f"\n  CSV -> {dest}\n")


if __name__ == "__main__":
    main()
