"""
Genera un HTML standalone para probar TODO el catálogo de sonidos procedimentales,
extrayendo el objeto `_SFX` real de sandbox/js/interactions.js (así el preview suena
exactamente como en el juego). Re-ejecútalo tras tocar los sonidos.

    python scripts/build_sound_preview.py
    → escribe sound_preview.html en la raíz de worldweaver/ (doble clic para abrir)
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / "sandbox" / "js" / "interactions.js").read_text(encoding="utf-8")

# Extraer el bloque `const _SFX = { ... };` (hasta justo antes de window._sfxPortal)
ini = JS.index("const _SFX = {")
fin = JS.index("window._sfxPortal")
sfx_block = JS[ini:fin].rstrip()

# Grupos del catálogo: (titulo, [(nombre_metodo, etiqueta, descripcion)])
GRUPOS = [
    ("Catálogo «sonido» · Expresión del ser", "#7fd3ff", [
        ("suave",    "suave",    "suspirar, rezar, murmurar, llorar"),
        ("criatura", "criatura", "ladrar, gruñir, rugido animal, piar"),
        ("ritual",   "ritual",   "invocar, conjurar, meditar, bendecir"),
        ("esfuerzo", "esfuerzo", "golpear, empujar, forcejear, atacar"),
        ("alegria",  "alegria",  "reír, celebrar, bailar, aplaudir"),
    ]),
    ("Catálogo «sonido» · Objeto / elemento", "#ffcf7a", [
        ("vibrar", "vibrar", "zumbido con trémolo (máquina, cristal, portal)"),
        ("rugir",  "rugir",  "retumbo grave (motor, trueno, derrumbe)"),
        ("metal",  "metal",  "golpe metálico resonante (gong, espada, campana)"),
        ("agua",   "agua",   "chapoteo / líquido (fuente, poción, pozo)"),
        ("magico", "magico", "destello/chispa (hechizo, encantamiento)"),
    ]),
    ("Default de acción (cuando sonido = null)", "#b8b0ff", [
        ("accion", "accion", "toque neutro de confirmación"),
    ]),
    ("Efectos ligados a interacción (automáticos)", "#9fe6b0", [
        ("recoger",     "recoger",     "susurro de papel (coger objeto)"),
        ("examinar",    "examinar",    "clic metálico + tono (examinar)"),
        ("activarOn",   "activar ON",  "click ascendente"),
        ("activarOff",  "activar OFF", "click descendente"),
        ("abrir",       "abrir",       "crujido resonante (puerta/cofre)"),
        ("llama",       "llama",       "crepitar de fuego"),
        ("brillo",      "brillo",      "cascada mágica aguda"),
        ("aparecer",    "aparecer",    "whoosh ascendente + ding"),
        ("desaparecer", "desaparecer", "whoosh descendente"),
        ("sacudir",     "sacudir",     "traqueteo irregular"),
        ("escapar",     "escapar",     "aleteo (huida)"),
        ("usarCon",     "usarCon",     "arpegio de dos notas (combinar)"),
        ("faseAvance",  "faseAvance",  "arpegio C-E-G-C5 (avanzar de fase)"),
        ("portal",      "portal",      "whoosh dramático de transición"),
    ]),
]

import json as _json
grupos_js = _json.dumps(GRUPOS, ensure_ascii=False)

HTML = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WorldWeaver · Catálogo de sonidos</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 38px 28px 60px; font-family: -apple-system, Segoe UI, Roboto, sans-serif;
    background: radial-gradient(1200px 600px at 50% -10%, #1b1d2e, #0a0b12 70%); color: #e8e9f0;
  }
  h1 { font-size: 22px; font-weight: 700; margin: 0 0 4px; letter-spacing: .3px; }
  .hint { color: #8b8da0; font-size: 13px; margin: 0 0 30px; }
  .grupo { margin-bottom: 34px; }
  .grupo h2 {
    font-size: 12px; text-transform: uppercase; letter-spacing: 2px; font-weight: 700;
    margin: 0 0 14px; padding-bottom: 7px; border-bottom: 1px solid rgba(255,255,255,.08);
  }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 12px; }
  .snd {
    cursor: pointer; text-align: left; border: 1px solid rgba(255,255,255,.10);
    background: rgba(255,255,255,.035); border-radius: 13px; padding: 13px 15px;
    transition: transform .1s, background .15s, border-color .15s; color: inherit;
  }
  .snd:hover { background: rgba(255,255,255,.08); transform: translateY(-2px); }
  .snd:active { transform: scale(.97); }
  .snd .n { font-size: 15px; font-weight: 700; font-family: ui-monospace, Menlo, monospace; }
  .snd .d { font-size: 11.5px; color: #9b9db2; margin-top: 4px; line-height: 1.4; }
  .snd.playing { border-color: currentColor; box-shadow: 0 0 0 1px currentColor inset; }
  #status { font-size: 13px; color: #9b9db2; margin: 0 0 26px; }
  #status b { color: #ffcf7a; }
  #status button { cursor: pointer; background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.15);
    color: #e8e9f0; border-radius: 8px; padding: 5px 12px; font-size: 12px; }
  #status button:hover { background: rgba(255,255,255,.16); }
</style>
</head>
<body>
<h1>🔊 Catálogo de sonidos · WorldWeaver</h1>
<p class="hint">Haz clic en cualquier botón para oírlo. Todo se sintetiza en vivo con Web Audio (sin archivos). Sube el volumen del sistema.</p>
<div id="status">build __STAMP__ &nbsp;·&nbsp; Estado del audio: <b id="st">sin iniciar</b>
  &nbsp;·&nbsp; <button id="enable">▶ Activar sonido</button>
  &nbsp;·&nbsp; <button id="test">🔔 Pitido de prueba</button></div>
<div id="root"></div>

<script>
let _twCtx = null;
__SFX_BLOCK__

const stEl = document.getElementById('st');
function setSt(s) { if (stEl) stEl.textContent = s; }
window.addEventListener('error', e => setSt('ERROR JS: ' + e.message));

// Ejecuta fn(ctx) solo cuando el contexto esté 'running'. resume() es ASÍNCRONO:
// si el sonido se programa antes de que el contexto arranque, no suena.
function whenReady(fn) {
  let ctx;
  try { ctx = _SFX._c(); } catch (e) { setSt('ERROR creando contexto: ' + e.message); return; }
  if (!ctx) { setSt('sin AudioContext (navegador sin Web Audio)'); return; }
  if (ctx.state === 'running') { fn(ctx); return; }
  ctx.resume().then(() => fn(ctx)).catch(e => setSt('resume() ERROR: ' + e.message));
}

document.getElementById('enable').onclick = () =>
  whenReady(ctx => setSt('contexto: ' + ctx.state + ' · sampleRate ' + ctx.sampleRate));

// Pitido de prueba mínimo (oscilador puro): descarta si el problema es Web Audio en sí
document.getElementById('test').onclick = () => whenReady(ctx => {
  const o = ctx.createOscillator(), g = ctx.createGain();
  o.connect(g); g.connect(ctx.destination);
  o.type = 'sine'; o.frequency.value = 660;
  g.gain.setValueAtTime(0.2, ctx.currentTime);
  g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
  o.start(); o.stop(ctx.currentTime + 0.42);
  setSt('PITIDO enviado · contexto: ' + ctx.state);
});

function play(name, el) {
  whenReady(ctx => {
    try {
      // Llamada como método (_SFX.x()) para conservar `this === _SFX`; con
      // (_SFX[name]||fn)() se pierde y this._c() falla.
      if (typeof _SFX[name] === 'function') _SFX[name]();
      else { setSt('no existe _SFX.' + name); return; }
      setSt('sono "' + name + '" · contexto: ' + ctx.state);
    } catch (e) { setSt('ERROR en "' + name + '": ' + e.message); }
  });
  if (el) { el.classList.add('playing'); setTimeout(() => el.classList.remove('playing'), 350); }
}

const GRUPOS = __GRUPOS__;
const root = document.getElementById('root');
for (const [titulo, color, sonidos] of GRUPOS) {
  const g = document.createElement('div'); g.className = 'grupo';
  const h = document.createElement('h2'); h.textContent = titulo; h.style.color = color;
  g.appendChild(h);
  const grid = document.createElement('div'); grid.className = 'grid';
  for (const [name, label, desc] of sonidos) {
    const b = document.createElement('button');
    b.className = 'snd'; b.style.color = color;
    b.innerHTML = '<div class="n" style="color:#e8e9f0">' + label + '</div><div class="d">' + desc + '</div>';
    b.onclick = () => play(name, b);
    grid.appendChild(b);
  }
  g.appendChild(grid); root.appendChild(g);
}
</script>
</body>
</html>
"""

import time as _time
HTML = (HTML.replace("__SFX_BLOCK__", sfx_block)
            .replace("__GRUPOS__", grupos_js)
            .replace("__STAMP__", _time.strftime("%H:%M:%S")))
out = ROOT / "sound_preview.html"
out.write_text(HTML, encoding="utf-8")
print(f"[ok] {out}")
