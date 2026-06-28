"""
Ensamblador — función determinística sin LLM.

Toma los outputs de Constructor, Programador y Dibujante y produce
el HTML final. Actúa como compilador/linker: sin lógica narrativa,
sin llamadas a API, completamente testeable.

Entradas:
  - SceneGraph          (Constructor)
  - SalidaProgramador   (Programador, opcional)
  - SalidaDibujante     (Dibujante, opcional)

Salida:
  - HTML standalone con scene_loader.js e interactions.js inlinados
"""

import json
from pathlib import Path
from typing import Optional

from schemas.scene_graph import SceneGraph
from schemas.escenas import Escena
from schemas.especificacion import SalidaDirector
from schemas.interacciones import SalidaProgramador
from schemas.assets import SalidaDibujante
from schemas.audio import SalidaMusico
from schemas.quiz import SalidaExaminador

from runtime_paths import recurso
SANDBOX = recurso("sandbox")


_PORTAL_LABEL = {"es": "portal de transición", "en": "next scene"}
_QUIZ_LABEL   = {"es": "cuestionario final",   "en": "final quiz"}
_INTRO_CONTINUE = {"es": "Pulsa cualquier tecla para continuar",
                   "en": "Press any key to continue"}


def ensamblar(
    scene_graph: SceneGraph,
    manifest: Optional[SalidaProgramador] = None,
    musico: Optional[SalidaMusico] = None,
    dibujante: Optional[SalidaDibujante] = None,
    escena: Optional[Escena] = None,
    director: Optional[SalidaDirector] = None,  # kept for backwards compat, unused
    next_scene_url: Optional[str] = None,
    portal_label: Optional[str] = None,
    texto_fin: Optional[str] = None,
    escenas_cielo: Optional[list] = None,
    output_path: Optional[Path] = None,
    idioma: str = "es",
    modo: str = "narrativo",
) -> str:
    """
    Genera el HTML final a partir de los outputs de los agentes.

    Retorna el HTML como string y, si se indica output_path, lo escribe en disco.
    """
    template       = (SANDBOX / "index.html").read_text(encoding="utf-8")
    personajes_code= (SANDBOX / "js" / "personajes.js").read_text(encoding="utf-8")
    loader_code    = (SANDBOX / "js" / "scene_loader.js").read_text(encoding="utf-8")
    inter_code     = (SANDBOX / "js" / "interactions.js").read_text(encoding="utf-8")
    sky_code       = (SANDBOX / "js" / "sky.js").read_text(encoding="utf-8")

    # ── Idioma + modo globales (deben inyectarse antes de cualquier otro script) ─
    html = template.replace("__IDIOMA_PLACEHOLDER__",
                            f'<script>const IDIOMA = "{idioma}"; const MODO = "{modo}";</script>')

    # ── Inline scripts ────────────────────────────────────────────────────────
    html = html.replace(
        '<script src="js/personajes.js"></script>\n<script src="js/scene_loader.js"></script>\n<script src="js/interactions.js"></script>\n<script src="js/sky.js"></script>',
        (
            f'<script>\n{personajes_code}\n</script>\n'
            f'<script>\n{loader_code}\n</script>\n'
            f'<script>\n{inter_code}\n</script>\n'
            f'<script>\n{sky_code}\n</script>'
        )
    )

    # ── SceneGraph ────────────────────────────────────────────────────────────
    scene_json = json.dumps(scene_graph.model_dump(), indent=2, ensure_ascii=False)
    html = html.replace("__SCENE_GRAPH_PLACEHOLDER__", scene_json)

    # ── Cielo ─────────────────────────────────────────────────────────────────
    cielo_json = json.dumps(scene_graph.cielo.model_dump(), ensure_ascii=False)
    html = html.replace("__CIELO_PLACEHOLDER__", cielo_json)

    # ── Manifest de interacciones ─────────────────────────────────────────────
    manifest_json = (
        json.dumps(manifest.model_dump(), indent=2, ensure_ascii=False)
        if manifest else "null"
    )
    html = html.replace("__MANIFEST_PLACEHOLDER__", manifest_json)

    # ── Audio del Músico ──────────────────────────────────────────────────────
    audio_js = "null"
    if musico and musico.pista_principal.url_preview:
        audio_js = json.dumps({
            "url_preview": musico.pista_principal.url_preview,
            "volumen":     musico.pista_principal.volumen,
            "titulo":      musico.pista_principal.titulo,
            "autor":       musico.pista_principal.autor,
        }, ensure_ascii=False)
    html = html.replace("__AUDIO_PLACEHOLDER__", audio_js)

    # ── Assets del Dibujante (rutas para inyección futura de base64) ──────────
    # Por ahora scene_loader.js ya resuelve las rutas por convención:
    #   assets/<id_escena>/<id_nodo>.png
    # Si dibujante está disponible, podemos usarlo para verificación futura.
    # El placeholder se deja preparado para la siguiente iteración.
    assets_js = _construir_assets_js(dibujante)
    if "__ASSETS_PLACEHOLDER__" in html:
        html = html.replace("__ASSETS_PLACEHOLDER__", assets_js)

    # ── URL de la siguiente escena (portal de transición) ────────────────────
    next_url_js = f'"{next_scene_url}"' if next_scene_url else "null"
    html = html.replace("__NEXT_SCENE_PLACEHOLDER__", next_url_js)

    # ── Etiqueta del portal ───────────────────────────────────────────────────
    html = html.replace("__PORTAL_LABEL_PLACEHOLDER__",
                        portal_label or _PORTAL_LABEL.get(idioma, _PORTAL_LABEL["es"]))

    # ── Intro narrativa ───────────────────────────────────────────────────────
    intro_html = _construir_intro(escena, idioma)
    html = html.replace("__INTRO_PLACEHOLDER__", intro_html)

    # ── FIN: datos para el portal dorado ─────────────────────────────────────
    fin_data_js = "null"
    if texto_fin and escenas_cielo:
        fin_data_js = json.dumps(
            {"texto_fin": texto_fin, "escenas": escenas_cielo},
            ensure_ascii=False,
        )
    html = html.replace("__FIN_DATA_PLACEHOLDER__", fin_data_js)

    # ── FIN: overlay de cierre con slideshow + typewriter ────────────────────
    fin_overlay_html = _construir_fin(texto_fin, escenas_cielo, idioma)
    html = html.replace("__FIN_OVERLAY_PLACEHOLDER__", fin_overlay_html)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")

    return html


