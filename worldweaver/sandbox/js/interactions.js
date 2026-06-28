/**
 * WorldWeaver — interactions.js
 */

// ── Resaltado de datos clave (modo educativo) ───────────────────────────────────
// El Organizador/Programador marcan los datos a aprender con ==texto==. En modo
// educativo se pintan en verde; en narrativo (o si se cuela una marca) se limpian.
// Funciones globales (window) — también las usan los overlays de intro/fin.
function _wwEduActivo() {
    return (typeof MODO !== 'undefined' && MODO === 'educativo');
}
function _wwSeg(texto) {
    // Parte el texto en segmentos {t, m}: quita SIEMPRE los marcadores == ==,
    // y solo marca (m=true) cuando el modo es educativo.
    const s = String(texto == null ? '' : texto);
    const edu = _wwEduActivo();
    const out = [];
    const re = /==(.+?)==/g;
    let last = 0, mm;
    while ((mm = re.exec(s))) {
        if (mm.index > last) out.push({ t: s.slice(last, mm.index), m: false });
        out.push({ t: mm[1], m: edu });
        last = re.lastIndex;
    }
    if (last < s.length) out.push({ t: s.slice(last), m: false });
    return out;
}
function _wwChars(texto) {
    // Lista de caracteres con su flag de marca, para el typewriter.
    const out = [];
    _wwSeg(texto).forEach(function (seg) {
        for (const ch of seg.t) out.push({ c: ch, m: seg.m });
    });
    return out;
}
function _wwEscape(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function _wwResaltar(texto) {
    // HTML seguro con los datos clave envueltos en <span class="dato-clave">.
    return _wwSeg(texto).map(function (seg) {
        const safe = _wwEscape(seg.t).replace(/\n/g, '<br>');
        return seg.m ? '<span class="dato-clave">' + safe + '</span>' : safe;
    }).join('');
}

// ── i18n ──────────────────────────────────────────────────────────────────────
const _T_DATA = {
    es: {
        talk:       nombre => `<kbd>E</kbd> Hablar con <em>${nombre}</em>`,
        give:       (t, nombre) => `<kbd>E</kbd> Entregar <em>${t}</em> a <em>${nombre}</em>`,
        carrying:   t => `[llevas ${t}]`,
        examine:    nombre => `<kbd>E</kbd> Examinar <em>${nombre}</em>`,
        deactivate: nombre => `Desactivar <em>${nombre}</em>`,
        activate:   nombre => `Activar <em>${nombre}</em>`,
        pickup:     nombre => `<kbd>E</kbd> Recoger <em>${nombre}</em>`,
        use_with:   (item, nombre) => `<kbd>E</kbd> Usar <em>${item}</em> con <em>${nombre}</em>`,
        need_item:  item => `<span class="int-hint-locked">⚬ Necesitas <em>${item}</em></span>`,
        need_to_continue: item => `Necesitas ${item} para continuar.`,
        talk_label: nombre => `Habla con ${nombre}`,
        explore_zone: 'Explora la zona',
        activate_label: nombre => `Activa ${nombre}`,
        discover_label: nombre => `Descubre ${nombre}`,
        examine_label:  nombre => `Examina ${nombre}`,
        pickup_label:   nombre => `Recoge ${nombre}`,
        use_with_label: nombre => `Usa con ${nombre}`,
        saved_item:     t => `Has guardado: ${t}`,
        info:       'Información',
        exit:       'salir',
        close:      'cerrar',
        keep_drop:  '<kbd>G</kbd> Guardar &nbsp;&nbsp; <kbd>E</kbd> Soltar',
        drag_rotate: 'Arrastra para girar',
        vocab_counter: (n, max) => `Fallos: ${n}/${max}`,
        vocab_wrong:   rem => `Ese no es. Te ${rem === 1 ? 'queda' : 'quedan'} ${rem} ${rem === 1 ? 'intento' : 'intentos'}.`,
        vocab_reset:   'Demasiados fallos. Reiniciando el reto…',
    },
    en: {
        talk:       nombre => `<kbd>E</kbd> Talk to <em>${nombre}</em>`,
        give:       (t, nombre) => `<kbd>E</kbd> Give <em>${t}</em> to <em>${nombre}</em>`,
        carrying:   t => `[carrying ${t}]`,
        examine:    nombre => `<kbd>E</kbd> Examine <em>${nombre}</em>`,
        deactivate: nombre => `Deactivate <em>${nombre}</em>`,
        activate:   nombre => `Activate <em>${nombre}</em>`,
        pickup:     nombre => `<kbd>E</kbd> Pick up <em>${nombre}</em>`,
        use_with:   (item, nombre) => `<kbd>E</kbd> Use <em>${item}</em> with <em>${nombre}</em>`,
        need_item:  item => `<span class="int-hint-locked">⚬ You need <em>${item}</em></span>`,
        need_to_continue: item => `You need ${item} to continue.`,
        talk_label: nombre => `Talk to ${nombre}`,
        explore_zone: 'Explore the area',
        activate_label: nombre => `Activate ${nombre}`,
        discover_label: nombre => `Discover ${nombre}`,
        examine_label:  nombre => `Examine ${nombre}`,
        pickup_label:   nombre => `Pick up ${nombre}`,
        use_with_label: nombre => `Use with ${nombre}`,
        saved_item:     t => `You saved: ${t}`,
        info:       'Info',
        exit:       'exit',
        close:      'close',
        keep_drop:  '<kbd>G</kbd> Keep &nbsp;&nbsp; <kbd>E</kbd> Drop',
        drag_rotate: 'Drag to rotate',
        vocab_counter: (n, max) => `Mistakes: ${n}/${max}`,
        vocab_wrong:   rem => `Not that one. ${rem} ${rem === 1 ? 'try' : 'tries'} left.`,
        vocab_reset:   'Too many mistakes. Restarting the challenge…',
    },
};
const _T = k => {
    const lang = (typeof IDIOMA !== 'undefined' ? IDIOMA : 'es');
    return (_T_DATA[lang] || _T_DATA.es)[k];
};

window.iniciarInteracciones = function (manifest, scene, camera, renderer) {

    if (!manifest) {
        console.warn('[Interactions] Manifest ausente — sin interacciones.');
        return { update: () => {} };
    }

    _inyectarEstilos();

    // ── Elementos UI ──────────────────────────────────────────────────────────
    const elHint      = _crearEl('div', 'int-hint');
    const elDialogo   = _crearEl('div', 'int-dialogo');
    const elExaminar  = _crearEl('div', 'int-examinar');
    const elActivacion= _crearEl('div', 'int-activacion');
    const elLore      = _crearEl('div', 'int-lore');
    const elTracker   = _crearEl('div', 'obj-tracker');
    const elAccion    = _crearEl('div', 'int-accion');

    // ── Mapa de nodos ─────────────────────────────────────────────────────────
    // obj3d se resuelve lazily en update() — los modelos glTF cargan asíncronamente.
    const mapa = {};
    let _personajeHablando = null;   // nodo_id del personaje con diálogo activo

    for (const pm of (manifest.personajes || [])) {
        mapa[pm.id_nodo] = {
            tipo:              'personaje',
            fase_aparicion:    pm.fase_aparicion,
            dialogos:          pm.dialogos || [],
            dialogos_con_item: pm.dialogos_con_item || [],
            dispara:           pm.dispara || null,
            acciones:          pm.acciones || [],
            ficha_info:        pm.ficha_info || null,
            obj3d:             null,
            indicePunto:       0,
            luzGuia:           null,
            spriteAura:        null,
        };
    }

    for (const om of (manifest.objetos || [])) {
        if (mapa[om.id_nodo]) continue;  // personaje tiene prioridad sobre objeto
        mapa[om.id_nodo] = {
            tipo:           'objeto',
            fase_aparicion: om.fase_aparicion,
            interaccion:    om.interaccion,
            acciones:       om.acciones || [],
            proximidad:     om.proximidad || null,
            dispara:        om.dispara || null,
            obj3d:          null,
            indicePunto:    0,
            luzGuia:        null,
            spriteAura:     null,
        };
    }

    // ── Textura de "..." (generada una sola vez) ──────────────────────────────
    const _texturaPuntos = (() => {
        const cv = document.createElement('canvas');
        cv.width = 128; cv.height = 72;
        const ctx = cv.getContext('2d');
        // Burbuja blanca redondeada
        ctx.fillStyle = 'rgba(255,255,255,0.92)';
        ctx.beginPath();
        ctx.roundRect(4, 4, 120, 52, 14);
        ctx.fill();
        // Puntos animados — tres círculos
        ctx.fillStyle = '#333';
        for (let i = 0; i < 3; i++) {
            ctx.beginPath();
            ctx.arc(34 + i * 30, 30, 8, 0, Math.PI * 2);
            ctx.fill();
        }
        return new THREE.CanvasTexture(cv);
    })();

    // ── Textura de aura (generada una sola vez) ───────────────────────────────
    const _texturaAura = (() => {
        const sz = 256, cv = document.createElement('canvas');
        cv.width = cv.height = sz;
        const ctx = cv.getContext('2d');
        const cx = sz / 2;
        // Núcleo brillante muy concentrado con caída rápida
        const g = ctx.createRadialGradient(cx, cx, 0, cx, cx, cx);
        g.addColorStop(0.00, 'rgba(255, 252, 200, 1.00)');  // núcleo blanco-amarillo
        g.addColorStop(0.18, 'rgba(255, 220,  60, 0.90)');  // oro intenso
        g.addColorStop(0.38, 'rgba(255, 170,   0, 0.35)');  // caída rápida
        g.addColorStop(0.58, 'rgba(255, 110,   0, 0.08)');  // casi transparente
        g.addColorStop(1.00, 'rgba(255,  60,   0, 0.00)');  // borde invisible
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, sz, sz);
        return new THREE.CanvasTexture(cv);
    })();

    // ── Estado de fases ───────────────────────────────────────────────────────
    const FASES = manifest.fases || [];
    const ZONAS = manifest.zonas_narrativas || [];

    // Examen de vocabulario: el avance se gatea por ENTREGA al guía (no por recoger).
    const EXAMEN_VOCAB = !!manifest.examen_vocabulario;
    // Examen conceptual (Tipo B): el avance se gatea por elegir la OPCIÓN correcta.
    const EXAMEN_OPCIONES = !!manifest.examen_opciones;
    const EXAMEN_VOCAB_MAX_FALLOS = 3;
    let _examenFallos = 0;

    let faseActual = 0;
    const nodosCompletados    = new Set();  // id_nodo de objetos interactuados
    const personajesHablados  = new Set();  // id_nodo de personajes con los que se habló
    const zonasVisitadas      = new Set();  // id de zonas que el jugador ha pisado


    // ── Estado de inspección de objeto ────────────────────────────────────────
    let _inspeccionActiva   = false;
    let _inspeccionIdNodo   = null;
    let _inspeccionInter    = null;
    let _inspeccionWrapper  = null;   // THREE.Group en la escena, actualizado cada frame
    let _inspeccionFlotante = false;  // true = objeto pequeño flotando frente a cámara
    let _inspeccionDrag     = false;
    let _inspeccionLastX    = 0;
    let _inspeccionLastY    = 0;
    let _inspeccionDragQuat = new THREE.Quaternion();  // rotación acumulada por el usuario
    window._wwInspeccionActiva = () => _inspeccionActiva;

    const _UMBRAL_FLOTANTE  = 1.5;   // unidades de escena; menor → flota en cámara
    const _INSP_DIST        = 0.65;  // distancia frente a la cámara
    const _INSP_TARGET_SIZE = 0.30;  // tamaño objetivo del objeto inspeccionado (u)

    // Mini renderers del inventario: id_nodo → { renderer, rafId }
    const _invMinis = {};

    const estadoActivar      = {};   // id → bool (toggle on/off)
    const proximidadActivados = new Set();  // ids de objetos cuya proximidad ya se disparó
    const efectosActivos = [];   // { obj3d, tipo, luz, ... }
    const inventario     = new Map();  // id_nodo → { titulo, nombre }
    const recogidos      = new Set();  // id_nodo de objetos ya recogidos (ocultos)
    const usados         = new Set();  // id_nodo de objetos usar_con ya completados

    let nodoEnRango       = null;
    let dialogoAbierto    = false;
    let _teclaDialogoActual  = null;   // tecla que abrió el diálogo/acción actual (ej: 'KeyR'); misma tecla lo cierra
    const _teclaHint = (verbo = _T('close')) => {
        const letra = (_teclaDialogoActual || 'KeyE').replace('Key', '');
        return `<div class="int-pista">${letra} · ${verbo}</div>`;
    };
    let hoverIdActual  = null;
    let timerLore      = null;
    let timerActivacion= null;
    let frameCount     = 0;
    let loreFpsId      = null;
    let loreFpsTimer   = null;

    // ── Typewriter (diálogos de personajes) ──────────────────────────────────
    let _twCtx    = null;
    let _twTimer  = null;
    let _twActivo = false;
    let _twSkipFn = null;

    function _twClik() {
        try {
            if (!_twCtx) _twCtx = new (window.AudioContext || window.webkitAudioContext)();
            var o = _twCtx.createOscillator(), g = _twCtx.createGain();
            o.connect(g); g.connect(_twCtx.destination);
            o.frequency.value = 600 + Math.random() * 300;
            g.gain.setValueAtTime(0.030, _twCtx.currentTime);
            g.gain.exponentialRampToValueAtTime(0.001, _twCtx.currentTime + 0.036);
            o.start(); o.stop(_twCtx.currentTime + 0.036);
        } catch(e) {}
    }

    function _twEscribir(el, texto, onDone) {
        if (_twTimer) clearTimeout(_twTimer);
        _twActivo = true;
        el.innerHTML = '';
        const chars = _wwChars(texto);
        let i = 0;
        let spanAct = null;   // span de dato clave en curso
        function _ap(o) {
            if (o.m) {
                if (!spanAct) {
                    spanAct = document.createElement('span');
                    spanAct.className = 'dato-clave';
                    el.appendChild(spanAct);
                }
                spanAct.appendChild(document.createTextNode(o.c));
            } else {
                spanAct = null;
                el.appendChild(document.createTextNode(o.c));
            }
        }
        function paso() {
            if (i >= chars.length) {
                _twActivo = false; _twSkipFn = null;
                if (onDone) onDone();
                return;
            }
            const o = chars[i++];
            _ap(o);
            if (o.c !== ' ' && i % 2 === 0) _twClik();
            const delay = (o.c === '.' || o.c === '…') ? 280 : o.c === ',' ? 110 : 28;
            _twTimer = setTimeout(paso, delay);
        }
        _twSkipFn = () => {
            if (_twTimer) { clearTimeout(_twTimer); _twTimer = null; }
            el.innerHTML = '';
            spanAct = null;
            chars.forEach(_ap);
            _twActivo = false; _twSkipFn = null;
            if (onDone) onDone();
        };
        paso();
    }

    function _twCancelar() {
        if (_twTimer) { clearTimeout(_twTimer); _twTimer = null; }
        _twActivo = false; _twSkipFn = null;
    }

    // ── Sonidos procedurales de interacción ───────────────────────────────────
    // Todos usan _twCtx (AudioContext compartido con el typewriter).
    const _SFX = {
        _c() {
            if (!_twCtx) _twCtx = new (window.AudioContext || window.webkitAudioContext)();
            return _twCtx;
        },
        // Pickup: susurro de papel (highpass)
        recoger() {
            try {
                const c=this._c(), t=c.currentTime;
                const buf=c.createBuffer(1,Math.ceil(c.sampleRate*0.12),c.sampleRate);
                const d=buf.getChannelData(0);
                for(let i=0;i<d.length;i++) d[i]=(Math.random()*2-1)*(1-i/d.length);
                const src=c.createBufferSource(); src.buffer=buf;
                const f=c.createBiquadFilter(); f.type='highpass'; f.frequency.value=4200;
                const g=c.createGain(); g.gain.setValueAtTime(0.18,t); g.gain.exponentialRampToValueAtTime(0.001,t+0.12);
                src.connect(f); f.connect(g); g.connect(c.destination);
                src.start(t); src.stop(t+0.14);
            } catch(e){}
        },
        // Activar ON: click cuadrado ascendente
        activarOn() {
            try {
                const c=this._c(), t=c.currentTime;
                const o=c.createOscillator(), g=c.createGain();
                o.connect(g); g.connect(c.destination);
                o.type='square';
                o.frequency.setValueAtTime(180,t); o.frequency.exponentialRampToValueAtTime(480,t+0.07);
                g.gain.setValueAtTime(0.13,t); g.gain.exponentialRampToValueAtTime(0.001,t+0.12);
                o.start(t); o.stop(t+0.15);
            } catch(e){}
        },
        // Activar OFF: click cuadrado descendente
        activarOff() {
            try {
                const c=this._c(), t=c.currentTime;
                const o=c.createOscillator(), g=c.createGain();
                o.connect(g); g.connect(c.destination);
                o.type='square';
                o.frequency.setValueAtTime(480,t); o.frequency.exponentialRampToValueAtTime(120,t+0.07);
                g.gain.setValueAtTime(0.11,t); g.gain.exponentialRampToValueAtTime(0.001,t+0.12);
                o.start(t); o.stop(t+0.15);
            } catch(e){}
        },
        // Examinar: click metálico + tono de resolve
        examinar() {
            try {
                const c=this._c(), t=c.currentTime;
                const buf=c.createBuffer(1,Math.ceil(c.sampleRate*0.05),c.sampleRate);
                const d=buf.getChannelData(0);
                for(let i=0;i<d.length;i++) d[i]=(Math.random()*2-1)*(1-i/d.length);
                const src=c.createBufferSource(); src.buffer=buf;
                const f=c.createBiquadFilter(); f.type='bandpass'; f.Q.value=4; f.frequency.value=1200;
                const g=c.createGain(); g.gain.setValueAtTime(0.28,t); g.gain.exponentialRampToValueAtTime(0.001,t+0.05);
                src.connect(f); f.connect(g); g.connect(c.destination);
                src.start(t); src.stop(t+0.06);
                const o=c.createOscillator(), g2=c.createGain();
                o.connect(g2); g2.connect(c.destination);
                o.type='sine'; o.frequency.setValueAtTime(440,t+0.06); o.frequency.exponentialRampToValueAtTime(660,t+0.18);
                g2.gain.setValueAtTime(0,t+0.06); g2.gain.linearRampToValueAtTime(0.16,t+0.10);
                g2.gain.exponentialRampToValueAtTime(0.001,t+0.32);
                o.start(t+0.06); o.stop(t+0.35);
            } catch(e){}
        },
        // Abrir: crujido resonante — barrido de bandpass Q=6 de 370→90 Hz
        abrir() {
            try {
                const c=this._c(), t=c.currentTime, dur=0.80;
                const buf=c.createBuffer(1,Math.ceil(c.sampleRate*dur),c.sampleRate);
                const d=buf.getChannelData(0);
                for(let i=0;i<d.length;i++) d[i]=(Math.random()+Math.random()-1)*0.8;
                const src=c.createBufferSource(); src.buffer=buf;
                const f=c.createBiquadFilter(); f.type='bandpass'; f.Q.value=6;
                f.frequency.setValueAtTime(370,t); f.frequency.exponentialRampToValueAtTime(90,t+dur);
                const g=c.createGain();
                g.gain.setValueAtTime(0,t); g.gain.linearRampToValueAtTime(0.55,t+0.05);
                g.gain.setValueAtTime(0.55,t+dur*0.6); g.gain.exponentialRampToValueAtTime(0.001,t+dur);
                src.connect(f); f.connect(g); g.connect(c.destination);
                src.start(t); src.stop(t+dur+0.05);
            } catch(e){}
        },
        // Llama: ráfaga de crepitar (pops de ruido aleatorios)
        llama() {
            try {
                const c=this._c();
                for(let i=0;i<6;i++) {
                    const t=c.currentTime+i*0.055+Math.random()*0.035;
                    const buf=c.createBuffer(1,Math.ceil(c.sampleRate*0.048),c.sampleRate);
                    const d=buf.getChannelData(0);
                    for(let j=0;j<d.length;j++) d[j]=Math.random()*2-1;
                    const src=c.createBufferSource(); src.buffer=buf;
                    const f=c.createBiquadFilter(); f.type='bandpass';
                    f.frequency.value=200+Math.random()*500; f.Q.value=0.7;
                    const g=c.createGain();
                    g.gain.setValueAtTime(0.14,t); g.gain.exponentialRampToValueAtTime(0.001,t+0.048);
                    src.connect(f); f.connect(g); g.connect(c.destination);
                    src.start(t); src.stop(t+0.06);
                }
            } catch(e){}
        },
        // Brillo / partículas: cascada mágica de tonos agudos aleatorios
        brillo() {
            try {
                const c=this._c();
                for(let i=0;i<7;i++) {
                    const t=c.currentTime+i*0.038;
                    const o=c.createOscillator(), g=c.createGain();
                    o.connect(g); g.connect(c.destination);
                    o.type='sine'; o.frequency.value=1100+Math.random()*2200;
                    g.gain.setValueAtTime(0.09,t); g.gain.exponentialRampToValueAtTime(0.001,t+0.14);
                    o.start(t); o.stop(t+0.14);
                }
            } catch(e){}
        },
        // Aparecer: whoosh ascendente + ding de llegada
        aparecer() {
            try {
                const c=this._c(), t=c.currentTime;
                const buf=c.createBuffer(1,Math.ceil(c.sampleRate*0.32),c.sampleRate);
                const d=buf.getChannelData(0);
                for(let i=0;i<d.length;i++) d[i]=Math.random()*2-1;
                const src=c.createBufferSource(); src.buffer=buf;
                const f=c.createBiquadFilter(); f.type='bandpass'; f.Q.value=1.8;
                f.frequency.setValueAtTime(80,t); f.frequency.exponentialRampToValueAtTime(2800,t+0.28);
                const g=c.createGain();
                g.gain.setValueAtTime(0,t); g.gain.linearRampToValueAtTime(0.28,t+0.08);
                g.gain.exponentialRampToValueAtTime(0.001,t+0.32);
                src.connect(f); f.connect(g); g.connect(c.destination);
                src.start(t); src.stop(t+0.35);
                const o=c.createOscillator(), g2=c.createGain();
                o.connect(g2); g2.connect(c.destination);
                o.type='sine'; o.frequency.value=1480;
                g2.gain.setValueAtTime(0,t+0.27); g2.gain.linearRampToValueAtTime(0.12,t+0.30);
                g2.gain.exponentialRampToValueAtTime(0.001,t+0.50);
                o.start(t+0.27); o.stop(t+0.52);
            } catch(e){}
        },
        // Desaparecer: whoosh descendente
        desaparecer() {
            try {
                const c=this._c(), t=c.currentTime;
                const buf=c.createBuffer(1,Math.ceil(c.sampleRate*0.32),c.sampleRate);
                const d=buf.getChannelData(0);
                for(let i=0;i<d.length;i++) d[i]=Math.random()*2-1;
                const src=c.createBufferSource(); src.buffer=buf;
                const f=c.createBiquadFilter(); f.type='bandpass'; f.Q.value=1.8;
                f.frequency.setValueAtTime(2800,t); f.frequency.exponentialRampToValueAtTime(60,t+0.3);
                const g=c.createGain();
                g.gain.setValueAtTime(0.28,t); g.gain.exponentialRampToValueAtTime(0.001,t+0.32);
                src.connect(f); f.connect(g); g.connect(c.destination);
                src.start(t); src.stop(t+0.35);
            } catch(e){}
        },
        // Sacudir: traqueteo irregular (8 pops mid-hi con timing variable)
        sacudir() {
            try {
                const c=this._c();
                [0,0.024,0.052,0.074,0.104,0.128,0.158,0.182].forEach(dt => {
                    const t=c.currentTime+dt+Math.random()*0.014;
                    const dur=0.016+Math.random()*0.016;
                    const buf=c.createBuffer(1,Math.ceil(c.sampleRate*dur),c.sampleRate);
                    const d=buf.getChannelData(0);
                    for(let j=0;j<d.length;j++) d[j]=Math.random()*2-1;
                    const src=c.createBufferSource(); src.buffer=buf;
                    const f=c.createBiquadFilter(); f.type='bandpass';
                    f.frequency.value=1600+Math.random()*1400; f.Q.value=2.5;
                    const g=c.createGain();
                    g.gain.setValueAtTime(0.09+Math.random()*0.09,t);
                    g.gain.exponentialRampToValueAtTime(0.001,t+dur);
                    src.connect(f); f.connect(g); g.connect(c.destination);
                    src.start(t); src.stop(t+dur+0.01);
                });
            } catch(e){}
        },
        // Escapar: aleteo (ruido modulado con tremolo rápido)
        escapar() {
            try {
                const c=this._c(), t=c.currentTime;
                const sr=c.sampleRate;
                const buf=c.createBuffer(1,Math.ceil(sr*0.22),sr);
                const d=buf.getChannelData(0);
                for(let i=0;i<d.length;i++) {
                    const env=1-i/d.length;
                    const flutter=Math.abs(Math.sin(i*28*Math.PI*2/sr));
                    d[i]=(Math.random()*2-1)*env*flutter*0.6;
                }
                const src=c.createBufferSource(); src.buffer=buf;
                const f=c.createBiquadFilter(); f.type='highpass'; f.frequency.value=1400;
                const g=c.createGain(); g.gain.value=0.22;
                src.connect(f); f.connect(g); g.connect(c.destination);
                src.start(t); src.stop(t+0.25);
            } catch(e){}
        },
        // Avance de fase: arpeggio ascendente C-E-G-C5
        faseAvance() {
            try {
                const c=this._c(), t=c.currentTime;
                [523,659,784,1047].forEach((freq,i) => {
                    const dt=i*0.09;
                    const o=c.createOscillator(), g=c.createGain();
                    o.connect(g); g.connect(c.destination);
                    o.type='sine'; o.frequency.value=freq;
                    g.gain.setValueAtTime(0,t+dt);
                    g.gain.linearRampToValueAtTime(0.17,t+dt+0.04);
                    g.gain.setValueAtTime(0.17,t+0.38);
                    g.gain.exponentialRampToValueAtTime(0.001,t+0.75);
                    o.start(t+dt); o.stop(t+0.78);
                });
            } catch(e){}
        },
        // Suave: aliento con formante vocal (suspirar, rezar, murmurar)
        suave() {
            try {
                const c=this._c(), t=c.currentTime, dur=0.52;
                const buf=c.createBuffer(1,Math.ceil(c.sampleRate*dur),c.sampleRate);
                const d=buf.getChannelData(0);
                for(let i=0;i<d.length;i++) d[i]=(Math.random()*2-1)*Math.sin(Math.PI*i/d.length);
                const src=c.createBufferSource(); src.buffer=buf;
                const f=c.createBiquadFilter(); f.type='lowpass'; f.frequency.value=1150;
                const g=c.createGain();
                g.gain.setValueAtTime(0,t); g.gain.linearRampToValueAtTime(0.24,t+0.14);
                g.gain.setValueAtTime(0.24,t+0.34); g.gain.exponentialRampToValueAtTime(0.001,t+dur);
                src.connect(f); f.connect(g); g.connect(c.destination);
                src.start(t); src.stop(t+dur+0.05);
                const o=c.createOscillator(), g2=c.createGain();
                o.connect(g2); g2.connect(c.destination);
                o.type='sine'; o.frequency.value=390;
                g2.gain.setValueAtTime(0,t); g2.gain.linearRampToValueAtTime(0.10,t+0.18);
                g2.gain.setValueAtTime(0.10,t+0.34); g2.gain.exponentialRampToValueAtTime(0.001,t+dur);
                o.start(t); o.stop(t+dur+0.05);
            } catch(e){}
        },
        // Criatura: ruido pulsado (cuerdas vocales) — orgánico, periodo aleatorio ±8%
        criatura() {
            try {
                const c=this._c(), t=c.currentTime, sr=c.sampleRate, dur=0.20;
                const buf=c.createBuffer(1,Math.ceil(sr*dur),sr);
                const d=buf.getChannelData(0);
                let period=Math.floor(sr/90), pos=0;
                for(let i=0;i<d.length;i++){
                    const n=i/sr;
                    if(++pos>=period){ pos=0; period=Math.floor(sr/90*(0.92+Math.random()*0.16)); }
                    const pulse=Math.exp(-pos/(period*0.28));
                    const breath=(Math.random()-0.5)*0.18;
                    const env=Math.min(n/0.020,1)*(n<dur-0.06?1:(dur-n)/0.06);
                    d[i]=((Math.random()*2-1)*pulse+breath)*env*0.52;
                }
                const src=c.createBufferSource(); src.buffer=buf;
                const lp=c.createBiquadFilter(); lp.type='lowpass'; lp.frequency.value=620;
                const g=c.createGain(); g.gain.value=1.05;
                src.connect(lp); lp.connect(g); g.connect(c.destination);
                src.start(t); src.stop(t+dur+0.05);
            } catch(e){}
        },
        // Ritual: dos sinusoides ligeramente desafinadas con decay largo (invocar, meditar)
        ritual() {
            try {
                const c=this._c(), t=c.currentTime;
                [[220,0],[277,0.07]].forEach(([freq,dt]) => {
                    const o=c.createOscillator(), g=c.createGain();
                    o.connect(g); g.connect(c.destination);
                    o.type='sine'; o.frequency.value=freq;
                    g.gain.setValueAtTime(0,t+dt); g.gain.linearRampToValueAtTime(0.22,t+dt+0.18);
                    g.gain.setValueAtTime(0.22,t+0.55); g.gain.exponentialRampToValueAtTime(0.001,t+0.90);
                    o.start(t+dt); o.stop(t+0.95);
                });
            } catch(e){}
        },
        // Esfuerzo: ruido bandpass con ataque suave + gruñido grave (tensión sostenida)
        esfuerzo() {
            try {
                const c=this._c(), t=c.currentTime, dur=0.45;
                const buf=c.createBuffer(1,Math.ceil(c.sampleRate*dur),c.sampleRate);
                const d=buf.getChannelData(0);
                for(let i=0;i<d.length;i++) d[i]=Math.random()*2-1;
                const src=c.createBufferSource(); src.buffer=buf;
                const f=c.createBiquadFilter(); f.type='bandpass'; f.Q.value=2.5;
                f.frequency.setValueAtTime(260,t); f.frequency.exponentialRampToValueAtTime(110,t+dur);
                const g=c.createGain();
                g.gain.setValueAtTime(0,t); g.gain.linearRampToValueAtTime(0.6,t+0.06);
                g.gain.setValueAtTime(0.6,t+0.18); g.gain.exponentialRampToValueAtTime(0.001,t+dur);
                src.connect(f); f.connect(g); g.connect(c.destination);
                src.start(t); src.stop(t+dur+0.05);
                const o=c.createOscillator(), g2=c.createGain();
                o.connect(g2); g2.connect(c.destination);
                o.type='sawtooth'; o.frequency.setValueAtTime(150,t); o.frequency.exponentialRampToValueAtTime(110,t+dur);
                g2.gain.setValueAtTime(0,t); g2.gain.linearRampToValueAtTime(0.13,t+0.08);
                g2.gain.setValueAtTime(0.13,t+0.22); g2.gain.exponentialRampToValueAtTime(0.001,t+dur);
                o.start(t); o.stop(t+dur+0.05);
            } catch(e){}
        },
        // Alegria: trío ascendente C5-E5-G5 (reír, celebrar, saludar)
        alegria() {
            try {
                const c=this._c(), t=c.currentTime;
                [[523,0],[659,0.09],[784,0.17]].forEach(([freq,dt]) => {
                    const o=c.createOscillator(), g=c.createGain();
                    o.connect(g); g.connect(c.destination);
                    o.type='sine'; o.frequency.value=freq;
                    g.gain.setValueAtTime(0,t+dt); g.gain.linearRampToValueAtTime(0.15,t+dt+0.03);
                    g.gain.exponentialRampToValueAtTime(0.001,t+dt+0.22);
                    o.start(t+dt); o.stop(t+dt+0.25);
                });
            } catch(e){}
        },
        // Vibrar: zumbido grave con trémolo (máquina, cristal, portal mágico)
        vibrar() {
            try {
                const c=this._c(), t=c.currentTime, dur=0.6;
                const o=c.createOscillator(); o.type='triangle'; o.frequency.value=140;
                const g=c.createGain();
                g.gain.setValueAtTime(0,t); g.gain.linearRampToValueAtTime(0.30,t+0.06);
                g.gain.setValueAtTime(0.30,t+dur-0.15); g.gain.exponentialRampToValueAtTime(0.001,t+dur);
                const lfo=c.createOscillator(); lfo.type='sine'; lfo.frequency.value=11;
                const lfoG=c.createGain(); lfoG.gain.value=0.18;
                lfo.connect(lfoG); lfoG.connect(g.gain);
                o.connect(g); g.connect(c.destination);
                o.start(t); o.stop(t+dur); lfo.start(t); lfo.stop(t+dur);
            } catch(e){}
        },
        // Rugir: retumbo grave sostenido (motor, trueno, derrumbe, gran bestia)
        rugir() {
            try {
                const c=this._c(), t=c.currentTime, dur=0.75;
                const buf=c.createBuffer(1,Math.ceil(c.sampleRate*dur),c.sampleRate);
                const d=buf.getChannelData(0);
                let last=0;
                for(let i=0;i<d.length;i++){ last=(last+(Math.random()*2-1)*0.5)*0.96; d[i]=last; }
                const src=c.createBufferSource(); src.buffer=buf;
                const f=c.createBiquadFilter(); f.type='lowpass'; f.frequency.value=190; f.Q.value=1.2;
                const g=c.createGain();
                g.gain.setValueAtTime(0,t); g.gain.linearRampToValueAtTime(0.85,t+0.18);
                g.gain.setValueAtTime(0.85,t+dur-0.2); g.gain.exponentialRampToValueAtTime(0.001,t+dur);
                src.connect(f); f.connect(g); g.connect(c.destination);
                src.start(t); src.stop(t+dur+0.05);
                const o=c.createOscillator(); o.type='sawtooth';
                o.frequency.setValueAtTime(70,t); o.frequency.linearRampToValueAtTime(55,t+dur);
                const g2=c.createGain();
                g2.gain.setValueAtTime(0,t); g2.gain.linearRampToValueAtTime(0.18,t+0.2);
                g2.gain.exponentialRampToValueAtTime(0.001,t+dur);
                o.connect(g2); g2.connect(c.destination); o.start(t); o.stop(t+dur+0.05);
            } catch(e){}
        },
        // Metal: golpe metálico resonante (espada, gong, campana, palanca, reja)
        metal() {
            try {
                const c=this._c(), t=c.currentTime;
                const buf=c.createBuffer(1,Math.ceil(c.sampleRate*0.04),c.sampleRate);
                const d=buf.getChannelData(0); for(let i=0;i<d.length;i++) d[i]=Math.random()*2-1;
                const src=c.createBufferSource(); src.buffer=buf;
                const bp=c.createBiquadFilter(); bp.type='bandpass'; bp.Q.value=2; bp.frequency.value=3200;
                const gi=c.createGain(); gi.gain.setValueAtTime(0.3,t); gi.gain.exponentialRampToValueAtTime(0.001,t+0.05);
                src.connect(bp); bp.connect(gi); gi.connect(c.destination); src.start(t); src.stop(t+0.06);
                [1860, 2760, 4100].forEach((f,k)=>{
                    const o=c.createOscillator(); o.type='sine'; o.frequency.value=f;
                    const g=c.createGain(); const v=0.16/(k+1);
                    g.gain.setValueAtTime(v,t+0.005); g.gain.exponentialRampToValueAtTime(0.001,t+0.62-k*0.12);
                    o.connect(g); g.connect(c.destination); o.start(t+0.005); o.stop(t+0.72);
                });
            } catch(e){}
        },
        // Agua: chapoteo / líquido (fuente, poción, pozo, salpicar)
        agua() {
            try {
                const c=this._c(), t=c.currentTime;
                const buf=c.createBuffer(1,Math.ceil(c.sampleRate*0.22),c.sampleRate);
                const d=buf.getChannelData(0); for(let i=0;i<d.length;i++) d[i]=(Math.random()*2-1)*(1-i/d.length);
                const src=c.createBufferSource(); src.buffer=buf;
                const hp=c.createBiquadFilter(); hp.type='highpass'; hp.frequency.value=600;
                const g=c.createGain(); g.gain.setValueAtTime(0.22,t); g.gain.exponentialRampToValueAtTime(0.001,t+0.22);
                src.connect(hp); hp.connect(g); g.connect(c.destination); src.start(t); src.stop(t+0.24);
                [0,0.07,0.13].forEach((dt,k)=>{
                    const o=c.createOscillator(); o.type='sine';
                    o.frequency.setValueAtTime(300+k*60,t+dt); o.frequency.exponentialRampToValueAtTime(700+k*120,t+dt+0.05);
                    const g2=c.createGain(); g2.gain.setValueAtTime(0.14,t+dt); g2.gain.exponentialRampToValueAtTime(0.001,t+dt+0.09);
                    o.connect(g2); g2.connect(c.destination); o.start(t+dt); o.stop(t+dt+0.1);
                });
            } catch(e){}
        },
        // Magico: destello/chispa brillante ascendente (hechizo, objeto encantado, teletransporte)
        magico() {
            try {
                const c=this._c(), t=c.currentTime;
                [880,1320,1760,2640].forEach((f,k)=>{
                    const dt=k*0.05;
                    const o=c.createOscillator(); o.type='sine'; o.frequency.value=f;
                    const g=c.createGain();
                    g.gain.setValueAtTime(0,t+dt); g.gain.linearRampToValueAtTime(0.12,t+dt+0.02);
                    g.gain.exponentialRampToValueAtTime(0.001,t+dt+0.3);
                    o.connect(g); g.connect(c.destination); o.start(t+dt); o.stop(t+dt+0.32);
                });
                const buf=c.createBuffer(1,Math.ceil(c.sampleRate*0.15),c.sampleRate);
                const d=buf.getChannelData(0); for(let i=0;i<d.length;i++) d[i]=(Math.random()*2-1)*(1-i/d.length);
                const src=c.createBufferSource(); src.buffer=buf;
                const bp=c.createBiquadFilter(); bp.type='bandpass'; bp.Q.value=3;
                bp.frequency.setValueAtTime(2000,t); bp.frequency.exponentialRampToValueAtTime(6000,t+0.15);
                const g2=c.createGain(); g2.gain.setValueAtTime(0.12,t); g2.gain.exponentialRampToValueAtTime(0.001,t+0.15);
                src.connect(bp); bp.connect(g2); g2.connect(c.destination); src.start(t); src.stop(t+0.16);
            } catch(e){}
        },
        // Usar con: arpeggio ascendente de dos notas (C5→G5)
        usarCon() {
            try {
                const c = this._c(), t = c.currentTime;
                [[523,0],[784,0.14]].forEach(([f,dt]) => {
                    const o=c.createOscillator(), g=c.createGain();
                    o.connect(g); g.connect(c.destination);
                    o.type='sine'; o.frequency.value=f;
                    g.gain.setValueAtTime(0,t+dt);
                    g.gain.linearRampToValueAtTime(0.22,t+dt+0.02);
                    g.gain.exponentialRampToValueAtTime(0.001,t+dt+0.28);
                    o.start(t+dt); o.stop(t+dt+0.3);
                });
            } catch(e){}
        },
        // Acción genérica: default cuando una acción no especifica `sonido`.
        // Toque breve y neutro (click filtrado + tono de confirmación) que corta
        // sobre la música → toda acción da feedback audible aunque el manifest
        // traiga sonido:null.
        accion() {
            try {
                const c=this._c(), t=c.currentTime;
                const buf=c.createBuffer(1,Math.ceil(c.sampleRate*0.05),c.sampleRate);
                const d=buf.getChannelData(0);
                for(let i=0;i<d.length;i++) d[i]=(Math.random()*2-1)*(1-i/d.length);
                const src=c.createBufferSource(); src.buffer=buf;
                const f=c.createBiquadFilter(); f.type='bandpass'; f.Q.value=1.4; f.frequency.value=900;
                const g=c.createGain(); g.gain.setValueAtTime(0.22,t); g.gain.exponentialRampToValueAtTime(0.001,t+0.07);
                src.connect(f); f.connect(g); g.connect(c.destination);
                src.start(t); src.stop(t+0.08);
                const o=c.createOscillator(), g2=c.createGain();
                o.connect(g2); g2.connect(c.destination);
                o.type='sine'; o.frequency.setValueAtTime(520,t+0.02); o.frequency.linearRampToValueAtTime(660,t+0.14);
                g2.gain.setValueAtTime(0,t+0.02); g2.gain.linearRampToValueAtTime(0.12,t+0.05);
                g2.gain.exponentialRampToValueAtTime(0.001,t+0.22);
                o.start(t+0.02); o.stop(t+0.24);
            } catch(e){}
        },
        // Portal: whoosh dramático grave→agudo con cola
        portal() {
            try {
                const c=this._c(), t=c.currentTime, dur=1.2;
                const buf=c.createBuffer(1,Math.ceil(c.sampleRate*dur),c.sampleRate);
                const d=buf.getChannelData(0);
                for(let i=0;i<d.length;i++) d[i]=Math.random()*2-1;
                const src=c.createBufferSource(); src.buffer=buf;
                const f=c.createBiquadFilter(); f.type='bandpass'; f.Q.value=1.2;
                f.frequency.setValueAtTime(55,t);
                f.frequency.exponentialRampToValueAtTime(1800,t+0.75);
                f.frequency.exponentialRampToValueAtTime(400,t+dur);
                const g=c.createGain();
                g.gain.setValueAtTime(0,t); g.gain.linearRampToValueAtTime(0.52,t+0.25);
                g.gain.setValueAtTime(0.52,t+0.65); g.gain.exponentialRampToValueAtTime(0.001,t+dur);
                src.connect(f); f.connect(g); g.connect(c.destination);
                src.start(t); src.stop(t+dur+0.05);
            } catch(e){}
        },
        // Chapoteo: pisada sobre agua (ruido filtrado lowpass con caída rápida)
        chapoteo() {
            try {
                const c=this._c(), t=c.currentTime, dur=0.18;
                const buf=c.createBuffer(1,Math.ceil(c.sampleRate*dur),c.sampleRate);
                const d=buf.getChannelData(0);
                for(let i=0;i<d.length;i++) d[i]=(Math.random()*2-1)*(1-i/d.length);
                const src=c.createBufferSource(); src.buffer=buf;
                const f=c.createBiquadFilter(); f.type='lowpass';
                f.frequency.setValueAtTime(1400,t); f.frequency.exponentialRampToValueAtTime(350,t+dur);
                const g=c.createGain(); g.gain.setValueAtTime(0.12,t); g.gain.exponentialRampToValueAtTime(0.001,t+dur);
                src.connect(f); f.connect(g); g.connect(c.destination);
                src.start(t); src.stop(t+dur+0.02);
            } catch(e){}
        },
    };
    window._sfxPortal = () => {};
    window._wwChapoteo = () => { try { _SFX.chapoteo(); } catch(e){} };

    // Exponer estado de diálogo para que index.html pueda bloquear el movimiento
    window._wwDialogoAbierto = () => dialogoAbierto;

    const DIST_PROXIMIDAD = 2.5;
    const DELAY_LORE_MS   = 1500;
    const raycaster       = new THREE.Raycaster();

    // ── Tracker de objetivos ──────────────────────────────────────────────────
    let _objetivos = [];  // [{id, tipo, completado, el}]
    const IDLE_UMBRAL = (typeof window._WW_IDLE_UMBRAL !== 'undefined') ? window._WW_IDLE_UMBRAL : 45000;
    let _idleTimer = null;

    function _resetIdleTimer() {
        clearTimeout(_idleTimer);
        if (!_objetivos.length || _objetivos.every(i => i.completado)) return;
        _idleTimer = setTimeout(() => {
            if (_objetivos.some(i => !i.completado)) elTracker.style.opacity = '1';
        }, IDLE_UMBRAL);
    }

    function _nombreNodo(id) {
        const e = mapa[id];
        if (e?.obj3d?.userData?.nombre) return e.obj3d.userData.nombre;
        if (typeof SCENE_GRAPH !== 'undefined') {
            const n = (SCENE_GRAPH.nodos || []).find(x => x.id === id);
            if (n?.nombre) return n.nombre;
        }
        return id;
    }

    function _textoHint(id) {
        const entry = mapa[id];
        const nombre = _nombreNodo(id);
        const fila = h => `<div class="int-hint-row">${h}</div>`;
        if (entry.tipo === 'personaje') {
            const rows = [];
            let principal = '';
            for (const dic of (entry.dialogos_con_item || [])) {
                if (inventario.has(dic.requiere_objeto)) {
                    const t = inventario.get(dic.requiere_objeto).titulo;
                    principal = dic.consume
                        ? _T('give')(t, nombre)
                        : _T('talk')(nombre) + ` <span style="color:rgba(255,200,60,0.65);font-size:11px;">${_T('carrying')(t)}</span>`;
                    break;
                }
            }
            rows.push(principal || _T('talk')(nombre));
            for (const ac of (entry.acciones || [])) {
                if (ac.fase_aparicion <= faseActual) {
                    const tecla = ac.tecla.replace('Key', '');
                    rows.push(`<kbd>${tecla}</kbd> <em>${ac.etiqueta}</em>`);
                }
            }
            if (entry.ficha_info) rows.push(`<kbd>I</kbd> <em>${_T('info')}</em>`);
            return rows.map(fila).join('');
        }
        const inter = entry.interaccion;
        const rows = [];
        if (!inter) {
            rows.push(_T('examine')(nombre));
        } else {
            const tipo = inter.tipo;
            if (tipo === 'activar') {
                const fn = (estadoActivar[id] ?? false) ? _T('deactivate') : _T('activate');
                rows.push(`<kbd>E</kbd> ${fn(nombre)}`);
            } else if (tipo === 'recoger') {
                rows.push(_T('pickup')(nombre));
            } else if (tipo === 'usar_con') {
                if (inventario.has(inter.requiere_objeto)) {
                    const itemNombre = inventario.get(inter.requiere_objeto).titulo;
                    rows.push(_T('use_with')(itemNombre, nombre));
                } else {
                    const itemNombre = _nombreNodo(inter.requiere_objeto);
                    rows.push(_T('need_item')(itemNombre));
                }
            } else {
                rows.push(_T('examine')(nombre));
            }
        }
        for (const ac of (entry.acciones || [])) {
            const tecla = ac.tecla.replace('Key', '');
            rows.push(`<kbd>${tecla}</kbd> <em>${ac.etiqueta}</em>`);
        }
        return rows.map(fila).join('');
    }

    function _textoItem(id, tipo) {
        const nombre = _nombreNodo(id);
        if (tipo === 'personaje') return _T('talk_label')(nombre);
        if (tipo === 'zona') {
            const z = ZONAS.find(z => z.id === id);
            return z ? z.texto.replace(/[.!?,][\s\S]*/, '').substring(0, 36) : _T('explore_zone');
        }
        const inter = mapa[id]?.interaccion?.tipo;
        if (inter === 'activar')   return _T('activate_label')(nombre);
        if (inter === 'lore')      return _T('discover_label')(nombre);
        if (inter === 'recoger')   return _T('pickup_label')(nombre);
        if (inter === 'usar_con')  return _T('use_with_label')(nombre);
        return _T('examine_label')(nombre);
    }

    function _actualizarInventarioUI() {
        let el = document.getElementById('inv-panel');
        if (!el) {
            el = document.createElement('div');
            el.id = 'inv-panel';
            document.body.appendChild(el);
        }

        // Limpiar mini renderers anteriores
        for (const id in _invMinis) {
            cancelAnimationFrame(_invMinis[id].rafId);
            try { _invMinis[id].renderer.dispose(); } catch(_) {}
            delete _invMinis[id];
        }

        el.innerHTML = '';
        if (inventario.size === 0) { el.style.display = 'none'; return; }
        el.style.display = 'flex';

        for (const [idNodo, data] of inventario) {
            const wrap = document.createElement('div');
            wrap.className = 'inv-item';

            const slot = document.createElement('div');
            slot.className = 'inv-slot';
            const canvas3d = document.createElement('div');
            canvas3d.className = 'inv-canvas3d';
            slot.appendChild(canvas3d);
            wrap.appendChild(slot);

            const lbl = document.createElement('div');
            lbl.className = 'inv-slot-label';
            const lblSpan = document.createElement('span');
            lblSpan.textContent = data.titulo;
            lbl.appendChild(lblSpan);
            wrap.appendChild(lbl);

            el.appendChild(wrap);
            requestAnimationFrame(() => {
                const ov = lblSpan.scrollWidth - lbl.clientWidth;
                if (ov > 2) { lblSpan.style.setProperty('--tx', `-${ov}px`); lbl.classList.add('inv-label-scroll'); }
                _crearMiniVisor(idNodo, canvas3d);
            });
        }
    }

    function _crearMiniVisor(idNodo, container) {
        const entry = mapa[idNodo];
        const SZ = 72;

        const miniRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        miniRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        miniRenderer.setSize(SZ, SZ);
        miniRenderer.setClearColor(0x000000, 0);
        container.appendChild(miniRenderer.domElement);

        const miniScene  = new THREE.Scene();
        miniScene.add(new THREE.AmbientLight(0xffffff, 0.9));
        const dir = new THREE.DirectionalLight(0xffeedd, 1.4);
        dir.position.set(1, 2, 2);
        miniScene.add(dir);

        const miniCam = new THREE.PerspectiveCamera(34, 1, 0.01, 100);
        miniCam.position.set(0, 0, 1.6);
        miniCam.lookAt(0, 0, 0);

        if (entry?.obj3d) {
            try {
                const clone = entry.obj3d.clone(true);
                clone.visible = true;
                clone.position.set(0, 0, 0);
                clone.rotation.set(0, 0, 0);
                clone.traverse(c => { c.frustumCulled = false; if (c.isMesh && c.material) {
                    const mats = Array.isArray(c.material) ? c.material : [c.material];
                    c.material = mats.map(m => m ? m.clone() : m);
                    if (!Array.isArray(entry.obj3d.material)) c.material = c.material[0];
                }});
                clone.updateMatrixWorld(true);

                const box    = new THREE.Box3().setFromObject(clone);
                const center = box.getCenter(new THREE.Vector3());
                const size   = box.getSize(new THREE.Vector3());
                const factor = 0.75 / Math.max(size.x, size.y, size.z, 0.001);
                clone.position.set(-center.x * factor, -center.y * factor, -center.z * factor);
                clone.scale.multiplyScalar(factor);
                miniScene.add(clone);

                let t = 0;
                const tick = () => {
                    t += 0.014;
                    clone.rotation.y = t;
                    clone.rotation.x = Math.sin(t * 0.41) * 0.5;
                    clone.rotation.z = Math.sin(t * 0.27) * 0.3;
                    miniRenderer.render(miniScene, miniCam);
                    _invMinis[idNodo].rafId = requestAnimationFrame(tick);
                };
                _invMinis[idNodo] = { renderer: miniRenderer, rafId: requestAnimationFrame(tick) };
                return;
            } catch(_) {}
        }

        // Fallback sin modelo: solo renderiza el fondo vacío
        miniRenderer.render(miniScene, miniCam);
        _invMinis[idNodo] = { renderer: miniRenderer, rafId: 0 };
    }

    function _construirTracker(fase, sinFade) {
        const fm = FASES.find(f => f.fase === fase);

        const rebuild = () => {
            elTracker.innerHTML = '';
            _objetivos = [];
            if (!fm) { elTracker.style.opacity = '0'; return; }

            const ca = fm.condicion_avance;
            const items = [
                ...(ca.personajes || []).map(id => ({ id, tipo: 'personaje' })),
                ...(ca.nodos      || []).map(id => ({ id, tipo: 'nodo'      })),
                ...(ca.zonas      || []).map(id => ({ id, tipo: 'zona'      })),
            ];
            if (!items.length) { elTracker.style.opacity = '0'; return; }

            if (fm.texto_objetivo) {
                const hdr = document.createElement('div');
                hdr.className = 'obj-header';
                hdr.textContent = fm.texto_objetivo;
                elTracker.appendChild(hdr);
            }

            for (const item of items) {
                const el = document.createElement('div');
                el.className = 'obj-item';
                el.innerHTML = `<span class="obj-dot"></span><span class="obj-label">${_textoItem(item.id, item.tipo)}</span>`;
                elTracker.appendChild(el);
                item.el = el;
                const yaHecho =
                    (item.tipo === 'nodo'      && nodosCompletados.has(item.id))   ||
                    (item.tipo === 'personaje' && personajesHablados.has(item.id)) ||
                    (item.tipo === 'zona'      && zonasVisitadas.has(item.id));
                item.completado = yaHecho;
                if (yaHecho) item.el.classList.add('obj-completado');
                _objetivos.push(item);
            }
            _resetIdleTimer();  // oculto hasta que el jugador lleve 45s sin interactuar
        };

        if (sinFade) {
            rebuild();
        } else {
            elTracker.style.opacity = '0';
            clearTimeout(_idleTimer);
            setTimeout(rebuild, 260);
        }
    }

    function _marcarObjetivoCompletado(id) {
        const item = _objetivos.find(i => i.id === id && !i.completado);
        if (!item) return;
        item.completado = true;
        item.el.classList.add('obj-completado');
        setTimeout(() => {
            item.el.classList.add('obj-saliendo');
            setTimeout(() => {
                item.el.remove();
                if (_objetivos.every(i => i.completado)) elTracker.style.opacity = '0';
            }, 400);
        }, 650);
    }

    // ── Guías narrativas: aura dorada ─────────────────────────────────────────
    function _guiasDeFase(fase) {
        const fm = FASES.find(f => f.fase === fase);
        return fm ? (fm.guias || []) : [];
    }

    // ¿Debe esta guía encenderse? Un objeto ya completado (o un 'activar' que sigue
    // activo, pues nodosCompletados refleja su estado on/off) no necesita aura: su
    // condición ya está satisfecha al entrar en la fase. Los personajes nunca se
    // filtran aquí — sus diálogos cambian y personajesHablados se limpia por fase.
    function _guiaPendiente(id) {
        const e = mapa[id];
        if (!e) return false;
        if (e.tipo === 'objeto' && nodosCompletados.has(id)) return false;
        return true;
    }

    function _activarGuia(entry, fasePara = faseActual) {
        if (!entry.obj3d || entry.luzGuia) return;

        // Centro geométrico real del objeto en espacio local
        const box = new THREE.Box3().setFromObject(entry.obj3d);
        const centro = new THREE.Vector3();
        box.getCenter(centro);
        entry.obj3d.worldToLocal(centro);
        const altura = box.max.y - box.min.y;

        // Luz intensa de corto alcance — ilumina el objeto pero no se derrama.
        // Brillante y de buen alcance para que el "brillo dorado" se lea también en
        // escenas diurnas muy claras (donde el sprite aditivo casi desaparece).
        entry.luzGuia = new THREE.PointLight(0xffcc33, 3.6, Math.max(3.2, altura * 1.5));
        entry.luzGuia.position.copy(centro);
        entry.obj3d.add(entry.luzGuia);

        const mat = new THREE.SpriteMaterial({
            map:         _texturaAura,
            blending:    THREE.AdditiveBlending,
            transparent: true,
            depthWrite:  false,
            opacity:     1.0,
        });
        entry.spriteAura = new THREE.Sprite(mat);
        const escala = Math.max(1.1, altura * 0.85);
        entry.escalaAura = escala;
        entry.spriteAura.scale.set(escala, escala, 1);
        entry.spriteAura.position.copy(centro);
        entry.obj3d.add(entry.spriteAura);

        // "..." solo si el personaje tiene diálogo específico para esta fase
        const tieneDialogoNuevo = entry.tipo === 'personaje' &&
            (entry.dialogos || []).some(d => d.fase === fasePara);
        if (tieneDialogoNuevo) {
            const matPuntos = new THREE.SpriteMaterial({
                map:         _texturaPuntos,
                transparent: true,
                depthWrite:  false,
                opacity:     0.95,
            });
            entry.spritePuntos = new THREE.Sprite(matPuntos);
            const anchoPuntos = 0.55;
            entry.spritePuntos.scale.set(anchoPuntos, anchoPuntos * (72 / 128), 1);
            // Justo encima de la cabeza. La caja de un personaje con esqueleto suele
            // salir algo más alta que su cuerpo visible, así que un offset pequeño basta
            // (un +0.3 los disparaba muy arriba y se salían de pantalla al acercarse).
            entry.puntosCabeceraY = altura + 0.10;
            entry.spritePuntos.position.set(centro.x, entry.puntosCabeceraY, centro.z);
            entry.obj3d.add(entry.spritePuntos);
        }
    }

    function _desactivarGuia(entry) {
        if (!entry.luzGuia) return;
        entry.obj3d?.remove(entry.luzGuia);
        entry.luzGuia = null;
        if (entry.spriteAura) {
            entry.obj3d?.remove(entry.spriteAura);
            entry.spriteAura.material.dispose();
            entry.spriteAura = null;
        }
        if (entry.spritePuntos) {
            entry.obj3d?.remove(entry.spritePuntos);
            entry.spritePuntos.material.dispose();
            entry.spritePuntos = null;
        }
    }

    function _sincronizarGuias(nuevaFase) {
        const anteriores = nuevaFase > 0 ? _guiasDeFase(nuevaFase - 1) : [];
        const nuevas     = _guiasDeFase(nuevaFase);

        for (const id of anteriores) {
            if (!nuevas.includes(id) && mapa[id]) _desactivarGuia(mapa[id]);
        }
        for (const id of nuevas) {
            const entry = mapa[id];
            if (entry?.obj3d && _guiaPendiente(id)) _activarGuia(entry, nuevaFase);
        }
    }

    // ── Avance de fase ────────────────────────────────────────────────────────
    function _verificarAvance() {
        if (faseActual >= FASES.length) return;
        const fm = FASES[faseActual];
        if (!fm) return;
        const ca = fm.condicion_avance;

        const ok =
            ca.nodos.every(n     => nodosCompletados.has(n))    &&
            ca.personajes.every(p => personajesHablados.has(p)) &&
            ca.zonas.every(z     => zonasVisitadas.has(z));

        if (ok) _avanzarFase();
    }

    function _avanzarFase() {
        if (faseActual >= FASES.length - 1) {
            // Última fase superada — limpiar todas las guías y spawnear portal
            for (const id of _guiasDeFase(faseActual)) {
                if (mapa[id]) _desactivarGuia(mapa[id]);
            }
            faseActual = FASES.length;
            console.log('[Interactions] Historia completada — invocando portal.');
            setTimeout(() => { _SFX.faseAvance(); window.spawnPortal?.(); }, 1400);
            return;
        }
        faseActual++;
        _sincronizarGuias(faseActual);
        // nodosCompletados NO se resetea: lo completado en fases anteriores sigue
        // completado. condicion_avance puede volver a listar un objeto que ya tocaste
        // en una fase previa — al entrar aquí entra ya pre-marcado (el tracker lo muestra
        // hecho y _sincronizarGuias no le enciende aura), así que no se te vuelve a pedir.
        // Para los 'activar', nodosCompletados refleja su estado on/off real: solo cuenta
        // como hecho si sigue activo; si lo apagaste, su guía se reenciende y debes reactivarlo.
        personajesHablados.clear();  // los diálogos cambian entre fases → re-hablar siempre
        _construirTracker(faseActual);
        _verificarAvance();  // auto-avanzar si la nueva fase ya está satisfecha
        console.log(`[Interactions] Fase → ${faseActual}`);
    }

    // ── Diálogo actual para un personaje ─────────────────────────────────────
    // Devuelve el DialogoFase con fase más alta que sea ≤ faseActual.
    function _dialogoActual(entry) {
        let mejor = null;
        for (const df of entry.dialogos) {
            if (df.fase <= faseActual) {
                if (!mejor || df.fase > mejor.fase) mejor = df;
            }
        }
        return mejor || entry.dialogos[0] || null;
    }

    // ── Ejecutar acción de objeto (leer / accion ambiental) ──────────────────
    function _ejecutarAccionObjeto(idNodo, accion) {
        _resetIdleTimer();
        if (accion.tipo === 'leer') { _mostrarLeer(accion, _nombreNodo(idNodo)); return; }
        if (accion.tipo === 'accion') {
            _SFX[(accion.sonido && _SFX[accion.sonido]) ? accion.sonido : 'accion']();  // método: conserva this; default si null/inválido
            const entry = mapa[idNodo];
            if (accion.efecto_visual && entry?.obj3d) _aplicarEfecto(entry.obj3d, accion.efecto_visual, true, null);
            if (accion.descripcion) {
                _teclaDialogoActual = accion.tecla || null;
                _mostrarAccion(accion.etiqueta, accion.descripcion);
                dialogoAbierto = true;
            } else {
                _mostrarActivacion(accion.etiqueta);
            }
        }
    }

    function _mostrarLeer(accion, nombreNodo) {
        let el = document.getElementById('int-leer-overlay');
        if (!el) {
            el = document.createElement('div');
            el.id = 'int-leer-overlay';
            document.body.appendChild(el);
        }
        const titulo = accion.titulo || nombreNodo;
        const estilo = accion.estilo || 'pergamino';
        const teclaLetra = (accion.tecla || '').replace('Key', '');
        _teclaDialogoActual = accion.tecla || null;
        el.innerHTML = `
            <div class="int-leer-doc int-leer-${estilo}">
                <div class="int-leer-titulo">${titulo}</div>
                <div class="int-leer-texto">${_wwResaltar(accion.texto)}</div>
                <div class="int-leer-pista">${teclaLetra} · ${_T('close')}</div>
            </div>`;
        el.style.display = 'flex';
        dialogoAbierto = true;
    }

    // ── Ejecutar acción de personaje (tecla Q/R/T/G/X/Z) ─────────────────────
    function _ejecutarAccion(idNodo, accion) {
        _resetIdleTimer();
        _SFX[(accion.sonido && _SFX[accion.sonido]) ? accion.sonido : 'accion']();  // método: conserva this; default si null/inválido
        // Animación del propio personaje que realiza la acción
        if (accion.animacion && window.PersonajesManager)
            PersonajesManager.playOnce(idNodo, accion.animacion);
        // Disparar todos los efectos/animaciones en otros nodos
        for (const d of (accion.dispara || [])) {
            const tgt    = mapa[d.id_nodo];
            const tgtObj = tgt?.obj3d ?? _encontrarNodo(scene, d.id_nodo);
            if (!tgtObj) continue;
            if (tgt) tgt.obj3d = tgtObj;
            if (d.efecto)    _aplicarEfecto(tgtObj, d.efecto, true, d.color);
            if (d.animacion && window.PersonajesManager)
                PersonajesManager.playOnce(d.id_nodo, d.animacion);
        }
        // Panel narrativo si hay descripción; si no, toast corto
        if (accion.descripcion) {
            _teclaDialogoActual = accion.tecla || null;
            _mostrarAccion(accion.etiqueta, accion.descripcion);
            dialogoAbierto = true;
        } else {
            _mostrarActivacion(accion.etiqueta);
        }
        // Si es narrativa, cuenta para condicion_avance
        if (accion.narrativa) {
            nodosCompletados.add(idNodo);
            personajesHablados.add(idNodo);
            _marcarObjetivoCompletado(idNodo);
            _desactivarGuia(mapa[idNodo]);
            _verificarAvance();
        }
    }

    // ── Examen de vocabulario: HUD de fallos + entrega al guía ────────────────
    // Devuelve un objeto recogido a su posición original (lo hace visible de nuevo y lo
    // saca del inventario). El recoger nunca movió el objeto, solo lo ocultó, así que
    // vuelve exactamente a su sitio. Usado en el examen al coger otro o al fallar.
    function _devolverObjeto(idNodo) {
        const e = mapa[idNodo];
        if (e?.obj3d) e.obj3d.visible = true;
        inventario.delete(idNodo);
        recogidos.delete(idNodo);
    }

    function _actualizarFallosHUD() {
        let el = document.getElementById('int-fallos-hud');
        if (!el) {
            el = document.createElement('div');
            el.id = 'int-fallos-hud';
            el.style.cssText = 'position:fixed;top:16px;left:50%;transform:translateX(-50%);' +
                'z-index:60;padding:6px 14px;border-radius:14px;font:600 14px system-ui,sans-serif;' +
                'color:#fff;background:rgba(20,20,28,.62);backdrop-filter:blur(4px);' +
                'border:1px solid rgba(255,255,255,.14);letter-spacing:.3px;pointer-events:none;';
            document.body.appendChild(el);
        }
        el.textContent = _T('vocab_counter')(_examenFallos, EXAMEN_VOCAB_MAX_FALLOS);
    }

    // Gestiona el hablar-con-el-guía durante el examen. Devuelve true si lo gestionó
    // (acierto o fallo); false si el jugador no lleva ningún objeto del vocabulario
    // (entonces sigue el flujo normal y se muestra la petición de la fase).
    function _entregaVocab(idNodo, entry) {
        const dci = entry.dialogos_con_item || [];
        if (!dci.length) return false;            // este personaje no es el guía del examen
        const fm = FASES[faseActual];
        const requested = fm?.condicion_avance?.nodos?.[0] || null;
        const vocabObjs = new Set(dci.map(d => d.requiere_objeto));
        const llevaAlguno = [...inventario.keys()].some(id => vocabObjs.has(id));

        // Acierto: lleva el objeto que pide esta fase
        if (requested && inventario.has(requested)) {
            const dic   = dci.find(d => d.requiere_objeto === requested);
            const punto = dic?.puntos?.[0] || { frases: ['¡Correcto!'], opciones: [] };
            _SFX.faseAvance?.();
            _mostrarDialogo(punto);
            dialogoAbierto = true;
            if (window.PersonajesManager) { PersonajesManager.hablar(idNodo); _personajeHablando = idNodo; }
            inventario.delete(requested);
            _actualizarInventarioUI();
            nodosCompletados.add(requested);
            personajesHablados.add(idNodo);
            _verificarAvance();
            return true;
        }

        // Fallo: lleva objeto(s) del vocabulario pero ninguno es el pedido
        if (llevaAlguno) {
            _examenFallos++;
            _SFX.activarOff?.();
            // El objeto entregado por error NO te lo quedas: vuelve a su posición.
            for (const id of [...inventario.keys()]) if (vocabObjs.has(id)) _devolverObjeto(id);
            _actualizarInventarioUI();
            _actualizarFallosHUD();
            if (_examenFallos >= EXAMEN_VOCAB_MAX_FALLOS) {
                _mostrarActivacion(_T('vocab_reset'));
                setTimeout(() => window.location.reload(), 1900);
                return true;
            }
            // María "quiere hablarte": muestra la PISTA de la fase (reformula la petición con
            // un rasgo visual). Si no hay pista en el manifest, cae al aviso breve.
            const df = _dialogoActual(entry);
            const pista = df && df.pista;
            if (pista && (pista.frases || []).length) {
                _mostrarDialogo(pista);
                dialogoAbierto = true;
                if (window.PersonajesManager) { PersonajesManager.hablar(idNodo); _personajeHablando = idNodo; }
            } else {
                _mostrarActivacion(_T('vocab_wrong')(EXAMEN_VOCAB_MAX_FALLOS - _examenFallos));
            }
            return true;
        }

        // No lleva nada relevante → flujo normal (mostrar la petición de la fase)
        return false;
    }

    // Examen conceptual (Tipo B): al hablar con el guía, muestra la PREGUNTA de la fase con
    // sus opciones. NO marca personajesHablados ni avanza: el avance lo decide elegir la
    // opción correcta (gestionado en _intOpcion vía examenCtx). Devuelve true si lo gestionó.
    function _preguntaConceptual(idNodo, entry) {
        const df = _dialogoActual(entry);
        const punto = df && df.puntos && df.puntos[0];
        if (!punto || !(punto.opciones || []).length) return false;  // no es pregunta de examen
        _mostrarDialogo(punto, { esExamen: true, pista: df.pista, idNodo });
        dialogoAbierto = true;
        if (window.PersonajesManager) { PersonajesManager.hablar(idNodo); _personajeHablando = idNodo; }
        return true;
    }

    // ── Activar interacción ───────────────────────────────────────────────────
    function _activar(idNodo) {
        const entry = mapa[idNodo];
        if (!entry || entry.fase_aparicion > faseActual) return;
        _resetIdleTimer();
        _cerrarTodos();

        if (entry.tipo === 'personaje') {
            // Examen de vocabulario: la entrega del objeto pedido (o el fallo) se gestiona
            // aparte. Si el jugador no lleva ningún objeto del vocabulario, sigue el flujo
            // normal y se muestra la petición de la fase.
            if (EXAMEN_VOCAB && _entregaVocab(idNodo, entry)) return;
            // Examen conceptual: muestra la pregunta de la fase con opciones (el avance lo decide
            // elegir la opción correcta, no el hablar).
            if (EXAMEN_OPCIONES && _preguntaConceptual(idNodo, entry)) return;
            // dialogos_con_item: item-specific lines take priority over phase dialogue
            let puntoAMostrar = null;
            let dicActivado   = null;
            for (const dic of (entry.dialogos_con_item || [])) {
                if (inventario.has(dic.requiere_objeto) && (dic.puntos || []).length) {
                    puntoAMostrar = dic.puntos[0];
                    dicActivado   = dic;
                    break;
                }
            }

            if (!puntoAMostrar) {
                const df = _dialogoActual(entry);
                if (!df) return;
                const puntos = df.puntos || [];
                if (!puntos.length) return;
                puntoAMostrar = puntos[entry.indicePunto % puntos.length];
                entry.indicePunto++;
            }

            _mostrarDialogo(puntoAMostrar);
            dialogoAbierto = true;
            personajesHablados.add(idNodo);
            // Animación: reacción narrativa (playOnce) o hablar estándar
            if (window.PersonajesManager) {
                const _anim = _dialogoActual(entry)?.animacion;
                if (_anim) {
                    PersonajesManager.playOnce(idNodo, _anim);
                } else {
                    PersonajesManager.hablar(idNodo);
                    _personajeHablando = idNodo;
                }
            }
            _marcarObjetivoCompletado(idNodo);
            _desactivarGuia(entry);
            _verificarAvance();
            // Entrega: consumir el objeto del inventario si corresponde
            if (dicActivado?.consume) {
                inventario.delete(dicActivado.requiere_objeto);
                _actualizarInventarioUI();
            }
            // Efecto encadenado opcional al hablar con el personaje
            if (entry.dispara) {
                const tgt    = mapa[entry.dispara.id_nodo];
                const tgtObj = tgt?.obj3d ?? _encontrarNodo(scene, entry.dispara.id_nodo);
                if (tgtObj) {
                    if (tgt) tgt.obj3d = tgtObj;
                    if (entry.dispara.efecto) _aplicarEfecto(tgtObj, entry.dispara.efecto, true, entry.dispara.color);
                    if (entry.dispara.animacion && window.PersonajesManager)
                        PersonajesManager.playOnce(entry.dispara.id_nodo, entry.dispara.animacion);
                }
            }

        } else if (entry.tipo === 'objeto') {
            const inter = entry.interaccion;

            if (inter.tipo === 'examinar') {
                _SFX.examinar();
                if (entry.obj3d) {
                    _abrirInspeccion(idNodo, inter, 'examinar');
                } else {
                    _mostrarExaminar(inter);
                    dialogoAbierto = true;
                }
                // Efecto visual opcional simultáneo al panel (ej: chimenea que se enciende)
                if (inter.efecto_visual) _aplicarEfecto(entry.obj3d, inter.efecto_visual, true, inter.color_efecto);

            } else if (inter.tipo === 'activar') {
                const ahora = !(estadoActivar[idNodo] ?? false);
                estadoActivar[idNodo] = ahora;
                ahora ? _SFX.activarOn() : _SFX.activarOff();
                if (nodoEnRango === idNodo) elHint.innerHTML = _textoHint(idNodo);
                const texto = ahora
                    ? (inter.texto_activacion ?? '')
                    : (inter.texto_desactivacion ?? inter.texto_activacion ?? '');
                const textoFinal = texto || (ahora && inter.descripcion ? inter.descripcion : '');
                _mostrarActivacion(textoFinal);
                _aplicarEfecto(entry.obj3d, inter.efecto_visual, ahora, inter.color_efecto);

            } else if (inter.tipo === 'lore') {
                // lore se muestra por hover; no hace nada al activar con E/click
                return;

            } else if (inter.tipo === 'recoger') {
                _SFX.examinar();
                _abrirInspeccion(idNodo, inter, 'recoger');
                return;

            } else if (inter.tipo === 'usar_con') {
                if (!inventario.has(inter.requiere_objeto)) {
                    const itemNombre = _nombreNodo(inter.requiere_objeto);
                    _mostrarActivacion(_T('need_to_continue')(itemNombre));
                    return;
                }
                if (inter.sonido && _SFX[inter.sonido]) _SFX[inter.sonido](); else _SFX.usarCon();
                if (inter.efecto_visual) _aplicarEfecto(entry.obj3d, inter.efecto_visual, true, inter.color_efecto);
                _mostrarActivacion(inter.titulo || inter.descripcion || '');
                inventario.delete(inter.requiere_objeto);
                _actualizarInventarioUI();
                // Convertir a examinar para que el objeto siga siendo accesible en fases posteriores.
                // La llave ya se consumió del inventario, así que no hay riesgo de doble-trigger.
                entry.interaccion = { tipo: 'examinar', titulo: inter.titulo, descripcion: inter.descripcion };
            }

            if (inter.tipo === 'activar') {
                if (estadoActivar[idNodo]) {
                    nodosCompletados.add(idNodo);
                    _marcarObjetivoCompletado(idNodo);
                    _desactivarGuia(entry);
                } else {
                    nodosCompletados.delete(idNodo);
                }
            } else {
                nodosCompletados.add(idNodo);
                _marcarObjetivoCompletado(idNodo);
                _desactivarGuia(entry);
            }
            _verificarAvance();

            if (entry.dispara) {
                const target    = mapa[entry.dispara.id_nodo];
                const targetObj = target?.obj3d ?? _encontrarNodo(scene, entry.dispara.id_nodo);
                if (targetObj) {
                    if (target) target.obj3d = targetObj;
                    if (entry.dispara.efecto) _aplicarEfecto(targetObj, entry.dispara.efecto, true, entry.dispara.color);
                    if (entry.dispara.animacion && window.PersonajesManager)
                        PersonajesManager.playOnce(entry.dispara.id_nodo, entry.dispara.animacion);
                }
            }
        }
    }

    // ── Teclado ───────────────────────────────────────────────────────────────
    document.addEventListener('keydown', (e) => {
        // G = guardar objeto inspeccionado — SOLO en modo 'recoger'.
        // En modo 'examinar' la inspección también está activa, pero G no debe guardar
        // (el objeto no es recogible); se cierra con E. Sin este chequeo, examinar
        // cualquier objeto y pulsar G lo metía en el inventario por error.
        if (e.code === 'KeyG' && _inspeccionActiva) {
            if (_inspeccionModo === 'recoger') _cerrarInspeccion(true);
            return;
        }
        if (e.code === 'KeyE') {
            if (_inspeccionActiva) {
                _cerrarInspeccion(false);
            } else if (_twActivo && _twSkipFn) {
                _twSkipFn();  // primer E: salta al texto completo sin cerrar el diálogo
            } else if (dialogoAbierto && !_teclaDialogoActual) {
                _cerrarTodos();
            } else if (!dialogoAbierto && nodoEnRango) {
                _activar(nodoEnRango);
            }
        }
        // La misma tecla que abrió el diálogo lo cierra; return para no re-disparar la acción
        if (_teclaDialogoActual && e.code === _teclaDialogoActual) {
            _cerrarTodos();
            return;
        }
        // Teclas de acción (Q, R, T, G, X, Z) sobre el nodo en rango
        if (!dialogoAbierto && nodoEnRango) {
            const entry = mapa[nodoEnRango];
            if (entry?.tipo === 'personaje') {
                // I = ficha de información educativa (tarjeta de presentación)
                if (e.code === 'KeyI' && entry.ficha_info) {
                    _mostrarFicha(entry.ficha_info);
                    return;
                }
                const ac = (entry.acciones || []).find(
                    a => a.tecla === e.code && a.fase_aparicion <= faseActual
                );
                if (ac) _ejecutarAccion(nodoEnRango, ac);
            } else if (entry?.tipo === 'objeto') {
                const ac = (entry.acciones || []).find(a => a.tecla === e.code);
                if (ac) _ejecutarAccionObjeto(nodoEnRango, ac);
            }
        }
        if (e.code === 'Escape') _cerrarTodos();
    });

    // ── Click (modo órbita) ───────────────────────────────────────────────────
    renderer.domElement.addEventListener('click', (e) => {
        if (document.pointerLockElement) return;
        // Con un diálogo/inspección abierto el puntero está suelto (no bloqueado): sin esta
        // guarda, un clic en el lienzo raycastearía y activaría otro objeto "a través" del
        // panel abierto (o re-dispararía el actual). Solo se interactúa con el panel cerrado.
        if (window._wwDialogoAbierto?.() || _inspeccionActiva) return;
        const id = _raycastRaton(e.clientX, e.clientY);
        if (id) _activar(id);
    });

    // ── Hover para lore (solo modo órbita) ───────────────────────────────────
    renderer.domElement.addEventListener('mousemove', (e) => {
        if (document.pointerLockElement) return;
        const id = _raycastRaton(e.clientX, e.clientY);

        if (id !== hoverIdActual) {
            clearTimeout(timerLore);
            hoverIdActual = id;
            elLore.style.display = 'none';

            const inter = id && mapa[id]?.interaccion;
            if (inter?.tipo === 'lore') {
                timerLore = setTimeout(() => {
                    elLore.innerHTML = _wwResaltar(inter.texto);
                    elLore.style.display = 'block';
                    elLore.style.left = (e.clientX + 16) + 'px';
                    elLore.style.top  = (e.clientY - 8) + 'px';
                    _marcarObjetivoCompletado(id);
                    _verificarAvance();
                }, DELAY_LORE_MS);
            }
        }
    });

    // ── Mostrar diálogo ───────────────────────────────────────────────────────
    function _mostrarDialogo(punto, examenCtx = null) {
        const frase = punto.frases[0];
        const textoCompleto = `“${frase}”`;  // comillas tipográficas

        // Estructura base: span vacío para el typewriter + hint desde el inicio
        elDialogo.innerHTML =
            `<div class="int-d-texto"><span class="int-tw-txt"></span></div>` +
            _teclaHint();
        elDialogo.style.display = 'block';
        if (document.pointerLockElement) document.exitPointerLock();

        const twEl = elDialogo.querySelector('.int-tw-txt');

        const onDone = () => {
            // Opciones aparecen al terminar de escribir
            if (punto.opciones?.length) {
                let opHtml = `<div class="int-d-opciones">`;
                punto.opciones.forEach((op, i) => {
                    opHtml += `<button class="int-d-btn" onclick="_intOpcion(${i})">▸ ${op.etiqueta}</button>`;
                });
                opHtml += `</div>`;
                twEl.closest('.int-d-texto').insertAdjacentHTML('afterend', opHtml);
                // Quitar hint cuando hay opciones
                const hint = elDialogo.querySelector('.int-pista');
                if (hint) hint.style.display = 'none';
            }
        };

        _twEscribir(twEl, textoCompleto, onDone);

        // Helper: escribe la respuesta del personaje y, al terminar, ejecuta `tras`.
        const _mostrarResp = (resp, tras) => {
            _twCancelar();
            const twEl2 = elDialogo.querySelector('.int-tw-txt');
            if (twEl2) { twEl2.textContent = ''; }
            elDialogo.querySelectorAll('.int-d-opciones, .int-pista').forEach(el => el.remove());
            elDialogo.querySelector('.int-d-texto').innerHTML = '<span class="int-tw-txt"></span>';
            elDialogo.insertAdjacentHTML('beforeend', _teclaHint());
            _twEscribir(elDialogo.querySelector('.int-tw-txt'), `“${resp}”`, tras || null);
        };

        window._intOpcion = (i) => {
            const op = punto.opciones[i];
            if (!op) return;

            // ── Examen conceptual (Tipo B): la correcta avanza; la mala falla ──
            if (examenCtx && examenCtx.esExamen) {
                if (op.correcta) {
                    _SFX.faseAvance?.();
                    _avanzarFase();   // faseActual++ (o portal si era la última)
                    if (faseActual >= FASES.length) {
                        // Conversación completada: réplica final. El jugador cierra con E
                        // (re-engancha el ratón); el portal ya se invocó en _avanzarFase.
                        _mostrarResp(op.respuesta || '¡Muy bien!', null);
                    } else {
                        // Conversación CONTINUA: muestra la réplica y luego la siguiente
                        // pregunta del guía en el MISMO diálogo (sin caminar ni perder el ratón).
                        _mostrarResp(op.respuesta || '', () => {
                            setTimeout(() => {
                                const eg = mapa[examenCtx.idNodo];
                                const df2 = eg && _dialogoActual(eg);
                                const pt2 = df2 && df2.puntos && df2.puntos[0];
                                if (pt2 && (pt2.opciones || []).length) {
                                    _mostrarDialogo(pt2, { esExamen: true, pista: df2.pista, idNodo: examenCtx.idNodo });
                                } else {
                                    _cerrarTodos();  // sin más preguntas → cerrar y re-enganchar ratón
                                }
                            }, 1100);
                        });
                    }
                    return;
                }
                _examenFallos++;
                _SFX.activarOff?.();
                _actualizarFallosHUD();
                if (_examenFallos >= EXAMEN_VOCAB_MAX_FALLOS) {
                    _mostrarResp(op.respuesta || '', () => {
                        _mostrarActivacion(_T('vocab_reset'));
                        setTimeout(() => window.location.reload(), 1700);
                    });
                } else {
                    // El guía reacciona con extrañeza y, tras la pista, re-ofrece las opciones.
                    _mostrarResp(op.respuesta || '', () => {
                        const pista = examenCtx.pista;
                        const reintento = (pista && (pista.frases || []).length)
                            ? { frases: pista.frases, opciones: punto.opciones }
                            : punto;
                        setTimeout(() => _mostrarDialogo(reintento, examenCtx), 950);
                    });
                }
                return;
            }

            // ── Diálogo normal: solo muestra la respuesta ──
            if (op.respuesta) _mostrarResp(op.respuesta, null);
        };
    }

    // ── Mostrar examinar ──────────────────────────────────────────────────────
    function _mostrarExaminar(inter) {
        elExaminar.innerHTML = `
            <div class="int-e-titulo">${_wwResaltar(inter.titulo ?? '')}</div>
            <div class="int-e-desc">${_wwResaltar(inter.descripcion)}</div>
            ${_teclaHint()}
        `;
        elExaminar.style.display = 'block';
        if (document.pointerLockElement) document.exitPointerLock();
    }

    // ── Acción de personaje (texto narrador sin caja, abajo) ─────────────────
    function _mostrarAccion(titulo, descripcion) {
        elAccion.innerHTML =
            `<div class="int-ac-titulo">${_wwResaltar(titulo)}</div>` +
            `<div class="int-ac-desc">${_wwResaltar(descripcion)}</div>` +
            _teclaHint(_T('exit'));
        elAccion.style.opacity = '0';
        elAccion.style.display = 'block';
        requestAnimationFrame(() => { elAccion.style.opacity = '1'; });
        if (document.pointerLockElement) document.exitPointerLock();
    }

    // ── Ficha de información educativa (tecla I) ──────────────────────────────
    function _mostrarFicha(ficha) {
        _cerrarTodos();
        _teclaDialogoActual = 'KeyI';   // I también la cierra
        dialogoAbierto = true;
        elAccion.innerHTML =
            `<div class="int-ac-titulo int-ficha-titulo">${_wwResaltar(ficha.titulo)}</div>` +
            `<div class="int-ac-desc int-ficha-desc">${_wwResaltar(ficha.texto)}</div>` +
            _teclaHint(_T('exit'));
        elAccion.style.opacity = '0';
        elAccion.style.display = 'block';
        requestAnimationFrame(() => { elAccion.style.opacity = '1'; });
        if (document.pointerLockElement) document.exitPointerLock();
    }

    // ── Toast de activación ───────────────────────────────────────────────────
    function _mostrarActivacion(texto) {
        elActivacion.innerHTML = _wwResaltar(texto);
        elActivacion.style.opacity = '1';
        elActivacion.style.display = 'block';
        clearTimeout(timerActivacion);
        timerActivacion = setTimeout(() => {
            elActivacion.style.opacity = '0';
            setTimeout(() => { elActivacion.style.display = 'none'; }, 700);
        }, 2800);
    }

    // ── Zona narrativa ────────────────────────────────────────────────────────
    function _mostrarZonaNarrativa(texto) {
        const el = document.createElement('div');
        el.className = 'int-zona';
        el.innerHTML = _wwResaltar(texto);
        document.body.appendChild(el);
        requestAnimationFrame(() => el.classList.add('int-zona-visible'));
        setTimeout(() => el.classList.remove('int-zona-visible'), 3200);
        setTimeout(() => el.remove(), 4500);
    }

    function _detectarZona() {
        if (!document.pointerLockElement || !ZONAS.length) return;

        const ang = Math.atan2(camera.position.x, -camera.position.z) * (180 / Math.PI);
        const angPorCol = [-150, -75, 0, 75, 150];
        let colActual = 2, distMin = Infinity;
        angPorCol.forEach((a, i) => {
            const d = Math.min(Math.abs(ang - a), 360 - Math.abs(ang - a));
            if (d < distMin) { distMin = d; colActual = i; }
        });

        for (const zona of ZONAS) {
            if (!zonasVisitadas.has(zona.id) && zona.columnas.includes(colActual)) {
                zonasVisitadas.add(zona.id);
                _resetIdleTimer();
                _marcarObjetivoCompletado(zona.id);
                _mostrarZonaNarrativa(zona.texto);
                _verificarAvance();
                break;
            }
        }
    }

    // ── Efectos visuales ──────────────────────────────────────────────────────
    function _parseColor(hex) {
        if (!hex) return null;
        return parseInt(hex.replace('#', ''), 16);
    }

    function _aplicarEfecto(obj3d, tipo, activar, color = null) {
        if (!obj3d) return;

        let ef = efectosActivos.find(e => e.obj3d === obj3d);
        if (!ef) {
            ef = { obj3d, tipo, luz: null };
            efectosActivos.push(ef);
        }
        ef.activo = activar;
        ef.tipo   = tipo;

        if (tipo === 'brillo') {
            const col = _parseColor(color) ?? 0xffdd88;
            if (!ef.luz) {
                ef.luz = new THREE.PointLight(col, 0, 4);
                ef.luz.position.set(0, 1, 0);
                obj3d.add(ef.luz);
            } else if (color) {
                ef.luz.color.setHex(col);
            }
            ef.luz.intensity = activar ? 2.0 : 0;
            if (activar) _SFX.brillo();

        } else if (tipo === 'llama') {
            const col = _parseColor(color) ?? 0xff8830;
            if (!ef.luz) {
                // Radio corto + decay físico para caída brusca (aspecto de llama real)
                const box3 = new THREE.Box3().setFromObject(obj3d);
                const h = box3.getSize(new THREE.Vector3()).y;
                const flameY = h * 0.88;
                ef.luz = new THREE.PointLight(col, 0, 2.5, 2);
                ef.luz.position.set(0, flameY, 0);
                obj3d.add(ef.luz);
                // Sprite de resplandor en la punta de la llama
                const matSprite = new THREE.SpriteMaterial({
                    color: col,
                    blending: THREE.AdditiveBlending,
                    transparent: true,
                    depthWrite: false,
                    opacity: 0,
                });
                ef.spriteFlama = new THREE.Sprite(matSprite);
                ef.spriteFlama.scale.set(0.14, 0.22, 1);
                ef.spriteFlama.position.set(0, flameY + 0.06, 0);
                obj3d.add(ef.spriteFlama);
            } else if (color) {
                ef.luz.color.setHex(col);
                if (ef.spriteFlama) ef.spriteFlama.material.color.setHex(col);
            }
            const encendida = activar ? 10.0 : 0;
            ef.luz.intensity = encendida;
            if (ef.spriteFlama) ef.spriteFlama.material.opacity = activar ? 0.85 : 0;
            if (activar) _SFX.llama();

        } else if (tipo === 'rotar') {
            ef.rotando = activar;

        } else if (tipo === 'pulsar') {
            ef.pulsando = activar;
            if (!activar) obj3d.scale.set(1, 1, 1);

        } else if (tipo === 'desaparecer' && activar) {
            obj3d.traverse(child => {
                if (child.isMesh && child.material) {
                    child.material = child.material.clone();
                    child.material.transparent = true;
                    child.material.opacity = 0;
                }
            });
            _SFX.desaparecer();

        } else if (tipo === 'flotar') {
            if (activar && !ef.flotando) {
                ef.flotando = true;
                ef.flotarBaseY = obj3d.position.y;
            } else if (!activar && ef.flotando) {
                ef.flotando = false;
                obj3d.position.y = ef.flotarBaseY;
            }

        } else if (tipo === 'sacudir' && activar) {
            // Capturar la orientación de reposo SOLO la primera vez. Los redisparos
            // (p.ej. proximidad cada frame) no deben re-clonar la base desde una
            // rotación ya desviada ni reiniciar el reloj — si no, el temblor acumula
            // deriva y el objeto acaba torcido. La base se restaura intacta al acabar.
            if (ef.sacudirBaseRot === undefined) ef.sacudirBaseRot = obj3d.rotation.clone();
            if (!ef.sacudiendo) {
                ef.sacudiendo = true;
                ef.sacudirT0  = performance.now();
                _SFX.sacudir();
            }

        } else if (tipo === 'aparecer') {
            obj3d.traverse(child => {
                if (child.isMesh && child.material) {
                    if (!child.material._wwCloned) {
                        child.material = child.material.clone();
                        child.material._wwCloned = true;
                    }
                    child.material.transparent = true;
                    if (activar) child.material.opacity = 0;
                }
            });
            ef.apareciendoTarget = activar ? 1.0 : 0.0;
            ef.apareciendo = true;
            if (activar) _SFX.aparecer(); else _SFX.desaparecer();

        } else if (tipo === 'abrir') {
            if (ef.abrirBase === undefined) ef.abrirBase = obj3d.rotation.y;
            ef.abrirFrom   = obj3d.rotation.y;
            ef.abrirTarget = activar ? ef.abrirBase - Math.PI / 2 : ef.abrirBase;
            ef.abrirT0     = performance.now();
            ef.abriendo    = true;
            if (activar) _SFX.abrir();

        } else if (tipo === 'emitir_particulas' && activar) {
            const box = new THREE.Box3().setFromObject(obj3d);
            const centro = new THREE.Vector3();
            box.getCenter(centro);
            const geoP = new THREE.SphereGeometry(0.045, 4, 4);
            const matBase = new THREE.MeshBasicMaterial({ color: 0xffcc44, transparent: true });
            ef.particulas = [];
            for (let i = 0; i < 22; i++) {
                const p = new THREE.Mesh(geoP, matBase.clone());
                p.position.copy(centro);
                const speed = 1.8 + Math.random() * 2.8;
                const theta = Math.random() * Math.PI * 2;
                const phi   = Math.random() * Math.PI;
                p.userData._vel = new THREE.Vector3(
                    speed * Math.sin(phi) * Math.cos(theta),
                    speed * Math.abs(Math.cos(phi)) + Math.random() * 1.5,
                    speed * Math.sin(phi) * Math.sin(theta)
                );
                scene.add(p);
                ef.particulas.push(p);
            }
            geoP.dispose();
            ef.particulasT0 = performance.now();
            _SFX.brillo();

        } else if (tipo === 'escapar' && activar) {
            ef.volando   = true;
            ef.escaparT0   = performance.now();
            ef.escaparBaseY = obj3d.position.y;
            obj3d.traverse(child => {
                if (child.isMesh && child.material) {
                    if (!child.material._wwCloned) {
                        child.material = child.material.clone();
                        child.material._wwCloned = true;
                    }
                    child.material.transparent = true;
                }
            });
            _SFX.escapar();

        } else if (tipo === 'cambiar_color') {
            obj3d.traverse(child => {
                if (child.isMesh && child.material) {
                    if (!child.material._wwCloned) {
                        child.material = child.material.clone();
                        child.material._wwCloned = true;
                    }
                    if (!ef.colorOriginalEmissive) {
                        ef.colorOriginalEmissive  = child.material.emissive?.clone() || new THREE.Color(0);
                        ef.intensidadOriginal = child.material.emissiveIntensity || 0;
                    }
                    child.material.emissive = activar
                        ? new THREE.Color(0xff6600)
                        : ef.colorOriginalEmissive.clone();
                    child.material.emissiveIntensity = activar ? 0.8 : ef.intensidadOriginal;
                }
            });
        }
    }

    // ── Inspección de objeto en 3D ────────────────────────────────────────────
    // Objetos pequeños (< _UMBRAL_FLOTANTE) o recogibles: flotan frente a la cámara.
    // Objetos grandes: solo overlay + texto, sin clonar nada.
    // modo: 'examinar' → E para cerrar   |   'recoger' → G guardar / Esc soltar
    let _inspeccionModo = null;

    function _abrirInspeccion(idNodo, inter, modo) {
        const entry = mapa[idNodo];

        _inspeccionActiva   = true;
        _inspeccionModo     = modo;
        _inspeccionIdNodo   = idNodo;
        _inspeccionInter    = inter;
        _inspeccionFlotante = false;
        dialogoAbierto      = true;

        if (entry?.obj3d) {
            try {
                // Medir tamaño real en espacio de escena
                const boxEscena = new THREE.Box3().setFromObject(entry.obj3d);
                const sizeEscena = boxEscena.getSize(new THREE.Vector3());
                const maxDimEscena = Math.max(sizeEscena.x, sizeEscena.y, sizeEscena.z, 0.001);

                // Flotar si es recoger (siempre pequeño) o si cabe en el umbral
                if (modo === 'recoger' || maxDimEscena < _UMBRAL_FLOTANTE) {
                    _inspeccionFlotante = true;

                    const clone = entry.obj3d.clone(true);
                    clone.position.set(0, 0, 0);
                    clone.rotation.set(0, 0, 0);
                    clone.traverse(child => {
                        if (!child.isMesh) return;
                        child.renderOrder = 999;
                        const mats = Array.isArray(child.material) ? child.material : [child.material];
                        const newMats = mats.map(m => {
                            if (!m) return m;
                            const mc = m.clone();
                            mc.depthTest  = false;
                            mc.depthWrite = false;
                            return mc;
                        });
                        child.material = Array.isArray(child.material) ? newMats : newMats[0];
                    });

                    const box    = new THREE.Box3().setFromObject(clone);
                    const size   = box.getSize(new THREE.Vector3());
                    const center = box.getCenter(new THREE.Vector3());
                    const maxDim = Math.max(size.x, size.y, size.z, 0.001);
                    const factor = _INSP_TARGET_SIZE / maxDim;

                    const wrapper = new THREE.Group();
                    clone.position.set(-center.x * factor, -center.y * factor, -center.z * factor);
                    clone.scale.multiplyScalar(factor);
                    clone.traverse(c => { c.frustumCulled = false; });
                    wrapper.frustumCulled = false;
                    wrapper.add(clone);

                    // Iluminación propia — independiente de la escena
                    const luzP = new THREE.DirectionalLight(0xfff4e8, 1.2);
                    luzP.position.set(0.6, 1.2, 1);
                    wrapper.add(luzP);
                    const luzR = new THREE.DirectionalLight(0x8899cc, 0.35);
                    luzR.position.set(-1, -0.3, 0.5);
                    wrapper.add(luzR);

                    // Centrado frente a la cámara
                    wrapper.position.set(0, 0, -0.55);
                    wrapper.scale.setScalar(0);
                    const _t0 = performance.now();
                    const _animEntry = () => {
                        const p = Math.min((performance.now() - _t0) / 350, 1);
                        wrapper.scale.setScalar(1 - Math.pow(1 - p, 3));
                        if (p < 1) requestAnimationFrame(_animEntry);
                    };
                    requestAnimationFrame(_animEntry);

                    // Posición inicial frente a la cámara (update() la mantiene cada frame)
                    const fwd0 = new THREE.Vector3(0, 0, -_INSP_DIST).applyQuaternion(camera.quaternion);
                    wrapper.position.copy(camera.position).add(fwd0);
                    wrapper.quaternion.copy(camera.quaternion);

                    scene.add(wrapper);
                    _inspeccionWrapper  = wrapper;
                    _inspeccionDragQuat = new THREE.Quaternion();

                    // Ocultar original — el clon lo representa mientras se examina
                    entry.obj3d.visible = false;
                }
            } catch(e) {
                _inspeccionFlotante = false;
                console.warn('[Inspeccion] Error clonando modelo:', e);
            }
        }

        if (document.pointerLockElement) document.exitPointerLock();

        // Overlay de viñeta
        const overlay = document.getElementById('int-insp-overlay');
        if (overlay) {
            overlay.style.opacity = '0';
            overlay.style.display = 'block';
            requestAnimationFrame(() => { overlay.style.opacity = '1'; });
        }

        const titulo = inter.titulo || _nombreNodo(idNodo);
        const desc   = inter.descripcion || '';

        document.getElementById('exam3d-titulo').innerHTML = _wwResaltar(titulo);
        document.getElementById('exam3d-desc').innerHTML   = _wwResaltar(desc);

        const dragHint = document.querySelector('#int-examinar-3d .int-insp-drag');
        if (dragHint) dragHint.style.display = _inspeccionFlotante ? 'block' : 'none';

        const pistaEl = document.getElementById('exam3d-pista');
        if (pistaEl) pistaEl.innerHTML = modo === 'recoger'
            ? _T('keep_drop')
            : _teclaHint();

        document.getElementById('int-examinar-3d').style.display = 'block';
    }

    function _cerrarInspeccion(guardar) {
        if (!_inspeccionActiva) return;

        if (_inspeccionWrapper) {
            scene.remove(_inspeccionWrapper);
            _inspeccionWrapper = null;
        }

        const overlay = document.getElementById('int-insp-overlay');
        if (overlay) {
            overlay.style.opacity = '0';
            setTimeout(() => { overlay.style.display = 'none'; }, 300);
        }

        const idNodo = _inspeccionIdNodo;
        const inter  = _inspeccionInter;
        const entry  = mapa[idNodo];
        const titulo = inter?.titulo || _nombreNodo(idNodo);

        if (guardar) {
            _SFX.recoger();
            // Examen: inventario de UN solo hueco — al coger otro, el que llevabas vuelve a su sitio.
            if (EXAMEN_VOCAB) {
                for (const prevId of [...inventario.keys()]) _devolverObjeto(prevId);
            }
            inventario.set(idNodo, { titulo, nombre: _nombreNodo(idNodo) });
            recogidos.add(idNodo);
            if (entry?.obj3d) entry.obj3d.visible = false;  // recogido — desaparece
            _actualizarInventarioUI();
            if (inter?.descripcion) _mostrarActivacion(_T('saved_item')(titulo));
            // En el examen de vocabulario, recoger NO avanza la fase: solo la ENTREGA del
            // objeto correcto al guía cuenta. Así se puede coger todo libremente.
            if (!EXAMEN_VOCAB) {
                nodosCompletados.add(idNodo);
                _marcarObjetivoCompletado(idNodo);
                if (entry) _desactivarGuia(entry);
                _verificarAvance();
            }
        } else {
            // Soltar sin guardar: restaurar visibilidad si habíamos ocultado el original
            if (_inspeccionFlotante && entry?.obj3d) entry.obj3d.visible = true;
        }

        const elEx3d = document.getElementById('int-examinar-3d');
        if (elEx3d) elEx3d.style.display = 'none';
        document.getElementById('int-inspeccion').style.display = 'none';
        _inspeccionActiva   = false;
        _inspeccionModo     = null;
        _inspeccionFlotante = false;
        _inspeccionIdNodo   = null;
        _inspeccionInter    = null;
        dialogoAbierto      = false;
        window._wwRetomarPointerLock?.();
    }

    // Drag para rotar el objeto inspeccionado
    renderer.domElement.addEventListener('mousedown', (e) => {
        if (!_inspeccionActiva || e.button !== 0) return;
        _inspeccionDrag  = true;
        _inspeccionLastX = e.clientX;
        _inspeccionLastY = e.clientY;
    });
    document.addEventListener('mousemove', (e) => {
        if (!_inspeccionActiva || !_inspeccionDrag || !_inspeccionWrapper) return;
        const dx = e.clientX - _inspeccionLastX;
        const dy = e.clientY - _inspeccionLastY;
        // Acumular rotación en espacio local del objeto (ejes Y y X)
        const qY = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), dx * 0.013);
        const qX = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), dy * 0.013);
        _inspeccionDragQuat.multiply(qY).multiply(qX);
        _inspeccionLastX = e.clientX;
        _inspeccionLastY = e.clientY;
    });
    document.addEventListener('mouseup', () => { _inspeccionDrag = false; });

    // ── Cerrar todos los paneles ──────────────────────────────────────────────
    function _cerrarTodos() {
        if (_inspeccionActiva) { _cerrarInspeccion(false); return; }
        _twCancelar();
        elDialogo.style.display  = 'none';
        elExaminar.style.display = 'none';
        elLore.style.display     = 'none';
        elAccion.style.display   = 'none';
        const elLeer = document.getElementById('int-leer-overlay');
        if (elLeer) elLeer.style.display = 'none';
        _teclaDialogoActual = null;
        dialogoAbierto = false;
        // Volver a Idle si había un personaje hablando
        if (_personajeHablando && window.PersonajesManager) {
            PersonajesManager.callar(_personajeHablando);
            _personajeHablando = null;
        }
        // Si el navegador soltó el pointer lock durante el diálogo, retomarlo.
        // La tecla E que cierra el diálogo cuenta como gesto de usuario.
        window._wwRetomarPointerLock?.();
    }

    // ── Helpers ───────────────────────────────────────────────────────────────
    function _encontrarNodo(scene, id) {
        let found = null;
        scene.traverse(obj => {
            if (!found && obj.userData?.id === id) found = obj;
        });
        return found;
    }

    function _raycastRaton(cx, cy) {
        raycaster.setFromCamera(
            new THREE.Vector2(
                (cx / window.innerWidth) * 2 - 1,
                -(cy / window.innerHeight) * 2 + 1
            ),
            camera
        );
        const hits = raycaster.intersectObjects(scene.children, true);
        for (const hit of hits) {
            let obj = hit.object;
            while (obj) {
                const id    = obj.userData?.id;
                const entry = id && mapa[id];
                if (entry && entry.fase_aparicion <= faseActual) return id;
                obj = obj.parent;
            }
        }
        return null;
    }

    // ── Lore en FPS: mirar al centro durante DELAY_LORE_MS ───────────────────
    function _detectarLoreFPS() {
        raycaster.setFromCamera(new THREE.Vector2(0, 0), camera);
        const hits = raycaster.intersectObjects(scene.children, true);

        let idMirado = null;
        for (const hit of hits) {
            let obj = hit.object;
            while (obj) {
                const id    = obj.userData?.id;
                const entry = id && mapa[id];
                if (entry?.interaccion?.tipo === 'lore' && entry.fase_aparicion <= faseActual) {
                    idMirado = id;
                    break;
                }
                obj = obj.parent;
            }
            if (idMirado) break;
        }

        if (idMirado !== loreFpsId) {
            clearTimeout(loreFpsTimer);
            elLore.style.display = 'none';
            loreFpsId = idMirado;

            if (idMirado) {
                loreFpsTimer = setTimeout(() => {
                    elLore.innerHTML = _wwResaltar(mapa[idMirado].interaccion.texto);
                    elLore.style.display = 'block';
                    elLore.style.left = '50%';
                    elLore.style.top  = '42%';
                    elLore.style.transform = 'translateX(-50%)';
                    _marcarObjetivoCompletado(idMirado);
                    _verificarAvance();
                }, DELAY_LORE_MS);
            }
        }
    }

    // ── Update (llamar desde animate loop) ───────────────────────────────────
    function update() {
        const t = performance.now() * 0.001;
        frameCount++;

        // ── Resolución lazy de obj3d + guías iniciales ───────────────────────
        for (const [id, entry] of Object.entries(mapa)) {
            if (!entry.obj3d) {
                entry.obj3d = _encontrarNodo(scene, id);
                if (entry.obj3d && entry.fase_aparicion <= faseActual) {
                    if (_guiasDeFase(faseActual).includes(id) && _guiaPendiente(id)) _activarGuia(entry, faseActual);
                    // Refrescar label del tracker con el nombre real
                    const _tItem = _objetivos.find(i => i.id === id && !i.completado);
                    if (_tItem) {
                        const _lbl = _tItem.el?.querySelector('.obj-label');
                        if (_lbl) _lbl.textContent = _textoItem(id, _tItem.tipo);
                    }
                }
            }
        }

        // ── Animación de aura guía ───────────────────────────────────────────
        for (const entry of Object.values(mapa)) {
            if (entry.luzGuia || entry.spriteAura) {
                const pulse = 0.5 + 0.5 * Math.sin(t * 2.4);
                if (entry.luzGuia)    entry.luzGuia.intensity = 2.4 + 1.6 * pulse;
                if (entry.spriteAura) {
                    const base = entry.escalaAura || 1.1;
                    const sc = base * (0.94 + 0.06 * pulse);
                    entry.spriteAura.scale.set(sc, sc, 1);
                    entry.spriteAura.material.opacity = 0.80 + 0.20 * pulse;
                }
                if (entry.spritePuntos) {
                    // Bobbing suave hacia arriba y abajo
                    const bob = Math.sin(t * 1.8) * 0.07;
                    entry.spritePuntos.position.y = entry.puntosCabeceraY + bob;
                }
            }
        }

        // ── Proximidad FPS + apuntado ────────────────────────────────────────
        if (document.pointerLockElement) {
            // Paso 1: candidatos dentro del radio de interacción
            const candidatos = new Set();
            for (const [id, entry] of Object.entries(mapa)) {
                if (!entry.obj3d) continue;
                if (entry.fase_aparicion > faseActual) continue;
                if (entry.tipo === 'objeto' && entry.interaccion?.tipo === 'lore') continue;
                if (recogidos.has(id)) continue;
                if (usados.has(id)) continue;
                const pos = entry.obj3d.position;
                const dx  = camera.position.x - pos.x;
                const dz  = camera.position.z - pos.z;
                if (Math.sqrt(dx * dx + dz * dz) < DIST_PROXIMIDAD) candidatos.add(id);
            }

            // Paso 2: raycast desde el centro — solo activa si hay candidatos cercanos
            let mirado = null;
            if (candidatos.size > 0) {
                raycaster.setFromCamera(new THREE.Vector2(0, 0), camera);
                const hits = raycaster.intersectObjects(scene.children, true);
                for (const hit of hits) {
                    let obj = hit.object;
                    while (obj) {
                        const id = obj.userData?.id;
                        if (id && candidatos.has(id)) { mirado = id; break; }
                        obj = obj.parent;
                    }
                    if (mirado) break;
                }
            }

            if (dialogoAbierto) {
                elHint.style.display = 'none';
            } else if (mirado !== nodoEnRango) {
                nodoEnRango = mirado;
                if (mirado) {
                    elHint.innerHTML = _textoHint(mirado);
                    elHint.style.display = 'flex';
                } else {
                    elHint.style.display = 'none';
                }
            }

            if (frameCount % 45 === 0) _detectarZona();
            if (frameCount % 20 === 0) _detectarLoreFPS();

        } else if (nodoEnRango) {
            nodoEnRango = null;
            elHint.style.display = 'none';
            clearTimeout(loreFpsTimer);
            loreFpsId = null;
            elLore.style.display = 'none';
        }

        // ── Objeto inspeccionado: posición + rotación cada frame ────────────
        if (_inspeccionWrapper) {
            // Siempre delante de la cámara, independientemente de dónde mire
            const fwd = new THREE.Vector3(0, 0, -_INSP_DIST).applyQuaternion(camera.quaternion);
            _inspeccionWrapper.position.copy(camera.position).add(fwd);

            // Rotación idle (cuando no arrastra)
            if (!_inspeccionDrag) {
                const idleSpin = new THREE.Quaternion().setFromAxisAngle(
                    new THREE.Vector3(0, 1, 0), 0.006
                );
                _inspeccionDragQuat.multiply(idleSpin);
            }

            // Orientación final = dirección de cámara × rotación del usuario
            _inspeccionWrapper.quaternion.multiplyQuaternions(camera.quaternion, _inspeccionDragQuat);
        }

        // ── Efectos visuales ─────────────────────────────────────────────────
        for (const ef of efectosActivos) {
            if (ef.tipo === 'brillo' && ef.activo && ef.luz) {
                ef.luz.intensity = 1.5 + 0.7 * Math.sin(t * 3.5);
            } else if (ef.tipo === 'llama' && ef.activo && ef.luz) {
                // Parpadeo errático: tres frecuencias superpuestas simulan turbulencia de llama
                const f1 = Math.sin(t * 11.7 + 0.4);
                const f2 = Math.sin(t * 7.3  + 1.9);
                const f3 = Math.sin(t * 3.1  + 0.8);
                const flicker = 0.70 + 0.18 * f1 + 0.08 * f2 + 0.04 * f3;
                ef.luz.intensity = 10.0 * flicker;
                if (ef.spriteFlama) {
                    ef.spriteFlama.material.opacity = 0.65 + 0.25 * f1;
                    ef.spriteFlama.scale.y = 0.22 + 0.07 * f2;
                }
            } else if (ef.tipo === 'rotar' && ef.rotando) {
                ef.obj3d.rotation.y += 0.018;
            } else if (ef.tipo === 'pulsar' && ef.pulsando) {
                const s = 1 + 0.07 * Math.sin(t * 2.5);
                ef.obj3d.scale.setScalar(s);
            } else if (ef.tipo === 'flotar' && ef.flotando) {
                ef.obj3d.position.y = ef.flotarBaseY + 0.3 + 0.1 * Math.sin(t * 1.5);
            } else if (ef.tipo === 'sacudir' && ef.sacudiendo) {
                const elapsed = performance.now() - ef.sacudirT0;
                if (elapsed < 600) {
                    const amp = 0.12 * (1 - elapsed / 600);
                    ef.obj3d.rotation.z = ef.sacudirBaseRot.z + amp * Math.sin(elapsed * 0.08);
                    ef.obj3d.rotation.x = ef.sacudirBaseRot.x + amp * 0.4 * Math.sin(elapsed * 0.06);
                } else {
                    ef.obj3d.rotation.copy(ef.sacudirBaseRot);
                    ef.sacudiendo = false;
                }

            } else if (ef.tipo === 'aparecer' && ef.apareciendo) {
                let listo = true;
                ef.obj3d.traverse(child => {
                    if (child.isMesh && child.material?.transparent) {
                        const diff = ef.apareciendoTarget - child.material.opacity;
                        if (Math.abs(diff) < 0.012) {
                            child.material.opacity = ef.apareciendoTarget;
                        } else {
                            child.material.opacity += diff * 0.09;
                            listo = false;
                        }
                    }
                });
                if (listo) ef.apareciendo = false;

            } else if (ef.tipo === 'abrir' && ef.abriendo) {
                const prog = Math.min(1, (performance.now() - ef.abrirT0) / 800);
                const ease = 1 - Math.pow(1 - prog, 3);
                ef.obj3d.rotation.y = ef.abrirFrom + (ef.abrirTarget - ef.abrirFrom) * ease;
                if (prog >= 1) ef.abriendo = false;

            } else if (ef.tipo === 'emitir_particulas' && ef.particulas?.length) {
                const VIDA = 1.1;
                const elapsed = (performance.now() - ef.particulasT0) / 1000;
                ef.particulas = ef.particulas.filter(p => {
                    if (elapsed > VIDA) {
                        scene.remove(p);
                        p.material.dispose();
                        return false;
                    }
                    p.position.addScaledVector(p.userData._vel, 0.016);
                    p.userData._vel.y -= 0.14;
                    p.material.opacity = 1 - elapsed / VIDA;
                    return true;
                });

            } else if (ef.tipo === 'cambiar_color' && ef.activo) {
                ef.obj3d.traverse(child => {
                    if (child.isMesh && child.material?._wwCloned)
                        child.material.emissiveIntensity = 0.55 + 0.35 * Math.sin(t * 2.2);
                });

            } else if (ef.tipo === 'escapar' && ef.volando) {
                const prog = Math.min(1, (performance.now() - ef.escaparT0) / 1200);
                ef.obj3d.position.y = ef.escaparBaseY + prog * 4.0;
                // Leve ondulación lateral para que parezca vuelo real
                ef.obj3d.position.x += Math.sin(performance.now() * 0.008) * 0.004;
                ef.obj3d.traverse(child => {
                    if (child.isMesh && child.material?.transparent)
                        child.material.opacity = Math.max(0, 1 - prog * 1.4);
                });
                if (prog >= 1) {
                    ef.obj3d.visible = false;
                    ef.volando = false;
                }
            }
        }

        // ── Proximidad ambiental ─────────────────────────────────────────────
        for (const [id, entry] of Object.entries(mapa)) {
            if (!entry.proximidad || !entry.obj3d || !entry.obj3d.visible) continue;
            if (entry.fase_aparicion > faseActual) continue;
            const cfg = entry.proximidad;
            if (cfg.una_vez && proximidadActivados.has(id)) continue;
            const pos = entry.obj3d.position;
            const dx  = camera.position.x - pos.x;
            const dz  = camera.position.z - pos.z;
            if (Math.sqrt(dx * dx + dz * dz) < cfg.radio) {
                _aplicarEfecto(entry.obj3d, cfg.efecto, true, null);
                if (cfg.una_vez) proximidadActivados.add(id);
            }
        }
    }

    // ── CSS ───────────────────────────────────────────────────────────────────
    function _inyectarEstilos() {
        if (document.getElementById('int-styles')) return;
        const s = document.createElement('style');
        s.id = 'int-styles';
        s.textContent = `
            /* Dato clave resaltado (modo educativo) — subrayador verde.
               Fondo translúcido + texto verde claro: legible sobre paneles
               oscuros (diálogos) y claros (pergaminos/notas del leer). */
            .dato-clave {
                color: #1f7a44;
                background: rgba(74,222,128,0.30);
                box-shadow: 0 0 0 1px rgba(74,222,128,0.18);
                border-radius: 3px; padding: 0 .16em;
                font-weight: 600;
            }
            .int-d-texto .dato-clave, .int-e-desc .dato-clave,
            .int-ac-desc .dato-clave, #exam3d-desc .dato-clave,
            #int-lore .dato-clave, .int-zona .dato-clave,
            .int-leer-libro .dato-clave, .int-leer-inscripcion .dato-clave {
                color: #aef5c4;
                background: rgba(74,222,128,0.16);
                box-shadow: 0 0 10px rgba(74,222,128,0.18);
            }
            #int-hint {
                display: none; position: absolute;
                bottom: calc(50% + 38px); left: calc(50% + 45px); transform: none;
                flex-direction: column; align-items: flex-start; gap: 5px;
                font-size: 13px; letter-spacing: 0.3px; pointer-events: none; color: #ddd;
            }
            .int-hint-row {
                background: rgba(0,0,0,0.72);
                border: 1px solid rgba(255,255,255,0.18);
                padding: 5px 16px 5px 12px; border-radius: 20px;
                display: flex; align-items: center; gap: 4px;
                white-space: nowrap;
            }
            #int-hint kbd {
                display: inline-block;
                background: rgba(255,255,255,0.16);
                border: 1px solid rgba(255,255,255,0.32);
                border-bottom-width: 2px;
                border-radius: 4px;
                padding: 0px 7px;
                font-family: monospace; font-size: 11px;
                color: #fff; margin-right: 5px;
            }
            #int-hint em { font-style: normal; color: #e8d88f; }
            .int-hint-locked { color: rgba(255,255,255,0.42); font-size: 12px; }
            .int-hint-locked em { font-style: normal; color: rgba(255,220,100,0.55); }

            #inv-panel {
                position: absolute; bottom: 70px; right: 20px;
                display: flex; flex-direction: column; gap: 8px; align-items: center;
                pointer-events: none;
            }
            .inv-item {
                display: flex; flex-direction: column; align-items: center; gap: 4px;
            }
            .inv-slot {
                width: 72px; height: 72px;
                position: relative;
                background: rgba(12,12,28,0.52);
                backdrop-filter: blur(14px) saturate(140%);
                -webkit-backdrop-filter: blur(14px) saturate(140%);
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 12px; overflow: hidden;
                box-shadow: 0 4px 20px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.10);
            }
            .inv-canvas3d { width: 72px; height: 72px; }
            .inv-canvas3d canvas { display: block; width: 72px !important; height: 72px !important; }
            .inv-slot-label {
                width: 72px; overflow: hidden; white-space: nowrap;
                text-align: center; pointer-events: none;
            }
            .inv-slot-label span {
                display: inline-block; padding: 0 4px;
                font-size: 9px; color: rgba(255,255,255,0.70);
                letter-spacing: 0.3px;
            }
            .inv-label-scroll span {
                animation: inv-ticker 5s 0.8s ease-in-out infinite;
            }
            @keyframes inv-ticker {
                0%,  30%  { transform: translateX(0); }
                60%,  78% { transform: translateX(var(--tx, 0px)); }
                100%      { transform: translateX(0); }
            }
            #int-dialogo {
                display: none; position: absolute;
                bottom: 70px; left: 50%; transform: translateX(-50%);
                width: min(540px, 88vw);
                background: rgba(8,8,24,0.93); color: #e8e8f0;
                border: 1px solid rgba(130,100,255,0.4);
                border-radius: 14px; padding: 20px 24px;
                font-size: 14px; line-height: 1.75;
            }
            .int-d-texto { font-style: italic; margin-bottom: 14px; }
            .int-d-opciones { display: flex; flex-direction: column; gap: 7px; }
            .int-d-btn {
                background: rgba(70,50,160,0.55); border: 1px solid rgba(130,100,255,0.35);
                color: #ccc; padding: 7px 14px; border-radius: 8px;
                cursor: pointer; text-align: left; font-size: 13px;
                transition: background 0.18s, color 0.18s;
            }
            .int-d-btn:hover { background: rgba(100,75,210,0.8); color: #fff; }
            .int-pista {
                color: rgba(255,255,255,0.28); font-size: 11px;
                text-align: right; margin-top: 10px; letter-spacing: 0.5px;
            }
            #int-examinar {
                display: none; position: absolute;
                top: 50%; right: 28px; transform: translateY(-50%);
                width: min(300px, 82vw);
                background: rgba(8,8,24,0.93); color: #e8e8f0;
                border: 1px solid rgba(80,160,255,0.35);
                border-radius: 14px; padding: 20px 22px;
                font-size: 13px; line-height: 1.75;
            }
            .int-e-titulo {
                font-weight: 700; font-size: 15px; color: #88aaff;
                margin-bottom: 10px;
            }
            .int-e-desc { color: #b8b8cc; }
            /* Pista de cerrar del panel examinar: centrada y un poco más grande */
            #int-examinar .int-pista {
                text-align: center;
                font-size: 13px;
                letter-spacing: 0.5px;
                color: rgba(255,255,255,0.5);
                margin-top: 14px;
            }
            #int-activacion {
                display: none; position: absolute;
                top: 38%; left: 50%; transform: translateX(-50%);
                background: rgba(15,35,15,0.9); color: #a8f0a8;
                border: 1px solid rgba(80,200,80,0.3);
                border-radius: 10px; padding: 11px 22px;
                font-size: 13px; max-width: 420px; text-align: center;
                pointer-events: none; transition: opacity 0.7s;
            }
            #int-lore {
                display: none; position: absolute;
                background: rgba(10,10,30,0.92); color: #ccc;
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 8px; padding: 8px 13px;
                font-size: 12px; max-width: 230px; line-height: 1.65;
                font-style: italic; pointer-events: none;
            }
            .int-zona {
                position: absolute; bottom: 84px; left: 50%;
                transform: translateX(-50%);
                color: rgba(255,255,255,0.88); font-size: 15px; font-style: italic;
                text-align: center; max-width: min(560px, 88vw); line-height: 1.65;
                padding: 16px 42px;
                pointer-events: none;
                opacity: 0;
                transition: opacity 1.2s ease;
                text-shadow: 0 0 20px rgba(150,130,255,0.4), 0 1px 6px rgba(0,0,0,0.9);
                /* Mismo fondo "humo" suave que la acción secundaria */
                background: radial-gradient(ellipse at center,
                    rgba(0,0,0,0.58) 0%, rgba(0,0,0,0.40) 48%, rgba(0,0,0,0) 80%);
            }
            .int-zona-visible { opacity: 1; }

            #obj-tracker {
                position: absolute; top: 56px; left: 12px;
                background: rgba(0,0,0,0.50);
                border: 1px solid rgba(255,255,255,0.09);
                border-radius: 10px; padding: 7px 13px 9px;
                min-width: 148px; max-width: 230px;
                pointer-events: none;
                font-size: 12px; font-family: inherit;
                opacity: 0; transition: opacity 0.28s ease;
            }
            .obj-header {
                color: rgba(255,255,255,0.32); font-style: italic;
                font-size: 11px; line-height: 1.4;
                margin-bottom: 6px; padding-bottom: 5px;
                border-bottom: 1px solid rgba(255,255,255,0.07);
            }
            .obj-item {
                display: flex; align-items: center; gap: 7px;
                padding: 3px 0;
                color: rgba(255,255,255,0.72); line-height: 1.4;
                max-height: 28px; overflow: hidden;
                transition: max-height 0.38s ease, opacity 0.38s ease,
                            padding 0.38s ease, color 0.28s;
            }
            .obj-item.obj-completado {
                text-decoration: line-through;
                color: rgba(255,255,255,0.25);
            }
            .obj-item.obj-completado .obj-dot { background: rgba(255,255,255,0.18) !important; }
            .obj-item.obj-saliendo { max-height: 0; opacity: 0; padding: 0; }
            .obj-dot {
                width: 5px; height: 5px; border-radius: 50%;
                background: #ffcc44; flex-shrink: 0;
                transition: background 0.28s;
            }

            #int-accion {
                display: none; position: absolute;
                bottom: 80px; left: 50%; transform: translateX(-50%);
                text-align: center; max-width: min(520px, 90vw);
                padding: 16px 44px;
                pointer-events: none;
                transition: opacity 0.5s ease;
                /* Fondo "humo" suave: oscuro en el centro, difuminado a transparente en
                   los bordes — hace legible el texto blanco sobre cualquier fondo. */
                background: radial-gradient(ellipse at center,
                    rgba(0,0,0,0.60) 0%, rgba(0,0,0,0.42) 48%, rgba(0,0,0,0) 80%);
            }
            .int-ac-titulo {
                font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase;
                color: rgba(255,255,255,0.38); margin-bottom: 7px;
            }
            .int-ac-desc {
                font-size: 15px; font-style: italic; line-height: 1.7;
                color: rgba(255,255,255,0.82);
                text-shadow: 0 0 24px rgba(150,130,255,0.35), 0 1px 10px rgba(0,0,0,0.95);
            }
            /* Ficha educativa (tecla I): tono divulgativo, no teatral */
            .int-ficha-titulo {
                font-size: 14px; letter-spacing: 0.5px; text-transform: none;
                color: rgba(120,210,255,0.92); font-weight: 600;
            }
            .int-ficha-desc {
                font-style: normal;
                text-shadow: 0 0 20px rgba(80,160,255,0.28), 0 1px 10px rgba(0,0,0,0.95);
            }
            .int-ac-pista {
                margin-top: 10px;
                color: rgba(255,255,255,0.22); font-size: 11px; letter-spacing: 0.5px;
            }
            /* La pista de salir dentro de la acción secundaria: centrada y legible
               (la .int-pista genérica va alineada a la derecha para el panel de diálogo). */
            #int-accion .int-pista {
                text-align: center;
                font-size: 13px;
                letter-spacing: 0.5px;
                color: rgba(255,255,255,0.55);
                margin-top: 14px;
                text-shadow: 0 1px 8px rgba(0,0,0,0.9);
            }

            #int-insp-overlay {
                display: none; position: absolute; inset: 0;
                background: radial-gradient(ellipse at 50% 44%,
                    transparent 16%,
                    rgba(0,0,0,0.55) 54%,
                    rgba(0,0,0,0.78) 100%);
                pointer-events: none;
                transition: opacity 0.35s ease;
            }

            #int-examinar-3d {
                display: none; position: absolute;
                bottom: 60px; left: 50%; transform: translateX(-50%);
                width: min(520px, 88vw);
                text-align: center; pointer-events: none;
                background: rgba(0,0,12,0.62);
                padding: 16px 24px 12px;
                border-radius: 14px;
                backdrop-filter: blur(8px);
                -webkit-backdrop-filter: blur(8px);
            }
            #exam3d-titulo {
                font-weight: 700; font-size: 16px; color: #d8e8ff;
                margin-bottom: 8px;
                text-shadow: 0 0 18px rgba(80,130,255,0.5);
                letter-spacing: 0.4px;
            }
            #exam3d-desc {
                color: rgba(220,220,240,0.90); font-size: 13px;
                line-height: 1.75; font-style: italic;
            }
            .int-insp-drag {
                margin-top: 12px;
                color: rgba(255,255,255,0.5); font-size: 12px; letter-spacing: 0.5px;
            }
            #exam3d-pista { margin-top: 6px; }
            /* El hint va anidado (#exam3d-pista contiene otro .int-pista de _teclaHint),
               así que centramos el .int-pista interno, no solo el contenedor. */
            #int-examinar-3d .int-pista {
                text-align: center;
                color: rgba(255,255,255,0.5); font-size: 12.5px; letter-spacing: 0.5px;
            }
            #exam3d-pista kbd {
                display: inline-block;
                background: rgba(255,255,255,0.12);
                border: 1px solid rgba(255,255,255,0.25);
                border-bottom-width: 2px; border-radius: 4px;
                padding: 0 6px; font-size: 10px; color: #ccd; margin: 0 2px;
            }

            #int-inspeccion { display: none; }

            #int-leer-overlay {
                display: none; position: absolute; inset: 0;
                background: rgba(0,0,0,0.80);
                backdrop-filter: blur(5px);
                -webkit-backdrop-filter: blur(5px);
                justify-content: center; align-items: center;
                z-index: 60; cursor: default;
            }
            .int-leer-doc {
                max-width: min(580px, 88vw);
                max-height: 72vh; overflow-y: auto;
                padding: 44px 52px; border-radius: 6px;
                text-align: center;
            }
            .int-leer-pergamino {
                background: linear-gradient(160deg, #f5e6c8 0%, #e4ceaa 100%);
                color: #3a2610; font-family: Georgia, serif;
                border: 2px solid rgba(120,70,20,0.35);
                box-shadow: 0 0 70px rgba(0,0,0,0.85), inset 0 0 40px rgba(140,90,30,0.12);
            }
            .int-leer-libro {
                background: linear-gradient(160deg, #1a1208 0%, #241b0e 100%);
                color: #d8c080; font-family: Georgia, serif;
                border: 2px solid rgba(170,130,40,0.35);
                box-shadow: 0 0 70px rgba(0,0,0,0.9);
            }
            .int-leer-nota {
                background: #f7f3e6; color: #1e1808;
                font-family: 'Courier New', monospace;
                border: 1px solid rgba(0,0,0,0.18);
                box-shadow: 0 6px 40px rgba(0,0,0,0.65);
                transform: rotate(-0.4deg);
            }
            .int-leer-inscripcion {
                background: linear-gradient(160deg, #28221c 0%, #1c1813 100%);
                color: #c8b890; font-family: Georgia, serif;
                letter-spacing: 2px; text-transform: uppercase;
                border: 1px solid rgba(190,160,100,0.25);
                box-shadow: 0 0 70px rgba(0,0,0,0.92);
            }
            .int-leer-titulo {
                font-weight: 700; font-size: 18px;
                margin-bottom: 20px; letter-spacing: 0.5px;
                padding-bottom: 14px;
            }
            .int-leer-pergamino .int-leer-titulo { color: #6a3414; border-bottom: 1px solid rgba(110,60,20,0.28); }
            .int-leer-libro     .int-leer-titulo { color: #e8c860; border-bottom: 1px solid rgba(170,130,40,0.28); }
            .int-leer-nota      .int-leer-titulo { color: #2a1e08; border-bottom: 1px solid rgba(0,0,0,0.15); }
            .int-leer-inscripcion .int-leer-titulo { color: #d4a060; border-bottom: 1px solid rgba(190,160,100,0.25); }
            .int-leer-texto { font-size: 15px; line-height: 2.0; }
            .int-leer-pista { margin-top: 26px; font-size: 11px; opacity: 0.38; letter-spacing: 0.5px; }
        `;
        document.head.appendChild(s);
    }

    function _crearEl(tag, id) {
        let el = document.getElementById(id);
        if (!el) { el = document.createElement(tag); el.id = id; document.body.appendChild(el); }
        return el;
    }

    // Panel de inspección unificado — descripción centrada abajo sin caja
    if (!document.getElementById('int-examinar-3d')) {
        const elEx3d = document.createElement('div');
        elEx3d.id = 'int-examinar-3d';
        elEx3d.innerHTML = `
            <div id="exam3d-titulo"></div>
            <div id="exam3d-desc"></div>
            <div class="int-insp-drag">${_T('drag_rotate')}</div>
            <div class="int-pista" id="exam3d-pista">${_teclaHint()}</div>
        `;
        document.body.appendChild(elEx3d);
    }

    // Overlay de fondo para inspección (se crea una sola vez)
    if (!document.getElementById('int-insp-overlay')) {
        const elOv = document.createElement('div');
        elOv.id = 'int-insp-overlay';
        document.body.appendChild(elOv);
    }

    // Panel legacy recoger — oculto; se mantiene por compatibilidad con _cerrarInspeccion
    if (!document.getElementById('int-inspeccion')) {
        const elInsp = document.createElement('div');
        elInsp.id = 'int-inspeccion';
        elInsp.style.display = 'none';
        document.body.appendChild(elInsp);
    }

    const nPersonajes = (manifest.personajes || []).length;
    const nObjetos    = (manifest.objetos    || []).length;
    console.log(
        `[Interactions] Listo — ${nPersonajes} personajes, ${nObjetos} objetos, ` +
        `${FASES.length} fases, ${ZONAS.length} zonas narrativas.`
    );

    // Iniciar tracker con la fase 0 (sin fade de entrada)
    _construirTracker(0, true);

    // Examen de vocabulario: mostrar el contador de fallos desde el principio
    if (EXAMEN_VOCAB) _actualizarFallosHUD();

    return { update, getFase: () => faseActual };
};

