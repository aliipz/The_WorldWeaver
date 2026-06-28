"""
Parchea los preview HTML ya horneados para aplicar (sin regenerar con LLM):
  1. Cap del volumen de música + slider de volumen persistido (index.html inline).
  2. SFX de acción más brillantes (suave / criatura / esfuerzo) en interactions.js inline.

Uso:
    python scripts/patch_audio_previews.py --dry  mundo1 mundo2 ...
    python scripts/patch_audio_previews.py        mundo1 mundo2 ...

Cada reemplazo se verifica: si el string viejo no aparece (p. ej. mundo generado
con otra versión), se reporta y se omite ese reemplazo en ese fichero — nunca
corrompe el resto.
"""
import sys
from pathlib import Path

OUTPUTS = Path(__file__).resolve().parent.parent / "outputs"

# ── SFX (interactions.js inline) — tokens únicos, indentación-agnósticos ──────
SFX = [
    # suave
    ("f.type='lowpass'; f.frequency.value=820;",
     "f.type='lowpass'; f.frequency.value=1150;"),
    ("g.gain.setValueAtTime(0,t); g.gain.linearRampToValueAtTime(0.15,t+0.14);",
     "g.gain.setValueAtTime(0,t); g.gain.linearRampToValueAtTime(0.24,t+0.14);"),
    ("g.gain.setValueAtTime(0.15,t+0.34); g.gain.exponentialRampToValueAtTime(0.001,t+dur);",
     "g.gain.setValueAtTime(0.24,t+0.34); g.gain.exponentialRampToValueAtTime(0.001,t+dur);"),
    ("g2.gain.setValueAtTime(0,t); g2.gain.linearRampToValueAtTime(0.055,t+0.18);",
     "g2.gain.setValueAtTime(0,t); g2.gain.linearRampToValueAtTime(0.10,t+0.18);"),
    ("g2.gain.setValueAtTime(0.055,t+0.34); g2.gain.exponentialRampToValueAtTime(0.001,t+dur);",
     "g2.gain.setValueAtTime(0.10,t+0.34); g2.gain.exponentialRampToValueAtTime(0.001,t+dur);"),
    # criatura
    ("lp.type='lowpass'; lp.frequency.value=380;",
     "lp.type='lowpass'; lp.frequency.value=620;"),
    ("const g=c.createGain(); g.gain.value=0.95;",
     "const g=c.createGain(); g.gain.value=1.05;"),
    # esfuerzo
    ("f.frequency.setValueAtTime(220,t); f.frequency.exponentialRampToValueAtTime(70,t+dur);",
     "f.frequency.setValueAtTime(260,t); f.frequency.exponentialRampToValueAtTime(110,t+dur);"),
    ("g.gain.setValueAtTime(0,t); g.gain.linearRampToValueAtTime(0.55,t+0.06);",
     "g.gain.setValueAtTime(0,t); g.gain.linearRampToValueAtTime(0.6,t+0.06);"),
    ("g.gain.setValueAtTime(0.55,t+0.18); g.gain.exponentialRampToValueAtTime(0.001,t+dur);",
     "g.gain.setValueAtTime(0.6,t+0.18); g.gain.exponentialRampToValueAtTime(0.001,t+dur);"),
    ("o.frequency.setValueAtTime(110,t); o.frequency.exponentialRampToValueAtTime(85,t+dur);",
     "o.frequency.setValueAtTime(150,t); o.frequency.exponentialRampToValueAtTime(110,t+dur);"),
    ("g2.gain.setValueAtTime(0,t); g2.gain.linearRampToValueAtTime(0.08,t+0.08);",
     "g2.gain.setValueAtTime(0,t); g2.gain.linearRampToValueAtTime(0.13,t+0.08);"),
    ("g2.gain.setValueAtTime(0.08,t+0.22); g2.gain.exponentialRampToValueAtTime(0.001,t+dur);",
     "g2.gain.setValueAtTime(0.13,t+0.22); g2.gain.exponentialRampToValueAtTime(0.001,t+dur);"),
]