def _construir_intro(escena: Optional[Escena], idioma: str = "es") -> str:
    """Genera el overlay de intro cinematográfico con typewriter y sonido procedural."""
    if not escena or not escena.tiene_intro or not (escena.texto_intro or "").strip():
        return ""

    texto = (escena.texto_intro or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")

    return f"""<style>
#intro-overlay {{
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    z-index: 999; display: flex; align-items: center; justify-content: center;
    background: rgba(0,0,0,0.88); opacity: 1; transition: opacity 0.9s ease;
}}
#intro-panel {{
    max-width: 580px; width: 90%; padding: 52px 60px;
    background: rgba(8,6,18,0.97);
    border: 1px solid rgba(255,255,255,0.07); border-radius: 3px;
    text-align: center; box-shadow: 0 0 100px rgba(0,0,0,0.9);
}}
#intro-text {{
    color: rgba(215,210,232,0.92); font-size: 17px; line-height: 1.95;
    font-family: 'Georgia','Times New Roman',serif;
    min-height: 60px; letter-spacing: 0.015em;
}}
#intro-continuar {{
    margin-top: 36px; color: rgba(255,255,255,0.22);
    font-size: 11px; letter-spacing: 0.18em; text-transform: uppercase;
    opacity: 0; transition: opacity 1.2s ease;
    font-family: 'Segoe UI',sans-serif;
}}
#intro-text .dato-clave {{
    color: #aef5c4; font-weight: 600;
    background: rgba(74,222,128,0.16);
    box-shadow: 0 0 10px rgba(74,222,128,0.18);
    border-radius: 3px; padding: 0 .18em;
}}
</style>
<div id="intro-overlay">
  <div id="intro-panel">
    <div id="intro-text"></div>
    <div id="intro-continuar">{_INTRO_CONTINUE.get(idioma, _INTRO_CONTINUE["es"])}</div>
  </div>
</div>
<script>
(function(){{
    window._introActiva = true;
    var _txt = "{texto}";
    var _ov  = document.getElementById('intro-overlay');
    var _tel = document.getElementById('intro-text');
    var _cnt = document.getElementById('intro-continuar');
    var _ctx = null, _i = 0, _fin = false;

    function _clik(){{
        try{{
            if(!_ctx) _ctx = new(window.AudioContext||window.webkitAudioContext)();
            var o=_ctx.createOscillator(), g=_ctx.createGain();
            o.connect(g); g.connect(_ctx.destination);
            o.frequency.value = 680 + Math.random()*380;
            g.gain.setValueAtTime(0.052,_ctx.currentTime);
            g.gain.exponentialRampToValueAtTime(0.001,_ctx.currentTime+0.042);
            o.start(); o.stop(_ctx.currentTime+0.042);
        }}catch(e){{}}
    }}

    var _chars = null;
    var _spanAct = null;
    function _ap(o){{
        if(o.m){{
            if(!_spanAct){{ _spanAct=document.createElement('span'); _spanAct.className='dato-clave'; _tel.appendChild(_spanAct); }}
            _spanAct.appendChild(document.createTextNode(o.c));
        }} else {{ _spanAct=null; _tel.appendChild(document.createTextNode(o.c)); }}
    }}
    function _escribir(){{
        if(!_chars) _chars = (window._wwChars ? window._wwChars(_txt)
                                              : _txt.split('').map(function(c){{return {{c:c,m:false}};}}));
        if(_i >= _chars.length){{ _fin=true; _cnt.style.opacity='1'; return; }}
        var o = _chars[_i++];
        _ap(o);
        if(o.c!==' ' && _i%2===0) _clik();
        setTimeout(_escribir, o.c==='.'||o.c==='…'? 320 : o.c===','? 140 : 36);
    }}

    function _cerrar(){{
        if(!_fin) return;
        _ov.style.opacity='0';
        setTimeout(function(){{ _ov.style.display='none'; window._introActiva=false; }}, 900);
    }}

    document.addEventListener('keydown',function _k(){{
        if(!_fin) return;
        window._wwEntrarFPS?.();
        _cerrar();
        document.removeEventListener('keydown',_k);
    }});
    _ov.addEventListener('click',function _c(){{
        if(!_fin) return;
        window._wwEntrarFPS?.();
        _cerrar();
        _ov.removeEventListener('click',_c);
    }});

    setTimeout(_escribir, 700);
}})();
</script>"""


_FIN_CONTINUE  = {"es": "Pulsa cualquier tecla para continuar", "en": "Press any key to continue"}
_FIN_BACK      = {"es": "Volver al inicio", "en": "Back to start"}
_FIN_QUIZ      = {"es": "Ir al cuestionario", "en": "Go to the quiz"}


def _construir_fin(texto_fin: Optional[str], escenas_cielo: Optional[list], idioma: str = "es") -> str:
    """Overlay de fin: slideshow atmosférico de todas las escenas + typewriter de conclusión."""
    if not texto_fin or not escenas_cielo:
        return ""

    texto   = texto_fin.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    esc_js  = json.dumps(escenas_cielo, ensure_ascii=False)
    back_label = _FIN_BACK.get(idioma, _FIN_BACK["es"])
    quiz_label = _FIN_QUIZ.get(idioma, _FIN_QUIZ["es"])

    return f"""<style>
#fin-overlay {{
    position: fixed; inset: 0; z-index: 998;
    display: none; flex-direction: column;
    align-items: center; justify-content: center;
    font-family: 'Segoe UI', system-ui, sans-serif;
}}
#fin-bg-a, #fin-bg-b {{
    position: absolute; inset: 0;
    transition: opacity 1.6s ease;
}}
#fin-vignette {{
    position: absolute; inset: 0;
    background: radial-gradient(ellipse at center, transparent 20%, rgba(0,0,0,0.72) 100%);
    pointer-events: none;
}}
#fin-escena-titulo {{
    position: absolute; top: 48px; left: 50%; transform: translateX(-50%);
    font-size: 10px; letter-spacing: 5px; text-transform: uppercase;
    color: rgba(255,255,255,0.28); transition: opacity 1.2s ease;
    white-space: nowrap;
}}
#fin-panel {{
    position: relative; z-index: 1;
    max-width: 600px; width: 90%; padding: 52px 60px;
    background: rgba(4,3,12,0.82);
    border: 1px solid rgba(255,255,255,0.07); border-radius: 3px;
    text-align: center; box-shadow: 0 0 120px rgba(0,0,0,0.95);
}}
#fin-text {{
    color: rgba(215,210,232,0.92); font-size: 17px; line-height: 1.95;
    font-family: 'Georgia','Times New Roman',serif;
    min-height: 60px; letter-spacing: 0.015em;
}}
#fin-text .dato-clave {{
    color: #aef5c4; font-weight: 600;
    background: rgba(74,222,128,0.16);
    box-shadow: 0 0 10px rgba(74,222,128,0.18);
    border-radius: 3px; padding: 0 .18em;
}}
#fin-continuar {{
    margin-top: 36px; color: rgba(255,255,255,0.22);
    font-size: 11px; letter-spacing: 0.18em; text-transform: uppercase;
    opacity: 0; transition: opacity 1.4s ease;
}}
#fin-volver {{
    display: none; margin-top: 28px;
    background: transparent; border: 1px solid rgba(255,200,80,0.3);
    color: rgba(255,210,100,0.8); font-family: inherit;
    font-size: 11px; letter-spacing: 4px; text-transform: uppercase;
    padding: 10px 32px; border-radius: 40px; cursor: pointer;
    transition: all 0.25s;
}}
#fin-volver:hover {{
    background: rgba(255,180,50,0.08);
    border-color: rgba(255,200,80,0.7); color: #fff;
}}
</style>
<div id="fin-overlay">
    <div id="fin-bg-a"></div>
    <div id="fin-bg-b" style="opacity:0"></div>
    <div id="fin-vignette"></div>
    <div id="fin-escena-titulo"></div>
    <div id="fin-panel">
        <div id="fin-text"></div>
        <div id="fin-continuar">{_FIN_CONTINUE.get(idioma, _FIN_CONTINUE["es"])}</div>
        <button id="fin-volver"></button>
    </div>
</div>
<script>
(function() {{
    var ESCENAS = {esc_js};
    var TEXTO   = "{texto}";

    var _bgA   = document.getElementById('fin-bg-a');
    var _bgB   = document.getElementById('fin-bg-b');
    var _titul = document.getElementById('fin-escena-titulo');
    var _tel   = document.getElementById('fin-text');
    var _cnt   = document.getElementById('fin-continuar');
    var _btn   = document.getElementById('fin-volver');
    var _ov    = document.getElementById('fin-overlay');
    var _flash = document.getElementById('portal-flash');

    var _iEsc = 0, _bgToggle = false, _fin = false, _ctx = null;

    function _grad(e) {{
        return 'radial-gradient(ellipse at 32% 28%, ' + e.color_sol + ' 0%, '
             + e.color_fondo + ' 42%, ' + e.color_ambiente + ' 100%)';
    }}

    function _setEscena(idx, el, fade) {{
        var e = ESCENAS[idx % ESCENAS.length];
        el.style.background = _grad(e);
        _titul.style.opacity = '0';
        setTimeout(function() {{
            _titul.textContent = e.titulo;
            _titul.style.opacity = '1';
        }}, fade ? 800 : 0);
    }}

    function _iniciarSlideshow() {{
        _setEscena(0, _bgA, false);
        _titul.textContent = ESCENAS[0].titulo;
        _titul.style.opacity = '1';

        setInterval(function() {{
            _iEsc++;
            _bgToggle = !_bgToggle;
            var next = _bgToggle ? _bgB : _bgA;
            var prev = _bgToggle ? _bgA : _bgB;
            _setEscena(_iEsc, next, true);
            next.style.opacity = '1';
            prev.style.opacity = '0';
        }}, 5500);
    }}

    function _clik() {{
        try {{
            if (!_ctx) _ctx = new (window.AudioContext || window.webkitAudioContext)();
            var o = _ctx.createOscillator(), g = _ctx.createGain();
            o.connect(g); g.connect(_ctx.destination);
            o.frequency.value = 680 + Math.random() * 380;
            g.gain.setValueAtTime(0.052, _ctx.currentTime);
            g.gain.exponentialRampToValueAtTime(0.001, _ctx.currentTime + 0.042);
            o.start(); o.stop(_ctx.currentTime + 0.042);
        }} catch(e) {{}}
    }}

    var _i = 0;
    var _chars = null;
    var _spanAct = null;
    function _ap(o){{
        if(o.m){{
            if(!_spanAct){{ _spanAct=document.createElement('span'); _spanAct.className='dato-clave'; _tel.appendChild(_spanAct); }}
            _spanAct.appendChild(document.createTextNode(o.c));
        }} else {{ _spanAct=null; _tel.appendChild(document.createTextNode(o.c)); }}
    }}
    function _escribir() {{
        if(!_chars) _chars = (window._wwChars ? window._wwChars(TEXTO)
                                              : TEXTO.split('').map(function(c){{return {{c:c,m:false}};}}));
        if (_i >= _chars.length) {{
            _fin = true;
            _cnt.style.opacity = '1';
            return;
        }}
        var o = _chars[_i++];
        _ap(o);
        if (o.c !== ' ' && _i % 2 === 0) _clik();
        setTimeout(_escribir, o.c === '.' || o.c === '…' ? 320 : o.c === ',' ? 140 : 36);
    }}

    function _cerrar() {{
        if (!_fin) return;
        _cnt.style.opacity = '0';
        // Botón según el destino: educativo → al cuestionario; narrativo → al inicio.
        var _quiz = (typeof NEXT_SCENE_URL !== 'undefined' && NEXT_SCENE_URL
                     && /quiz\\.html/.test(NEXT_SCENE_URL));
        _btn.textContent = _quiz ? "{quiz_label}" : "{back_label}";
        _btn.onclick = function() {{
            window.location.href = _quiz ? (NEXT_SCENE_URL + '?portal=1') : '/?upload=1';
        }};
        _btn.style.display = 'block';
    }}

    document.addEventListener('keydown', function _k(e) {{
        if (!_fin) return;
        _cerrar();
        document.removeEventListener('keydown', _k);
    }});
    _ov.addEventListener('click', function(e) {{
        if (e.target === _btn) return;
        if (!_fin) return;
        _cerrar();
    }});

    window._mostrarFinOverlay = function() {{
        _ov.style.display = 'flex';
        _iniciarSlideshow();
        // Desvanecer el flash del portal
        setTimeout(function() {{
            if (_flash) {{
                _flash.style.transition = 'opacity 0.9s ease';
                _flash.style.opacity = '0';
            }}
        }}, 350);
        setTimeout(_escribir, 1800);
    }};
}})();
</script>"""


_QUIZ_TEMPLATE = """\
<!DOCTYPE html>
<html lang="__QUIZ_LANG__">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__QUIZ_TITLE__</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#05030f;color:rgba(215,210,232,.92);font-family:'Segoe UI',system-ui,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}
.container{max-width:640px;width:100%}
.header{text-align:center;margin-bottom:36px}
.ww-tag{font-size:11px;letter-spacing:5px;text-transform:uppercase;color:rgba(255,255,255,.22);margin-bottom:10px}
.quiz-titulo{font-size:20px;font-family:'Georgia','Times New Roman',serif;color:rgba(215,210,232,.9);line-height:1.4}
.progress-wrap{height:2px;background:rgba(255,255,255,.07);border-radius:2px;margin:28px 0 8px;overflow:hidden}
.progress-fill{height:100%;background:rgba(160,200,255,.65);transition:width .4s ease;border-radius:2px}
.progress-label{font-size:11px;letter-spacing:3px;text-transform:uppercase;color:rgba(255,255,255,.2);text-align:right;margin-bottom:24px}
.card{background:rgba(8,6,18,.97);border:1px solid rgba(255,255,255,.07);border-radius:3px;padding:40px 44px;box-shadow:0 0 80px rgba(0,0,0,.75)}
.pregunta{font-size:17px;line-height:1.75;font-family:'Georgia','Times New Roman',serif;color:rgba(215,210,232,.92);margin-bottom:28px}
.opciones{display:flex;flex-direction:column;gap:9px}
.opcion{background:transparent;border:1px solid rgba(255,255,255,.1);border-radius:2px;color:rgba(215,210,232,.8);font-family:inherit;font-size:14px;line-height:1.5;padding:13px 18px;text-align:left;cursor:pointer;transition:border-color .15s,background .15s,color .15s;display:flex;gap:14px;align-items:flex-start;width:100%}
.opcion:hover:not(:disabled){border-color:rgba(160,200,255,.35);background:rgba(160,200,255,.04);color:rgba(215,210,232,1)}
.opcion:disabled{cursor:default}
.letra{font-size:10px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,.28);flex-shrink:0;margin-top:3px;min-width:12px}
.opcion.correcta{border-color:rgba(80,210,120,.7);background:rgba(80,210,120,.07);color:rgba(180,240,200,.95)}
.opcion.incorrecta{border-color:rgba(220,80,80,.45);background:rgba(220,80,80,.06);color:rgba(240,180,180,.7)}
.opcion.correcta .letra{color:rgba(80,210,120,.75)}
.opcion.incorrecta .letra{color:rgba(220,80,80,.55)}
.explicacion{display:none;margin-top:18px;padding:14px 18px;border-left:2px solid rgba(160,200,255,.28);color:rgba(180,200,220,.72);font-size:13px;line-height:1.7}
.btn-sig{display:none;margin-top:24px;width:100%;background:transparent;border:1px solid rgba(160,200,255,.18);color:rgba(160,200,255,.75);font-family:inherit;font-size:11px;letter-spacing:4px;text-transform:uppercase;padding:13px;cursor:pointer;border-radius:2px;transition:all .2s}
.btn-sig:hover{border-color:rgba(160,200,255,.55);background:rgba(160,200,255,.05);color:rgba(160,200,255,1)}
.resultado-card{text-align:center}
.orb{width:88px;height:88px;margin:0 auto 28px;border-radius:50%;background:radial-gradient(circle at 35% 35%,rgba(160,200,255,.9),rgba(60,100,220,.6),rgba(20,10,60,.9));box-shadow:0 0 40px rgba(100,160,255,.3),0 0 80px rgba(60,100,220,.12);animation:fl 3s ease-in-out infinite}
@keyframes fl{0%,100%{transform:translateY(0)}50%{transform:translateY(-9px)}}
.score-num{font-size:52px;font-family:'Georgia',serif;color:rgba(215,210,232,.95);letter-spacing:-1px;line-height:1}
.score-label{font-size:11px;color:rgba(255,255,255,.28);letter-spacing:4px;text-transform:uppercase;margin:10px 0 24px}
.mensaje{font-size:15px;line-height:1.8;font-family:'Georgia',serif;color:rgba(215,210,232,.78);max-width:400px;margin:0 auto 32px}
.btn-volver{background:transparent;border:1px solid rgba(255,200,80,.28);color:rgba(255,210,100,.75);font-family:inherit;font-size:11px;letter-spacing:4px;text-transform:uppercase;padding:12px 40px;border-radius:40px;cursor:pointer;transition:all .25s}
.btn-volver:hover{background:rgba(255,180,50,.08);border-color:rgba(255,200,80,.65);color:#fff}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div class="ww-tag" id="quiz-wwtag"></div>
    <div class="quiz-titulo" id="quiz-titulo"></div>
  </div>
  <div id="quiz-activo">
    <div class="progress-wrap"><div class="progress-fill" id="prog"></div></div>
    <div class="progress-label" id="prog-label"></div>
    <div class="card">
      <div class="pregunta" id="pregunta"></div>
      <div class="opciones" id="opciones"></div>
      <div class="explicacion" id="explicacion"></div>
      <button class="btn-sig" id="btn-sig"></button>
    </div>
  </div>
  <div id="resultado" style="display:none">
    <div class="card resultado-card">
      <div class="orb"></div>
      <div class="score-num" id="res-score"></div>
      <div class="score-label" id="quiz-score-lbl"></div>
      <div class="mensaje" id="res-msg"></div>
      <button class="btn-volver" id="quiz-btn-volver" onclick="window.location.href='/?upload=1'"></button>
    </div>
  </div>
</div>
<script>
var IDIOMA = "__QUIZ_IDIOMA__";
var _QI = {
  es:{wwtag:'WorldWeaver · Modo Educativo',progress:function(i,t){return 'Pregunta '+(i+1)+' de '+t;},next:'Siguiente pregunta →',result:'Ver resultado',done:'Completado',correct_label:'respuestas correctas',back:'Volver al inicio',msg_great:'Excelente dominio del temario. Has demostrado una comprensión profunda del contenido.',msg_good:'Buen trabajo. Tienes una sólida comprensión del temario con algunas áreas de mejora.',msg_ok:'Resultado aceptable. Te recomendamos repasar el contenido para consolidar los conceptos clave.',msg_low:'Hay conceptos que necesitan refuerzo. Explora de nuevo el mundo y repasa el temario.'},
  en:{wwtag:'WorldWeaver · Educational Mode',progress:function(i,t){return 'Question '+(i+1)+' of '+t;},next:'Next question →',result:'See result',done:'Completed',correct_label:'correct answers',back:'Back to start',msg_great:'Excellent command of the material. You have shown a deep understanding of the content.',msg_good:'Good work. You have a solid grasp of the material with some areas for improvement.',msg_ok:'Acceptable result. We recommend reviewing the content to consolidate the key concepts.',msg_low:'Some concepts need reinforcement. Explore the world again and review the material.'},
};
var _QL = _QI[IDIOMA] || _QI.es;
var QUIZ = __QUIZ_JSON__;
var idx = 0, score = 0;
var $qt   = document.getElementById('quiz-titulo');
var $prog = document.getElementById('prog');
var $lbl  = document.getElementById('prog-label');
var $preg = document.getElementById('pregunta');
var $opc  = document.getElementById('opciones');
var $exp  = document.getElementById('explicacion');
var $sig  = document.getElementById('btn-sig');
var $qa   = document.getElementById('quiz-activo');
var $res  = document.getElementById('resultado');

document.getElementById('quiz-wwtag').textContent = _QL.wwtag;
document.getElementById('quiz-score-lbl').textContent = _QL.correct_label;
document.getElementById('quiz-btn-volver').textContent = _QL.back;
$qt.textContent = QUIZ.titulo;

function cargar(i) {
  var q = QUIZ.preguntas[i];
  var total = QUIZ.preguntas.length;
  $prog.style.width = ((i / total) * 100) + '%';
  $lbl.textContent = _QL.progress(i, total);
  $preg.textContent = q.pregunta;
  $opc.innerHTML = '';
  $exp.style.display = 'none';
  $sig.style.display = 'none';
  q.opciones.forEach(function(op, oi) {
    var btn = document.createElement('button');
    btn.className = 'opcion';
    btn.innerHTML = '<span class="letra">' + op.letra + '</span><span>' + op.texto + '</span>';
    btn.onclick = (function(capturedOi) {
      return function() { if (btn.disabled) return; responder(capturedOi, q); };
    })(oi);
    $opc.appendChild(btn);
  });
}

function responder(elegidaIdx, q) {
  var btns = $opc.querySelectorAll('.opcion');
  btns.forEach(function(b) { b.disabled = true; });
  q.opciones.forEach(function(op, i) {
    if (op.correcta) btns[i].classList.add('correcta');
    else if (i === elegidaIdx) btns[i].classList.add('incorrecta');
  });
  if (q.opciones[elegidaIdx].correcta) score++;
  $exp.textContent = q.explicacion;
  $exp.style.display = 'block';
  $sig.textContent = (idx + 1 >= QUIZ.preguntas.length) ? _QL.result : _QL.next;
  $sig.style.display = 'block';
}

$sig.onclick = function() {
  idx++;
  if (idx >= QUIZ.preguntas.length) mostrarResultado();
  else cargar(idx);
};

function mostrarResultado() {
  $qa.style.display = 'none';
  $res.style.display = 'block';
  $prog.style.width = '100%';
  $lbl.textContent = _QL.done;
  var total = QUIZ.preguntas.length;
  document.getElementById('res-score').textContent = score + ' / ' + total;
  var pct = score / total;
  var msg;
  if (pct >= 0.875) msg = _QL.msg_great;
  else if (pct >= 0.625) msg = _QL.msg_good;
  else if (pct >= 0.375) msg = _QL.msg_ok;
  else msg = _QL.msg_low;
  document.getElementById('res-msg').textContent = msg;
}

cargar(0);
</script>
<script>
(function(){
  const a = new Audio('/assets/music/quizz.mp3');
  a.loop = true; a.volume = 0;
  function fadeIn(){ a.volume = Math.min(0.38, a.volume + 0.38/40); if(a.volume < 0.38) setTimeout(fadeIn, 50); }
  const start = () => { a.play().then(fadeIn).catch(()=>{}); document.removeEventListener('click', start); };
  // Intenta sonar de inmediato; si el navegador bloquea el autoplay, arranca al primer clic.
  a.play().then(fadeIn).catch(() => document.addEventListener('click', start, { once: true }));
})();
</script>
</body>
</html>"""


def generar_quiz_html(salida: SalidaExaminador, output_path: Path, idioma: str = "es") -> str:
    """Genera el HTML standalone del cuestionario final."""
    _QUIZ_TITLES = {"es": "Cuestionario — WorldWeaver", "en": "Quiz — WorldWeaver"}
    quiz_json = json.dumps(salida.model_dump(), indent=2, ensure_ascii=False)
    html = _QUIZ_TEMPLATE.replace("__QUIZ_JSON__", quiz_json)
    html = html.replace("__QUIZ_IDIOMA__", idioma)
    html = html.replace("__QUIZ_LANG__", idioma)
    html = html.replace("__QUIZ_TITLE__", _QUIZ_TITLES.get(idioma, _QUIZ_TITLES["es"]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return html


def _construir_assets_js(dibujante: Optional[SalidaDibujante]) -> str:
    """
    Genera un objeto JS con las rutas de assets disponibles.
    Permite que scene_loader.js sepa qué PNGs existen sin hacer peticiones 404.
    """
    if not dibujante:
        return "{}"

    assets = {
        asset.id_elemento: asset.ruta_png
        for asset in dibujante.assets
    }
    return json.dumps(assets, ensure_ascii=False)