// ── Footsteps procedurales ────────────────────────────────────────────────────
(function () {
    let _ctx = null;
    let _lastX = null, _lastZ = null;
    let _distAcum = 0;
    const STEP_DIST = 1.1;  // unidades recorridas por paso

    // Perfil de síntesis por tipo_ambiente
    const _PERFILES = {
        bosque:            'tierra',
        naturaleza:        'tierra',
        campo:             'tierra',
        pradera:           'tierra',
        selva:             'tierra',
        sabana:            'tierra_seca',
        desierto:          'arena',
        playa:             'arena',
        ciudad:            'piedra',
        pueblo:            'piedra',
        ruinas:            'piedra',
        montaña:           'piedra',
        cueva:             'piedra_eco',
        interior:          'madera',
        espacio:           'silencio',
        superficie_planeta:'polvo',
        bajo_el_agua:      'agua',
    };

    function _getCtx() {
        if (!_ctx) _ctx = new (window.AudioContext || window.webkitAudioContext)();
        return _ctx;
    }

    function _noise(ctx, dur) {
        const n = Math.ceil(ctx.sampleRate * dur);
        const buf = ctx.createBuffer(1, n, ctx.sampleRate);
        const d = buf.getChannelData(0);
        for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
        return buf;
    }

    function _noiseLayer(ctx, t, freq, q, gain, attack, decay) {
        const src = ctx.createBufferSource();
        src.buffer = _noise(ctx, attack + decay + 0.04);
        const flt = ctx.createBiquadFilter();
        flt.type = 'bandpass';
        flt.frequency.value = freq;
        flt.Q.value = q;
        const env = ctx.createGain();
        env.gain.setValueAtTime(0, t);
        env.gain.linearRampToValueAtTime(gain, t + attack);
        env.gain.exponentialRampToValueAtTime(0.0001, t + attack + decay);
        src.connect(flt); flt.connect(env); env.connect(ctx.destination);
        src.start(t); src.stop(t + attack + decay + 0.04);
    }

    function _thump(ctx, t, freq, gain, decay) {
        const osc = ctx.createOscillator();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(freq, t);
        osc.frequency.exponentialRampToValueAtTime(freq * 0.08, t + decay);
        const env = ctx.createGain();
        env.gain.setValueAtTime(gain, t);
        env.gain.exponentialRampToValueAtTime(0.0001, t + decay);
        osc.connect(env); env.connect(ctx.destination);
        osc.start(t); osc.stop(t + decay + 0.01);
    }

    function _playStep(superficie) {
        try {
            const ctx = _getCtx();
            if (ctx.state === 'suspended') ctx.resume();
            const t = ctx.currentTime;
            const p = 0.93 + Math.random() * 0.14;  // variación de pitch ±7%
            const v = 0.10 + Math.random() * 0.04;  // variación de volumen

            switch (superficie) {
                case 'tierra':
                    _noiseLayer(ctx, t, 220, 0.9, v,       0.003, 0.13);
                    _thump     (ctx, t, 75 * p, v * 0.8,   0.09);
                    break;
                case 'tierra_seca':
                    _noiseLayer(ctx, t, 420, 1.4, v * 0.8, 0.002, 0.08);
                    _thump     (ctx, t, 95 * p, v * 0.5,   0.06);
                    break;
                case 'arena':
                    _noiseLayer(ctx, t, 140, 0.5, v * 0.55, 0.006, 0.20);
                    break;
                case 'piedra':
                    _noiseLayer(ctx, t, 1300, 3.0, v * 0.7, 0.001, 0.05);
                    _thump     (ctx, t, 160 * p, v * 0.9,   0.05);
                    break;
                case 'piedra_eco':
                    _noiseLayer(ctx, t,        1100, 2.5, v * 0.8, 0.001, 0.09);
                    _thump     (ctx, t,        130 * p, v,         0.07);
                    _thump     (ctx, t + 0.20, 130 * p, v * 0.28,  0.07);  // eco
                    break;
                case 'madera':
                    _noiseLayer(ctx, t, 700, 2.2, v * 0.65, 0.001, 0.07);
                    _thump     (ctx, t, 190 * p, v * 1.1,   0.07);
                    break;
                case 'polvo':
                    _noiseLayer(ctx, t, 280, 0.6, v * 0.35, 0.005, 0.16);
                    _thump     (ctx, t, 55 * p,  v * 0.30,  0.11);
                    break;
                case 'agua':
                    _noiseLayer(ctx, t,        90,   0.4, v * 0.30, 0.008, 0.28);  // paso sordo
                    _noiseLayer(ctx, t + 0.04, 2800, 4.5, v * 0.18, 0.001, 0.06);  // burbuja aguda
                    _noiseLayer(ctx, t + 0.07, 2200, 3.5, v * 0.12, 0.001, 0.05);  // burbuja secundaria
                    break;
                case 'silencio':
                default:
                    break;
            }
        } catch (_) {}
    }

    function _superficie() {
        const ta = (typeof SCENE_GRAPH !== 'undefined' && SCENE_GRAPH.tipo_ambiente) || 'otro';
        return _PERFILES[ta] || 'tierra';
    }

    function _tick() {
        requestAnimationFrame(_tick);
        if (typeof fpsModo === 'undefined' || !fpsModo) { _lastX = _lastZ = null; return; }
        if (typeof camera === 'undefined') return;
        const x = camera.position.x, z = camera.position.z;
        if (_lastX !== null) {
            const dx = x - _lastX, dz = z - _lastZ;
            _distAcum += Math.sqrt(dx * dx + dz * dz);
            if (_distAcum >= STEP_DIST) {
                _distAcum -= STEP_DIST;
                _playStep(_superficie());
            }
        }
        _lastX = x; _lastZ = z;
    }

    _tick();
})();