# ── index.html: CSS del control (ancla en la regla .sonando) ──────────────────
CSS_OLD = "#audio-btn.sonando { color: #a8d8a8; border-color: rgba(100,200,100,0.3); }"
CSS_NEW = CSS_OLD + """

        #audio-ctrl {
            position: fixed; bottom: 16px; left: 16px; z-index: 50;
            display: flex; align-items: center; gap: 9px;
            padding: 6px 11px; border-radius: 10px;
            background: rgba(0,0,0,0.38);
            opacity: 0.42; transition: opacity .25s;
        }
        #audio-ctrl:hover { opacity: 1; }
        #audio-vol {
            -webkit-appearance: none; appearance: none;
            width: 74px; height: 4px; border-radius: 3px;
            background: rgba(255,255,255,0.22);
            pointer-events: auto; cursor: pointer; outline: none;
        }
        #audio-vol::-webkit-slider-thumb {
            -webkit-appearance: none; appearance: none;
            width: 12px; height: 12px; border-radius: 50%;
            background: #a8d8a8; cursor: pointer;
        }
        #audio-vol::-moz-range-thumb {
            width: 12px; height: 12px; border: none; border-radius: 50%;
            background: #a8d8a8; cursor: pointer;
        }"""

# ── index.html: quitar botón del contenedor oculto ────────────────────────────
BTN_OLD = '<button id="audio-btn" onclick="toggleAudio()" style="display:none"></button>'
BTN_NEW = ""

# ── index.html: insertar control visible antes de #hint ───────────────────────
CTRL_OLD = '<div id="hint"></div>'
CTRL_NEW = '''<!-- Control de música visible: mute + volumen (persistido) -->
<div id="audio-ctrl" style="display:none">
    <button id="audio-btn" onclick="toggleAudio()"></button>
    <input type="range" id="audio-vol" min="0" max="0.5" step="0.01" title="Volumen música">
</div>
<div id="hint"></div>'''

# ── index.html: reescribir el IIFE de audio (cap + slider + persistencia) ──────
JS_OLD = """    const btn = document.getElementById('audio-btn');
    btn.style.display = 'block';

    let silenciado = false;
    const volTarget = AUDIO_DATA.volumen ?? 0.25;

    // Fade in al cargar — requiere gesto del usuario (política del browser)
    function iniciarAudio() {
        audio.play().then(() => {
            btn.classList.add('sonando');
            // Fade in suave en 3 segundos
            let v = 0;
            const step = volTarget / 60;
            const fade = setInterval(() => {
                v = Math.min(v + step, volTarget);
                audio.volume = v;
                if (v >= volTarget) clearInterval(fade);
            }, 50);
        }).catch(() => {});
    }

    // El browser bloquea autoplay sin gesto — arrancamos en el primer click/tecla
    const arrancar = () => { iniciarAudio(); document.removeEventListener('click', arrancar); document.removeEventListener('keydown', arrancar); };
    document.addEventListener('click', arrancar);
    document.addEventListener('keydown', arrancar);

    btn.textContent = _wwUI('audio_on');
    window.toggleAudio = function() {
        silenciado = !silenciado;
        audio.volume = silenciado ? 0 : volTarget;
        btn.textContent = silenciado ? _wwUI('audio_off') : _wwUI('audio_on');
        btn.classList.toggle('sonando', !silenciado);
    };
})();"""

