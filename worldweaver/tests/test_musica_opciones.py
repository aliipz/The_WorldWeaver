"""
Muestra los top resultados de Freesound para varias queries ambientales.
Abre las URLs en el navegador para escucharlas y elige cuál quieres como fallback.

Uso:
    python worldweaver/tests/test_musica_opciones.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from config.settings import settings

FREESOUND_SEARCH = "https://freesound.org/apiv2/search/text/"

QUERIES = [
    "nature ambience loop",
    "forest birds ambience",
    "wind outdoor ambience",
    "cinematic ambient drone",
    "magical forest ambience",
    "medieval tavern ambience",
    "mysterious cave drone",
    "ocean waves soundscape",
    "night insects ambience",
    "fantasy ambient loop",
]


def buscar(query: str, api_key: str, n: int = 4) -> list[dict]:
    params = {
        "query":     query,
        "token":     api_key,
        "fields":    "id,name,username,duration,previews,avg_rating",
        "filter":    "duration:[30 TO 600]",
        "sort":      "rating_desc",
        "page_size": n,
    }
    r = requests.get(FREESOUND_SEARCH, params=params, timeout=10)
    if r.status_code != 200:
        return []
    return r.json().get("results", [])


def main():
    api_key = settings.freesound_api_key
    if not api_key:
        print("ERROR: No hay FREESOUND_API_KEY en el .env")
        return

    print("\n" + "="*70)
    print("  WorldWeaver — Opciones de música ambiente")
    print("="*70)

    for query in QUERIES:
        resultados = buscar(query, api_key)
        if not resultados:
            continue

        print(f"\n── Query: \"{query}\" ──────────────────────────────────")
        for i, r in enumerate(resultados, 1):
            previews = r.get("previews", {})
            url = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3") or "—"
            dur = round(r.get("duration", 0))
            rating = round(r.get("avg_rating", 0), 1)
            print(f"  [{i}] {r['name']} — {r['username']} ({dur}s, ★{rating})")
            print(f"      {url}")

    print("\n" + "="*70)
    print("  Abre las URLs en el navegador para escucharlas.")
    print("  Dile a Claude cuál quieres como fallback (url o nombre).")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
