"""
Descarga 6 paisajes sonoros CC0 de Freesound para usar como música de fallback
cuando la búsqueda en vivo no encuentra nada (o Freesound está caído del todo).

Uso:
    python scripts/descargar_musica_fallback.py            # descarga los que falten
    python scripts/descargar_musica_fallback.py --force    # re-descarga todos

Solo descarga sonidos con licencia Creative Commons 0 (dominio público), así que
se pueden empaquetar en assets/ sin obligación de atribución. Guarda los MP3 en
assets/music/fallback/<bucket>.mp3, que es de donde los lee el Músico.
"""
import sys
import time
import argparse
from pathlib import Path

import requests

# La consola de Windows (cp1252) no codifica ✓/✗/→; forzamos UTF-8 en stdout.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import settings  # noqa: E402

SEARCH = "https://freesound.org/apiv2/search/text/"
DEST = Path(__file__).resolve().parent.parent / "assets" / "music" / "fallback"

# Cada bucket: lista de queries en orden de preferencia (la 2ª se prueba si la 1ª no da nada)
BUCKETS = {
    "naturaleza": ["forest birds ambience", "forest wind leaves ambience"],
    "agua":       ["ocean waves loop", "sea waves beach ambience"],
    "arido":      ["desert wind ambience", "wind howling open ambience"],
    "urbano":     ["city street crowd ambience", "town square people ambience", "medieval market crowd ambience"],
    "cosmico":    ["calm space ambient pad", "ethereal space ambient soft"],
    "interior":   ["room tone ambience", "cave drone dripping"],
}


def _buscar(query: str, api_key: str) -> list[dict]:
    """Busca CC0 ordenado por descargas, con reintento ante los 5xx intermitentes."""
    params = {
        "query":     query,
        "token":     api_key,
        "page_size": 5,
        "filter":    'license:"Creative Commons 0" duration:[40 TO 400]',
        "sort":      "downloads_desc",
        "fields":    "id,name,username,duration,license,previews,num_downloads",
    }
    for intento in range(4):
        try:
            r = requests.get(SEARCH, params=params, timeout=15)
            if r.status_code == 200:
                return r.json().get("results", [])
            if r.status_code == 401:
                print("  ERROR: API key inválida (401)")
                return []
            if 500 <= r.status_code < 600:
                espera = 1.0 * (intento + 1)
                print(f"  Freesound {r.status_code} (sobrecarga), reintento en {espera:.0f}s...")
                time.sleep(espera)
                continue
            print(f"  Freesound error {r.status_code}")
            return []
        except requests.RequestException as e:
            print(f"  Error de red ({e}), reintento...")
            time.sleep(1.0 * (intento + 1))
    return []


def _descargar(url: str, destino: Path, reintentos: int = 5) -> bool:
    """Descarga con reintento ante 5xx — el CDN de Freesound también da 504 intermitentes."""
    for intento in range(reintentos):
        ultimo = intento == reintentos - 1
        try:
            r = requests.get(url, timeout=60, stream=True)
            if r.status_code == 200:
                destino.parent.mkdir(parents=True, exist_ok=True)
                total = 0
                with open(destino, "wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
                        total += len(chunk)
                print(f"  ✓ {destino.name} — {total // 1024} KB")
                return True
            if 500 <= r.status_code < 600 and not ultimo:
                espera = 1.5 * (intento + 1)
                print(f"  CDN {r.status_code} (sobrecarga), reintento {intento + 1}/{reintentos - 1} en {espera:.0f}s...")
                time.sleep(espera)
                continue
            print(f"  Descarga falló: HTTP {r.status_code}")
            return False
        except requests.RequestException as e:
            if not ultimo:
                espera = 1.5 * (intento + 1)
                print(f"  Error descargando ({e}), reintento en {espera:.0f}s...")
                time.sleep(espera)
                continue
            print(f"  Error descargando: {e}")
            return False
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Re-descarga aunque ya exista")
    args = parser.parse_args()

    api_key = settings.freesound_api_key
    if not api_key:
        print("FREESOUND_API_KEY no configurada en .env")
        sys.exit(1)

    print(f"Destino: {DEST}\n")
    creditos = []

    for bucket, queries in BUCKETS.items():
        destino = DEST / f"{bucket}.mp3"
        if destino.exists() and not args.force:
            print(f"[{bucket}] ya existe, omitido (usa --force para re-descargar)")
            continue

        print(f"[{bucket}]")
        elegido = None
        for q in queries:
            print(f"  buscando: '{q}'")
            resultados = _buscar(q, api_key)
            if resultados:
                elegido = resultados[0]
                break

        if not elegido:
            print(f"  ✗ sin resultados CC0 para '{bucket}'")
            continue

        previews = elegido.get("previews", {})
        url = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3")
        if not url:
            print("  ✗ sin URL de preview")
            continue

        print(f"  elegido: '{elegido['name']}' por {elegido['username']} "
              f"({elegido['duration']:.0f}s, {elegido['num_downloads']} descargas)")
        if _descargar(url, destino):
            creditos.append(f"{bucket}: '{elegido['name']}' por {elegido['username']} "
                            f"(Freesound id {elegido['id']}, CC0)")
        print()

    if creditos:
        print("\n— Créditos (CC0, atribución no obligatoria pero recomendada) —")
        for c in creditos:
            print(" ", c)


if __name__ == "__main__":
    main()