JS_NEW = """    const btn    = document.getElementById('audio-btn');
    const slider = document.getElementById('audio-vol');
    const ctrl   = document.getElementById('audio-ctrl');
    if (ctrl) ctrl.style.display = 'flex';

    // La música es FONDO: aunque el Músico genere un volumen alto (algunos mundos
    // traen 0.6), lo capamos para que no tape los SFX de acción. El usuario puede
    // subirlo/bajarlo con el slider (persistido en localStorage).
    const VOL_MAX = 0.5;
    const VOL_DEF = Math.min(AUDIO_DATA.volumen ?? 0.25, 0.32);
    let volTarget = VOL_DEF;
    const guardado = parseFloat(localStorage.getItem('ww_music_vol'));
    if (!isNaN(guardado)) volTarget = Math.min(VOL_MAX, Math.max(0, guardado));

    let silenciado = false;
    if (slider) { slider.max = VOL_MAX; slider.value = volTarget; }

    // Fade in al cargar — requiere gesto del usuario (política del browser)
    function iniciarAudio() {
        audio.play().then(() => {
            btn.classList.add('sonando');
            // Fade in suave en 3 segundos hasta el volumen objetivo actual
            let v = 0;
            const step = Math.max(volTarget, 0.0001) / 60;
            const fade = setInterval(() => {
                v = Math.min(v + step, volTarget);
                if (!silenciado) audio.volume = v;
                if (v >= volTarget) clearInterval(fade);
            }, 50);
        }).catch(() => {});
    }

    // El browser bloquea autoplay sin gesto — arrancamos en el primer click/tecla
    const arrancar = () => { iniciarAudio(); document.removeEventListener('click', arrancar); document.removeEventListener('keydown', arrancar); };
    document.addEventListener('click', arrancar);
    document.addEventListener('keydown', arrancar);

    btn.textContent = _wwUI('audio_on');
    window.toggleAudio = function() {
        silenciado = !silenciado;
        audio.volume = silenciado ? 0 : volTarget;
        btn.textContent = silenciado ? _wwUI('audio_off') : _wwUI('audio_on');
        btn.classList.toggle('sonando', !silenciado);
    };

    if (slider) {
        slider.addEventListener('input', () => {
            volTarget = parseFloat(slider.value);
            localStorage.setItem('ww_music_vol', String(volTarget));
            if (!silenciado) audio.volume = volTarget;
        });
        // Evita que arrastrar el slider cuente como gesto de movimiento/click 3D
        slider.addEventListener('click',     e => e.stopPropagation());
        slider.addEventListener('mousedown', e => e.stopPropagation());
    }
})();"""

REEMPLAZOS = SFX + [
    (CSS_OLD, CSS_NEW),
    (BTN_OLD, BTN_NEW),
    (CTRL_OLD, CTRL_NEW),
    (JS_OLD, JS_NEW),
]


def parchear(world: str, dry: bool) -> None:
    wdir = OUTPUTS / world
    previews = sorted(wdir.glob("preview_escena_*.html"))
    if not previews:
        print(f"  ⚠ {world}: sin previews")
        return
    for p in previews:
        txt = p.read_text(encoding="utf-8")
        orig = txt
        faltan = []
        for old, new in REEMPLAZOS:
            n = txt.count(old)
            if n == 0:
                # ya aplicado o no presente: solo avisa si tampoco está el nuevo
                if new and new not in txt:
                    faltan.append(old[:50])
                continue
            txt = txt.replace(old, new)
        estado = "OK" if not faltan else f"FALTAN {len(faltan)}"
        if faltan:
            for f in faltan:
                print(f"      · no encontrado: {f!r}")
        if dry:
            print(f"  [dry] {p.name}: {estado} (cambia={txt != orig})")
        else:
            if txt != orig:
                p.write_text(txt, encoding="utf-8")
            print(f"  [write] {p.name}: {estado} (cambiado={txt != orig})")


if __name__ == "__main__":
    args = sys.argv[1:]
    dry = "--dry" in args
    worlds = [a for a in args if a != "--dry"]
    if not worlds:
        print("Uso: python scripts/patch_audio_previews.py [--dry] mundo1 mundo2 ...")
        sys.exit(1)
    for w in worlds:
        print(f"\n=== {w} ===")
        parchear(w, dry)
