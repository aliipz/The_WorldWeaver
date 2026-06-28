/**
 * WorldWeaver — Scene Loader
 *
 * Tipos de nodo:
 *   fondo    → CylinderGeometry invertido (textura 2D panorámica)
 *   suelo    → CircleGeometry horizontal (textura 2D)
 *   resto    → modelos 3D glTF de poly.pizza (con fallback a billboard de color)
 *
 * Fallback de texturas (fondo/suelo):
 *   Si el Dibujante no se ha ejecutado, Three.js conserva el color sólido.
 *
 * Fallback de modelos 3D:
 *   Si gltf_url es null o la carga falla, se muestra un billboard de color.
 */

// Alturas objetivo por talla (unidades 3D; el jugador mide 1.8u)
const _TALLA_ALTURA = {
    adulto_alto:  2.05,
    adulto_medio: 1.80,
    adulto_bajo:  1.55,
    nino_enano:   0.95,
};

const TIPO_COLOR = {
    fondo:     0x2a4a6a,
    suelo:     0x5a7a3a,
    personaje: 0xFF9977,
    objeto:    0xFFD700,
    decorado:  0x88BB55,
};

const _COLOR_SUELO = {
    bosque:       0x384228,
    naturaleza:   0x4a5432,
    campo:        0x505838,
    pradera:      0x565a38,
    selva:        0x263020,
    sabana:       0xc8a030,
    desierto:     0xe8d080,
    playa:        0xf0d888,
    montaña:      0x7a7060,
    ciudad:       0x888888,
    pueblo:       0x998870,
    cueva:        0x3a3030,
    ruinas:       0x9a8870,
    bajo_el_agua:       0xd4c870,
    superficie_planeta: 0x9a9a8a,  // fallback gris; el color real viene de sceneGraph.color_suelo
    otro:               0x505438,
};

// Paleta de habitación (Capa 1/2 del rework de interiores). Las paredes NO usan
// color_fondo del cielo (que en cálido/frío es casi negro: es el vacío del cilindro
// viejo), sino una paleta propia por tipo de cielo. pared/techo/suelo/zocalo/puerta.
const _PALETA_INTERIOR = {
    interior_calido:   { pared: 0xc2a079, techo: 0x8a6a4a, suelo: 0x8a6038, zocalo: 0x5a4430, puerta: 0x4a3320 },
    interior_luminoso: { pared: 0xd6dbe1, techo: 0xe4e8ec, suelo: 0x8f744a, zocalo: 0xb6bcc2, puerta: 0x9a7f5e },
    interior_frio:     { pared: 0x70757d, techo: 0x565a61, suelo: 0x4c5057, zocalo: 0x383c42, puerta: 0x2e3238 },
};
function _paletaInterior(cieloTipo) {
    return _PALETA_INTERIOR[cieloTipo] || _PALETA_INTERIOR.interior_calido;
}

// ─── Estado de animación del módulo ──────────────────────────────────────
// Objetos registrados para animación frame a frame (flotan, giran, suben)
const _floatingObjects = [];
// Tipo de ambiente activo — permite que crearModelo3D añada flotación automáticamente
let _tipoAmbiente = null;
const _AMBIENTES_FLOTANTES = new Set(['espacio', 'superficie_planeta', 'bajo_el_agua']);

// ─── Helpers ──────────────────────────────────────────────────────────────

function _intentarCargarTextura(mat, idEscena, idNodo) {
    const ruta = `assets/${idEscena}/${idNodo}.png`;
    new THREE.TextureLoader().load(
        ruta,
        (texture) => { mat.map = texture; mat.color.set(0xffffff); mat.needsUpdate = true; },
        undefined,
        () => { /* PNG no encontrado — conserva color fallback */ }
    );
}

function crearTexturaEtiqueta(texto) {
    const canvas = document.createElement('canvas');
    canvas.width = 320; canvas.height = 72;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = 'rgba(10,10,25,0.78)';
    ctx.beginPath(); ctx.roundRect(4, 4, 312, 64, 10); ctx.fill();
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 21px sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(texto.length > 20 ? texto.slice(0, 18) + '…' : texto, 160, 38);
    return new THREE.CanvasTexture(canvas);
}

// ─── Fondo y suelo (texturas 2D) ──────────────────────────────────────────

function crearCilindroFondo(nodo, idEscena, radio) {
    const geo = new THREE.CylinderGeometry(radio, radio, nodo.alto, 48, 1, true);
    geo.scale(-1, 1, 1);
    // Color base: color_fondo del cielo, opaco. Si el Dibujante carga una textura la sobreescribe.
    const colorBase = (typeof CIELO_CONFIG !== 'undefined' && CIELO_CONFIG?.color_fondo)
        ? CIELO_CONFIG.color_fondo
        : (SCENE_GRAPH?.cielo?.color_fondo ?? '#2a4a6a');
    const mat = new THREE.MeshBasicMaterial({
        color: colorBase, side: THREE.BackSide, fog: false,
    });
    _intentarCargarTextura(mat, idEscena, nodo.id);
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(0, nodo.alto / 2, 0);
    mesh.userData = nodo;
    return mesh;
}

// Textura de cielo para el cristal de la ventana (degradado vertical → "se ve fuera").
function _texturaCieloVentana(hexArriba, hexAbajo) {
    const c = document.createElement('canvas'); c.width = 16; c.height = 64;
    const ctx = c.getContext('2d');
    const g = ctx.createLinearGradient(0, 0, 0, 64);
    g.addColorStop(0, hexArriba); g.addColorStop(1, hexAbajo);
    ctx.fillStyle = g; ctx.fillRect(0, 0, 16, 64);
    return new THREE.CanvasTexture(c);
}

// Construye una ventana creíble (mira hacia +Z en local): cristal con cielo + marco de
// 4 barras + cruz de montantes (4 cuadrantes) + alféizar. Se coloca y rota por pared.
function _crearVentana(wW, wH, luz, colorMarco) {
    const g = new THREE.Group();
    // Tono del cristal según la luz exterior de la historia (día / tarde / noche).
    const _G = { dia: ['#bfe4ff', '#eaf6ff'], tarde: ['#ffcf86', '#ffe7c2'], noche: ['#10183a', '#22305e'] };
    const [arriba, abajo] = _G[luz] || _G.dia;
    const matGlass = new THREE.MeshBasicMaterial({ map: _texturaCieloVentana(arriba, abajo), fog: false });
    const matMarco = new THREE.MeshLambertMaterial({ color: colorMarco, side: THREE.DoubleSide, fog: false });
    g.add(new THREE.Mesh(new THREE.PlaneGeometry(wW, wH), matGlass));   // cristal
    const t = 0.1;
    const mk = (geo, x, y) => { const m = new THREE.Mesh(geo, matMarco); m.position.set(x, y, 0.02); g.add(m); };
    const barH = new THREE.PlaneGeometry(wW + 2 * t, t);
    const barV = new THREE.PlaneGeometry(t, wH + 2 * t);
    mk(barH, 0,  wH / 2 + t / 2); mk(barH, 0, -wH / 2 - t / 2);          // marco arriba/abajo
    mk(barV, -wW / 2 - t / 2, 0); mk(barV,  wW / 2 + t / 2, 0);          // marco izq/der
    mk(new THREE.PlaneGeometry(wW, 0.06), 0, 0);                         // montante horizontal
    mk(new THREE.PlaneGeometry(0.06, wH), 0, 0);                         // montante vertical
    const sill = new THREE.Mesh(new THREE.BoxGeometry(wW + 2 * t + 0.12, 0.1, 0.2), matMarco);
    sill.position.set(0, -wH / 2 - t, 0.1);                             // alféizar que sobresale
    g.add(sill);

    // Haz de luz que entra por la ventana: plano additive de baja opacidad que cae hacia
    // el interior (local +Z) y hacia abajo. Tenue de noche (luz de luna fría), dorado de
    // tarde, cálido de día. Doble cara y sin escritura de profundidad → lee como luz.
    const _BEAM = { dia: ['#fff3d8', 0.10], tarde: ['#ffcc88', 0.13], noche: ['#9fb6ff', 0.05] };
    const [beamCol, beamOp] = _BEAM[luz] || _BEAM.dia;
    const shaftLen = 4.0;
    const shaft = new THREE.Mesh(
        new THREE.PlaneGeometry(wW * 0.9, shaftLen),
        new THREE.MeshBasicMaterial({
            color: beamCol, transparent: true, opacity: beamOp,
            blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
            depthWrite: false, fog: false,
        })
    );
    shaft.rotation.x = -Math.PI / 3;                 // inclinado: de la ventana al suelo
    shaft.position.set(0, -shaftLen * 0.30, shaftLen * 0.42);
    g.add(shaft);
    return g;
}

// ─── Habitación en caja (interiores construidos: interior / interior_grande) ──
// Reemplaza el cilindro redondo plano por una sala real: 4 paredes + techo,
// tintadas por paleta según el tipo de cielo, con puerta (alineada con el portal)
// y ventanas (solo interior_luminoso). El suelo lo sigue poniendo crearSuelo
// (cuadrado para interiores). No aplica a 'cueva' (cueva natural → se deja como está).
function crearHabitacion(nodo, radio, cieloTipo) {
    const grupo = new THREE.Group();
    // alto_cilindro es 7 para ambos tipos; en interior_grande (radio≈16) eso queda
    // aplastado (32×32×7), así que damos algo más de altura a las salas grandes.
    // Techo: salas grandes (radio>12) algo más altas; habitación pequeña (radio<7) más
    // baja y acogedora; interior normal usa la altura tal cual.
    const alto  = radio > 12 ? nodo.alto * 1.45 : (radio < 7 ? Math.min(nodo.alto, 4.6) : nodo.alto);
    const half  = radio;          // paredes en ±radio
    const pal   = _paletaInterior(cieloTipo);

    const matPared = new THREE.MeshLambertMaterial({ color: pal.pared, side: THREE.DoubleSide, fog: false });
    const matTecho = new THREE.MeshLambertMaterial({ color: pal.techo, side: THREE.DoubleSide, fog: false });

    function pared(geo, mat, x, z, rotY) {
        const m = new THREE.Mesh(geo, mat);
        m.position.set(x, alto / 2, z);
        m.rotation.y = rotY;
        m.receiveShadow = true;
        grupo.add(m);
        return m;
    }
    const geoPared = new THREE.PlaneGeometry(2 * half, alto);
    pared(geoPared, matPared, 0,    -half, 0);            // frontal (-Z), cara hacia +Z
    pared(geoPared, matPared, 0,     half, Math.PI);      // trasera (+Z)
    pared(geoPared, matPared, -half, 0,    Math.PI / 2);  // izquierda (-X)
    pared(geoPared, matPared,  half, 0,   -Math.PI / 2);  // derecha (+X)

    // Techo (plano horizontal mirando hacia abajo)
    const techo = new THREE.Mesh(new THREE.PlaneGeometry(2 * half, 2 * half), matTecho);
    techo.rotation.x = Math.PI / 2;
    techo.position.set(0, alto, 0);
    grupo.add(techo);

    // Zócalo (rodapié): franja oscura en la base de las 4 paredes → ancla la sala al suelo
    const altoZoc = 0.35;
    const matZoc  = new THREE.MeshLambertMaterial({ color: pal.zocalo, side: THREE.DoubleSide, fog: false });
    const geoZoc  = new THREE.PlaneGeometry(2 * half, altoZoc);
    [[0, -half, 0], [0, half, Math.PI], [-half, 0, Math.PI / 2], [half, 0, -Math.PI / 2]].forEach(([x, z, r]) => {
        const m = new THREE.Mesh(geoZoc, matZoc);
        m.position.set(x, altoZoc / 2, z + (z === 0 ? 0 : (z < 0 ? 0.02 : -0.02)));
        if (x !== 0) m.position.x = x + (x < 0 ? 0.02 : -0.02);
        m.rotation.y = r;
        grupo.add(m);
    });

    // Puerta en la pared frontal (-Z), alineada en X con el portal (~1.8). Marco + hoja.
    const dW = 1.4, dH = 2.6, dx = 1.8, zFront = -half + 0.05;
    const marco = new THREE.Mesh(
        new THREE.PlaneGeometry(dW + 0.24, dH + 0.18),
        new THREE.MeshLambertMaterial({ color: 0x000000, side: THREE.DoubleSide, fog: false })
    );
    marco.position.set(dx, (dH + 0.18) / 2, zFront);
    grupo.add(marco);
    const hoja = new THREE.Mesh(
        new THREE.PlaneGeometry(dW, dH),
        new THREE.MeshLambertMaterial({ color: pal.puerta, side: THREE.DoubleSide, fog: false })
    );
    hoja.position.set(dx, dH / 2, zFront + 0.02);
    grupo.add(hoja);
    // Pomo
    const pomo = new THREE.Mesh(
        new THREE.CircleGeometry(0.06, 12),
        new THREE.MeshBasicMaterial({ color: 0xd8b850, fog: false })
    );
    pomo.position.set(dx + dW / 2 - 0.18, dH / 2, zFront + 0.04);
    grupo.add(pomo);

    // Ventanas — en interiores cálidos y luminosos (el frío = bodega/cripta no lleva),
    // repartidas por 3 paredes (derecha, izquierda y fondo; la frontal lleva la puerta).
    // El cristal es autoiluminado (MeshBasic): "brilla" sin coste de luz ni saturar la sala.
    // Tono según el cielo: luminoso → luz fría de día; cálido → luz dorada.
    if (cieloTipo !== 'interior_frio') {
        const esLuminoso = (cieloTipo === 'interior_luminoso');
        // Luz exterior de la historia (día/tarde/noche). Si el Constructor no la fijó,
        // genérico: luminoso → día, cálido → tarde.
        const luz = (typeof SCENE_GRAPH !== 'undefined' && SCENE_GRAPH.cielo && SCENE_GRAPH.cielo.luz_exterior)
                    || (esLuminoso ? 'dia' : 'tarde');
        const _POOL    = { dia: '#fff3d8', tarde: '#ffcc88', noche: '#7fa0e0' };
        const _POOL_OP = { dia: 0.16, tarde: 0.18, noche: 0.07 };
        const poolCol = _POOL[luz] || _POOL.dia;
        const poolOp  = _POOL_OP[luz] ?? 0.16;
        const wW = 1.5, wH = 1.7, wy = 1.9;     // centro a 1.9 → alféizar ~1.0, alto ~2.8
        const eps = 0.06;
        // Cada pared: eje fijo + su valor (posición en la normal) + rotación hacia dentro
        const muros = [
            { fijo: 'x', val:  half - eps, rotY: -Math.PI / 2 },  // derecha (+X)
            { fijo: 'x', val: -half + eps, rotY:  Math.PI / 2 },  // izquierda (-X)
            { fijo: 'z', val:  half - eps, rotY:  Math.PI     },  // fondo (+Z)
        ];
        const offs = [-half * 0.4, half * 0.4];
        muros.forEach(mu => {
            offs.forEach(t => {
                const px = mu.fijo === 'x' ? mu.val : t;
                const pz = mu.fijo === 'z' ? mu.val : t;
                const win = _crearVentana(wW, wH, luz, pal.zocalo);
                win.position.set(px, wy, pz);
                win.rotation.y = mu.rotY;
                grupo.add(win);

                // Charco de luz en el suelo, desplazado hacia el interior de la sala.
                let ix = px, iz = pz;
                if (mu.fijo === 'x') ix += (mu.val > 0 ? -1.5 : 1.5);
                else                 iz += (mu.val > 0 ? -1.5 : 1.5);
                const pool = new THREE.Mesh(
                    new THREE.CircleGeometry(1.1, 24),
                    new THREE.MeshBasicMaterial({
                        color: poolCol, transparent: true, opacity: poolOp,
                        blending: THREE.AdditiveBlending, depthWrite: false, fog: false,
                    })
                );
                pool.rotation.x = -Math.PI / 2;
                pool.position.set(ix, 0.04, iz);
                grupo.add(pool);
            });
        });
    }

    grupo.userData = nodo;
    return grupo;
}

// Geometría de la cubierta del barco (compartida con index.html vía window).
window._BARCO_DECK_H = 1.0;   // altura de la cubierta sobre el agua
window._BARCO_DECK_R = 4.6;   // radio de la cubierta

// Suelo de AGUA animada ('sobre_agua' y 'barco'): plano segmentado con olas por
// desplazamiento de vértices + material translúcido especular. En 'barco' es más
// transparente para ver la vida submarina por debajo.
function _crearSueloAgua(radio, opacidad) {
    const geo = new THREE.PlaneGeometry(2 * radio * 1.2, 2 * radio * 1.2, 52, 52);
    const mat = new THREE.MeshPhongMaterial({
        color: 0x1d6e88, specular: 0xbfe6ff, shininess: 130,
        transparent: true, opacity: (opacidad ?? 0.9), side: THREE.DoubleSide,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.y = 0.0;
    mesh.receiveShadow = true;
    // Registrar para animación de olas por frame
    _floatingObjects.push({ type: 'agua', mesh: mesh, amp: 0.22 });
    return mesh;
}

// Mar de NUBES como suelo ('otro' con tipo_suelo='nubes'): el personaje camina sobre un
// manto de nubes (reino del cielo de un cuento). Base blanca + esferas aplastadas que
// forman los cúmulos, más densas y grandes hacia el horizonte para ocultar el borde, y
// unas pocas flotando algo más arriba para dar profundidad.
function _crearSueloNubes(radio) {
    const g = new THREE.Group();
    // Material base con emisivo MUY bajo: antes (0.25) lavaba todos los cúmulos a un
    // blanco plano sin relieve. Bajándolo, la luz de la escena modela cada esfera
    // (sombra abajo / luz arriba) y se aprecia el volumen de las nubes.
    const matNube = new THREE.MeshStandardMaterial({
        color: 0xffffff, roughness: 1.0, metalness: 0.0,
        emissive: 0x9fb4d8, emissiveIntensity: 0.04, fog: false,
    });
    // Base blanca que tapa el borde inferior del cilindro
    const base = new THREE.Mesh(
        new THREE.CircleGeometry(radio * 1.5, 48),
        new THREE.MeshStandardMaterial({ color: 0xeaf0fc, emissive: 0xc8d6f0,
            emissiveIntensity: 0.12, roughness: 1.0, fog: false }),
    );
    base.rotation.x = -Math.PI / 2; base.position.y = -1.4; base.receiveShadow = true;
    g.add(base);
    const _puff = (x, y, z, s, scY) => {
        // Tono por cúmulo: blanco con un punto de azul y luminosidad variable, para que
        // las nubes contiguas contrasten entre sí (textura visible) en vez de fundirse.
        const mat = matNube.clone();
        mat.color.setHSL(0.58, 0.16, 0.66 + Math.random() * 0.30);
        const m = new THREE.Mesh(new THREE.SphereGeometry(s, 7, 5), mat);
        m.position.set(x, y, z);
        m.scale.y = scY !== undefined ? scY : (0.28 + Math.random() * 0.14);
        g.add(m);
    };
    // Capa principal: cúmulos bajos y pequeños, la cima justo al nivel del suelo
    for (let i = 0; i < 200; i++) {
        const t = Math.pow(Math.random(), 0.5);
        const r = t * radio * 1.3;
        const a = Math.random() * Math.PI * 2;
        const s = 0.3 + Math.random() * 0.8 + (r / radio) * 0.7;  // max ~1.8 lejos, ~1.1 cerca
        _puff(Math.cos(a) * r, -1.1 + Math.random() * 0.5, Math.sin(a) * r, s);
    }
    // Pocas nubes flotando en el horizonte (más pequeñas y más bajas que antes)
    for (let i = 0; i < 10; i++) {
        const a = Math.random() * Math.PI * 2, r = radio * (0.75 + Math.random() * 0.5);
        _puff(Math.cos(a) * r, 1.2 + Math.random() * 2.0, Math.sin(a) * r,
              0.8 + Math.random() * 1.2, 0.4 + Math.random() * 0.15);
    }
    // Niebla a ras de suelo: discos planos translúcidos que dan efecto de humo/vapor
    const matNiebla = new THREE.MeshStandardMaterial({
        color: 0xffffff, transparent: true, opacity: 0.18,
        roughness: 1.0, metalness: 0.0, fog: false, depthWrite: false,
    });
    for (let i = 0; i < 40; i++) {
        const r = Math.sqrt(Math.random()) * radio * 0.85;
        const a = Math.random() * Math.PI * 2;
        const s = 1.5 + Math.random() * 3.5;
        const m = new THREE.Mesh(new THREE.CircleGeometry(s, 10), matNiebla);
        m.rotation.x = -Math.PI / 2;
        m.position.set(Math.cos(a) * r, 0.04 + Math.random() * 0.3, Math.sin(a) * r);
        g.add(m);
    }
    return g;
}

// Suelo de LAVA ('otro', tipo_suelo='lava'): roca oscura con charcos incandescentes.
function _crearSueloLava(radio) {
    const g = new THREE.Group();
    const base = new THREE.Mesh(
        new THREE.CircleGeometry(radio, 48),
        new THREE.MeshStandardMaterial({ color: 0x1a0d08, roughness: 0.95, metalness: 0.0,
            emissive: 0x3a1402, emissiveIntensity: 0.4 }),
    );
    base.rotation.x = -Math.PI / 2; base.position.y = 0.001; base.receiveShadow = true; g.add(base);
    for (let i = 0; i < 44; i++) {
        const a = Math.random() * Math.PI * 2, r = Math.sqrt(Math.random()) * radio * 0.95;
        const s = 0.4 + Math.random() * 1.6;
        const m = new THREE.Mesh(new THREE.CircleGeometry(s, 12),
            new THREE.MeshBasicMaterial({ color: new THREE.Color().setHSL(0.055, 1.0, 0.48 + Math.random() * 0.16), fog: false }));
        m.rotation.x = -Math.PI / 2; m.position.set(Math.cos(a) * r, 0.02, Math.sin(a) * r);
        g.add(m);
    }
    return g;
}

// Suelo de CRISTAL/HIELO ('otro', tipo_suelo='cristal'): translúcido, brillante, especular.
function _crearSueloCristal(radio) {
    const m = new THREE.Mesh(
        new THREE.CircleGeometry(radio, 64),
        new THREE.MeshStandardMaterial({ color: 0xbfe6ff, roughness: 0.08, metalness: 0.25,
            emissive: 0x2a4a66, emissiveIntensity: 0.15, transparent: true, opacity: 0.55,
            side: THREE.DoubleSide, fog: false }),
    );
    m.rotation.x = -Math.PI / 2; m.position.y = 0.001; m.receiveShadow = true;
    return m;
}

// TECHO de nubes bajas ('otro', tipo_techo='nubes_bajas'): manto de nubes a ~10 de altura
// que oculta lo alto (un tallo/torre gigante se pierde dentro y no se ve dónde acaba).
function _crearTechoNubes(radio) {
    const g = new THREE.Group();
    const mat = new THREE.MeshStandardMaterial({ color: 0xeef2fb, roughness: 1.0, metalness: 0.0,
        emissive: 0xdfe8ff, emissiveIntensity: 0.2, transparent: true, opacity: 0.97, fog: false });
    for (let i = 0; i < 120; i++) {
        const a = Math.random() * Math.PI * 2, r = Math.sqrt(Math.random()) * radio * 1.35;
        const s = 1.6 + Math.random() * 2.8;
        const m = new THREE.Mesh(new THREE.SphereGeometry(s, 8, 6), mat);
        m.position.set(Math.cos(a) * r, 9.5 + Math.random() * 3.2, Math.sin(a) * r);
        m.scale.y = 0.4 + Math.random() * 0.2;
        g.add(m);
    }
    return g;
}

function crearSuelo(nodo, idEscena, radio, tipoAmbiente, tipoCielo, colorOverride, tipoSuelo) {
    if (tipoSuelo === 'nubes')          return _crearSueloNubes(radio);
    if (tipoSuelo === 'agua')           return _crearSueloAgua(radio, 0.9);
    if (tipoSuelo === 'lava')           return _crearSueloLava(radio);
    if (tipoSuelo === 'cristal')        return _crearSueloCristal(radio);
    if (tipoAmbiente === 'sobre_agua') return _crearSueloAgua(radio, 0.92);
    if (tipoAmbiente === 'barco')      return _crearSueloAgua(radio, 0.68);  // translúcido: se ven los peces
    // Interiores construidos (interior / interior_grande): suelo CUADRADO que casa con
    // las paredes en caja, con color de la paleta de habitación. Cueva y exteriores → círculo.
    const esInteriorCaja = (tipoAmbiente === 'habitacion' || tipoAmbiente === 'interior' || tipoAmbiente === 'interior_grande');
    const geo = esInteriorCaja
        ? new THREE.PlaneGeometry(2 * radio, 2 * radio)
        : new THREE.CircleGeometry(radio, 48);
    const esNieve = tipoCielo && tipoCielo.includes('nevad');
    let color;
    if (esInteriorCaja) {
        color = _paletaInterior(tipoCielo).suelo;
    } else if (colorOverride) {
        color = parseInt(colorOverride.replace('#', ''), 16);
    } else {
        color = esNieve ? 0xf0f0f0 : (_COLOR_SUELO[tipoAmbiente] ?? TIPO_COLOR.suelo);
    }
    const mat = new THREE.MeshLambertMaterial({ color, side: THREE.FrontSide });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.set(0, 0.001, 0);
    mesh.receiveShadow = true;
    mesh.userData = nodo;
    return mesh;
}

// ─── Billboard de color (fallback para modelos 3D no encontrados) ──────────

function crearBillboard(nodo) {
    const grupo = new THREE.Group();
    const geo = new THREE.PlaneGeometry(nodo.ancho, nodo.alto);
    const mat = new THREE.MeshBasicMaterial({
        color: TIPO_COLOR[nodo.tipo] ?? 0xCCCCCC,
        transparent: true, opacity: 0.85,
        side: THREE.DoubleSide, depthWrite: false,
    });
    grupo.add(new THREE.Mesh(geo, mat));
    grupo.add(new THREE.LineSegments(
        new THREE.EdgesGeometry(geo),
        new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.3 })
    ));

    // Etiqueta
    const anchoEt = Math.min(nodo.ancho * 1.05, 2.4);
    const altoEt  = anchoEt * (72 / 320);
    const etMesh  = new THREE.Mesh(
        new THREE.PlaneGeometry(anchoEt, altoEt),
        new THREE.MeshBasicMaterial({ map: crearTexturaEtiqueta(nodo.nombre || nodo.id), transparent: true, depthWrite: false })
    );
    etMesh.position.set(0, nodo.alto / 2 + altoEt / 2 + 0.06, 0.01);
    grupo.add(etMesh);

    grupo.position.set(nodo.posicion.x, nodo.posicion.y, nodo.posicion.z);
    grupo.userData = nodo;
    grupo.onBeforeRender = function(renderer, scene, camera) { this.lookAt(camera.position); };
    return grupo;
}

// ─── Modelo 3D desde poly.pizza (glTF) ────────────────────────────────────

function crearModelo3D(nodo, scene) {
    /**
     * Carga el modelo glTF de forma asíncrona y lo añade a la escena.
     * Centrado automático usando bounding box.
     * Escalado para que quepa en ancho×alto del nodo.
     * Fallback a billboard si la carga falla.
     */
    if (!window.THREE.GLTFLoader) {
        console.warn(`[WorldWeaver] GLTFLoader no disponible. Billboard fallback para '${nodo.id}'`);
        scene.add(crearBillboard(nodo));
        return;
    }

    const loader = new THREE.GLTFLoader();
    loader.load(
        nodo.gltf_url,
        (gltf) => {
            const model = gltf.scene;

            // 1. Calcular bounding box del modelo tal como viene del fichero
            const box  = new THREE.Box3().setFromObject(model);
            const size = box.getSize(new THREE.Vector3());
            const center = box.getCenter(new THREE.Vector3());

            // 2. Escalar para que encaje en las dimensiones del nodo.
            //    Para personajes del catálogo Quaternius se escala solo por altura:
            //    la T-pose extiende los brazos y hace que size.x sea ~3u (envergadura),
            //    lo que hundiría el Math.min a una escala ridículamente pequeña.
            let targetAlto = nodo.alto;
            let esPersonajeCatalogo = false;
            if (nodo.tipo === 'personaje' &&
                nodo.gltf_url && nodo.gltf_url.includes('/assets/characters/'))
            {
                esPersonajeCatalogo = true;
                const _reg = (typeof SCENE_GRAPH !== 'undefined' && SCENE_GRAPH.registro_personajes) || {};
                const _skin = _reg[nodo.id];
                if (_skin && _skin.talla && _TALLA_ALTURA[_skin.talla]) {
                    targetAlto = _TALLA_ALTURA[_skin.talla];
                }
            }
            //    Importante: se limita también la PROFUNDIDAD (size.z) con un presupuesto
            //    GENEROSO (3× la mayor dimensión declarada). Así se recorta solo un modelo
            //    con Z desproporcionada (p.ej. una rama de canela de poly.pizza, que de otro
            //    modo se cuela gigante porque el escalado solo miraba X e Y), SIN encoger
            //    objetos legítimamente largos (un carro, una horca, un banco).
            let escala;
            if (esPersonajeCatalogo) {
                escala = targetAlto / Math.max(size.y, 0.001);
            } else if (nodo.tam_real) {
                // Tamaño coherente fijado por el pase del Constructor: escala INVARIANTE
                // A LA ORIENTACIÓN — el eje más largo del modelo se lleva a tam_real,
                // preservando proporciones (un palo mide igual tumbado o de pie).
                escala = nodo.tam_real / Math.max(size.x, size.y, size.z, 0.001);
            } else {
                const _escalaXY = Math.min(
                    nodo.ancho / Math.max(size.x, 0.001),
                    targetAlto / Math.max(size.y, 0.001)
                );
                const _budgetZ = Math.max(nodo.ancho, targetAlto) * 3.0;
                escala = Math.min(_escalaXY, _budgetZ / Math.max(size.z, 0.001));
            }
            model.scale.setScalar(escala);

            // 3. Posicionar el modelo correctamente en el espacio del grupo
            //
            //    En Three.js: world_pos = position + scale × local_vertex
            //
            //    Queremos:
            //      · Base del modelo en y=0 del grupo (apoya en el suelo)
            //        → position.y = -escala × box.min.y
            //      · Centro del modelo en x=0 y z=0 del grupo
            //        → position.x = -escala × center.x
            //        → position.z = -escala × center.z
            //
            //    Esta fórmula es correcta para cualquier origen de modelo
            //    (base centrada, origen en suelo, origen arbitrario, etc.)
            model.position.set(
                -escala * center.x,
                -escala * box.min.y,
                -escala * center.z
            );

            // 4. Sombras y niebla por tipo de nodo
            const distCentro = Math.sqrt(nodo.posicion.x ** 2 + nodo.posicion.z ** 2);
            const sinNiebla = nodo.tipo === 'personaje'
                           || nodo.tipo === 'objeto'
                           || (nodo.tipo === 'decorado' && distCentro < 4.5);
            model.traverse(child => {
                if (child.isMesh) {
                    child.castShadow    = true;
                    child.receiveShadow = true;
                    if (sinNiebla && child.material) {
                        // Personajes y objetos narrativos nunca se difuminan con la niebla
                        // — deben ser siempre visibles independientemente de la posición del jugador
                        const mats = Array.isArray(child.material) ? child.material : [child.material];
                        mats.forEach(m => { m.fog = false; });
                    }
                }
            });

            // 5. Crear grupo y posicionarlo en las coordenadas del SceneGraph
            //    nodo.posicion.y lo ignoramos: la altura la gestiona el modelo internamente
            const grupo = new THREE.Group();
            grupo.add(model);
            grupo.position.set(nodo.posicion.x, 0, nodo.posicion.z);
            grupo.userData = nodo;

            // Interiores en caja: girar el mobiliario PEGADO A LAS PAREDES para que encare
            // la sala (un armario/cama/estantería contra la pared debe mirar al centro, no de
            // lado). atan2(x,z) hace que el frente del modelo (-Z) apunte al centro. Los
            // personajes no se giran (van al centro y mantienen su orientación de diálogo).
            if ((_tipoAmbiente === 'habitacion' || _tipoAmbiente === 'interior' || _tipoAmbiente === 'interior_grande') && nodo.tipo !== 'personaje') {
                const _r = SCENE_GRAPH.radio_escena ?? 10;
                const _half = _r - 1.5;
                const _x = nodo.posicion.x, _z = nodo.posicion.z;
                // Objetos PLANOS de suelo (alfombra, tapiz, tapete...) NUNCA se giran ni
                // cuelgan: se quedan tumbados en el suelo aunque estén pegados a una pared
                // (subidos un pelín para no "vibrar" por z-fighting con el suelo).
                // Se detectan por NOMBRE (lista) o por GEOMETRÍA: una pieza mucho más
                // ancha/larga que alta (size.y ≪ size.x|z) es algo tumbado en el suelo, sea
                // cual sea su nombre. Lo segundo atrapa la alfombra que llega con un nombre
                // inesperado o un modelo de poly.pizza que el regex no cubre — y NO confunde
                // un cuadro (alto y fino en profundidad: size.y NO es pequeña frente a size.x).
                const _nomPlano = (nodo.nombre || '').toLowerCase();
                const _planoPorNombre = /alfombra|moqueta|tapete|felpudo|estera|alfombrilla|rug|carpet/.test(_nomPlano);
                const _planoPorGeom = size.y < 0.30 * Math.max(size.x, size.z);
                const _esPlano = _planoPorNombre || _planoPorGeom;
                if (_esPlano) grupo.position.y = 0.05;
                if (!_esPlano && Math.max(Math.abs(_x), Math.abs(_z)) > _half * 0.55) {
                    // Gira el mueble para que encare la sala PERPENDICULAR a su pared más
                    // cercana (de frente, plano contra el muro — no de lado ni en diagonal).
                    const _enParedX = Math.abs(_x) >= Math.abs(_z);
                    if (_enParedX) grupo.rotation.y = (_x > 0 ? Math.PI / 2 : -Math.PI / 2);
                    else           grupo.rotation.y = (_z < 0 ? Math.PI : 0);
                    // SOLO se cuelgan a la pared cuadros/espejos/retratos (arte de pared real).
                    // El resto se queda en el SUELO contra la pared (NO todo se cuelga).
                    const _nom = (nodo.nombre || '').toLowerCase();
                    // Mobiliario de SUELO de pie: NUNCA se cuelga aunque el nombre mencione un
                    // objeto mural (p.ej. "estantería con relojes" lleva 'reloj' pero es un mueble
                    // que va en el suelo). Se comprueba ANTES que el colgado.
                    const _muebleSuelo = /estanter|estante|armario|vitrina|aparador|c[oó]moda|alacena|mueble|mesa|banco|repisa|c[oó]nsola|escritorio|cajoner/.test(_nom);
                    // Arte/objetos MURALES se elevan y cuelgan; el resto se queda en el SUELO en
                    // la celda donde lo puso el Director (que ya distingue pared vs centro).
                    if (!_muebleSuelo && /cuadro|espejo|retrato|pintura|lienzo|reloj|mapa|estandarte|escudo|placa|tapiz/.test(_nom)) {
                        if (_enParedX) grupo.position.x = Math.sign(_x || 1) * (_r - 0.35);
                        else           grupo.position.z = Math.sign(_z || 1) * (_r - 0.35);
                        // Altura según el tamaño: borde inferior ~1.0 m (sobre el mobiliario)
                        // y sube con la pieza, en vez de un 1.3 fijo que enterraba los espejos
                        // grandes y dejaba flotando los marcos pequeños. Tope para no clipar techo.
                        grupo.position.y = Math.min(1.0 + (nodo.alto || 1) / 2, 3.0);
                    }
                }
            }

            // Barco: los objetos dentro del radio de la CUBIERTA se elevan a su altura;
            // los de fuera se quedan en el agua (y=0), alcanzables al desembarcar.
            if (_tipoAmbiente === 'barco') {
                const _dc = Math.hypot(nodo.posicion.x, nodo.posicion.z);
                if (_dc < (window._BARCO_DECK_R ?? 4.6)) grupo.position.y = (window._BARCO_DECK_H ?? 1.0) + 0.1;
            }

            // Escena de conversación (idiomas): cada personaje MIRA hacia el/los otro(s)
            // personaje(s), como si hablasen entre sí. A diferencia del mobiliario, los GLB
            // humanos de Quaternius miran a +Z, así que para encararlos al objetivo se usa
            // rotation.y = atan2(tx - x, tz - z) (vector self→objetivo, NO el inverso del mueble).
            if (SCENE_GRAPH.escena_conversacion && nodo.tipo === 'personaje') {
                const otros = (SCENE_GRAPH.nodos || []).filter(n => n.tipo === 'personaje' && n.id !== nodo.id);
                if (otros.length) {
                    const tx = otros.reduce((s, n) => s + n.posicion.x, 0) / otros.length;
                    const tz = otros.reduce((s, n) => s + n.posicion.z, 0) / otros.length;
                    grupo.rotation.y = Math.atan2(tx - nodo.posicion.x, tz - nodo.posicion.z);
                }
            }

            scene.add(grupo);

            const esPersonajeNoHumano = nodo.tipo === 'personaje' && !esPersonajeCatalogo;

            // En espacio y bajo_el_agua los modelos narrativos flotan — salvo los
            // personajes no-humanos, cuya posición la gobierna la animación procedural
            // (su "respiración" idle ya les da movimiento; flotar la pisaría cada frame).
            if (_AMBIENTES_FLOTANTES.has(_tipoAmbiente) && !esPersonajeNoHumano) {
                const amp = 0.15 + Math.random() * 0.25;
                grupo.position.y = amp;
                _floatingObjects.push({ type: 'float', mesh: grupo, baseY: amp,
                    freq: 0.1 + Math.random() * 0.2, phase: Math.random() * Math.PI * 2, amp });
            }

            if (window.PersonajesManager) {
                if (esPersonajeCatalogo) {
                    // Personajes del catálogo Quaternius: apariencia + animaciones esqueléticas
                    const skin = (typeof SCENE_GRAPH !== 'undefined' && SCENE_GRAPH.registro_personajes || {})[nodo.id];
                    PersonajesManager.registrar(nodo.id, model, gltf, skin);
                } else if (esPersonajeNoHumano) {
                    // Personajes no-humanos (poly.pizza, rígidos): animación procedural por transform
                    PersonajesManager.registrarProcedural(nodo.id, grupo, size.y * escala);
                }
            }

            console.log(`[WorldWeaver] ✓ Modelo 3D cargado: '${nodo.id}' (${nodo.keyword_busqueda ?? nodo.nombre})`);
        },
        undefined,
        (error) => {
            console.warn(`[WorldWeaver] Error cargando modelo '${nodo.id}' desde ${nodo.gltf_url}. Billboard fallback.`, error);
            scene.add(crearBillboard(nodo));
        }
    );
}

// ─── Bosque procedural (geometría Three.js, sin poly.pizza) ──────────────

function _crearArbolBosque(x, z, escala, colorTronco, colorCopa) {
    const g = new THREE.Group();
    const tronco = new THREE.Mesh(
        new THREE.CylinderGeometry(0.08 * escala, 0.13 * escala, 0.85 * escala, 6),
        new THREE.MeshLambertMaterial({ color: colorTronco })
    );
    tronco.position.y = 0.42 * escala;
    tronco.castShadow = true;
    g.add(tronco);
    const copaMat = new THREE.MeshLambertMaterial({ color: colorCopa });
    const copa = new THREE.Mesh(new THREE.SphereGeometry(0.55 * escala, 6, 5), copaMat);
    copa.position.y = 1.12 * escala;
    copa.castShadow = true;
    g.add(copa);
    const copa2 = new THREE.Mesh(new THREE.SphereGeometry(0.38 * escala, 6, 5), copaMat);
    copa2.position.set(0.26 * escala, 1.48 * escala, 0.1 * escala);
    copa2.castShadow = true;
    g.add(copa2);
    g.position.set(x, 0, z);
    return g;
}

function _crearRocaBosque(x, z, sx, sy, sz) {
    const geo = new THREE.DodecahedronGeometry(0.28 + Math.random() * 0.22, 0);
    const m = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({ color: 0x7a7060 }));
    m.scale.set(sx, sy, sz);
    m.position.set(x, 0, z);
    m.rotation.y = Math.random() * Math.PI * 2;
    return m;
}

function _poblarBosqueProcedural(radio, scene) {
    const rng = (a, b) => a + Math.random() * (b - a);
    const COPAS   = [0x2d6a1f, 0x3a7d2a, 0x236018, 0x4a8530, 0x1e5214, 0x557a30];
    const TRONCOS = [0x5c3a1e, 0x6b4226, 0x4a2e12];
    // Tres anillos: lejano (80-97%), medio (44-70%), cercano (22-52% — zona explorable)
    const N_FAR = 64, N_MID = 18, N_NEAR = 20, N_ROCAS = 14;

    for (let i = 0; i < N_FAR; i++) {
        const r = rng(radio * 0.80, radio * 0.97);
        const ang = Math.random() * Math.PI * 2;
        const esc = rng(1.0, 2.0);
        scene.add(_crearArbolBosque(
            r * Math.sin(ang), r * Math.cos(ang), esc,
            TRONCOS[Math.floor(Math.random() * TRONCOS.length)],
            COPAS[Math.floor(Math.random() * COPAS.length)]
        ));
    }
    for (let i = 0; i < N_MID; i++) {
        const r = rng(radio * 0.44, radio * 0.70);
        const ang = Math.random() * Math.PI * 2;
        const esc = rng(0.65, 1.35);
        scene.add(_crearArbolBosque(
            r * Math.sin(ang), r * Math.cos(ang), esc,
            TRONCOS[Math.floor(Math.random() * TRONCOS.length)],
            COPAS[Math.floor(Math.random() * COPAS.length)]
        ));
    }
    for (let i = 0; i < N_NEAR; i++) {
        const r = rng(radio * 0.22, radio * 0.52);
        const ang = Math.random() * Math.PI * 2;
        // Árboles más pequeños cerca del centro para no obstruir la zona narrativa
        const esc = rng(0.35, 0.80) * (0.6 + 0.4 * (r / (radio * 0.52)));
        scene.add(_crearArbolBosque(
            r * Math.sin(ang), r * Math.cos(ang), esc,
            TRONCOS[Math.floor(Math.random() * TRONCOS.length)],
            COPAS[Math.floor(Math.random() * COPAS.length)]
        ));
    }
    for (let i = 0; i < N_ROCAS; i++) {
        const r = rng(radio * 0.22, radio * 0.86);
        const ang = Math.random() * Math.PI * 2;
        scene.add(_crearRocaBosque(r * Math.sin(ang), r * Math.cos(ang),
            rng(0.8, 1.6), rng(0.5, 1.0), rng(0.7, 1.4)));
    }
    console.log(`[WorldWeaver] Bosque procedural: ${N_FAR + N_MID + N_NEAR} árboles, ${N_ROCAS} rocas`);
}

// ─── Espacio procedural (asteroides Three.js + campo de estrellas) ────────

function _crearEspacioProcedural(radio, scene) {
    const rng = (a, b) => a + Math.random() * (b - a);
    const N_ASTEROIDES = 28;
    const matAst = new THREE.MeshLambertMaterial({ color: 0x887766 });
    for (let i = 0; i < N_ASTEROIDES; i++) {
        const r = rng(radio * 0.70, radio * 0.96);
        const ang = Math.random() * Math.PI * 2;
        const esc = rng(0.25, 1.1);
        const geo = new THREE.DodecahedronGeometry(esc, 0);
        const m = new THREE.Mesh(geo, matAst);
        const baseY = rng(0.5, 8.0);
        m.position.set(r * Math.sin(ang), baseY, r * Math.cos(ang));
        m.rotation.set(rng(0, Math.PI), rng(0, Math.PI), rng(0, Math.PI));
        scene.add(m);
        _floatingObjects.push({ type: 'spin', mesh: m, baseY,
            freq: rng(0.05, 0.18), phase: rng(0, Math.PI * 2), amp: rng(0.2, 0.9),
            rotSpeed: rng(0.015, 0.06) });
    }
    // Campo de estrellas denso
    const N = 700;
    const pos = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) {
        const theta = Math.random() * Math.PI * 2;
        const phi   = Math.random() * Math.PI;
        const r = radio * rng(0.86, 0.99);
        pos[i*3]   = r * Math.sin(phi) * Math.cos(theta);
        pos[i*3+1] = r * Math.cos(phi) + 4.0;
        pos[i*3+2] = r * Math.sin(phi) * Math.sin(theta);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    scene.add(new THREE.Points(geo, new THREE.PointsMaterial({
        color: 0xffffff, size: 0.14, sizeAttenuation: true, fog: false,
    })));
    console.log(`[WorldWeaver] Espacio procedural: ${N_ASTEROIDES} asteroides, ${N} estrellas`);
}

// ─── Pez procedural (bajo el agua) ───────────────────────────────────────

function _crearPezProcedural(color, escala) {
    const g = new THREE.Group();
    const mat = new THREE.MeshLambertMaterial({ color });
    const body = new THREE.Mesh(new THREE.SphereGeometry(escala, 6, 4), mat);
    body.scale.set(1.6, 0.75, 1.0);
    g.add(body);
    const tail = new THREE.Mesh(new THREE.ConeGeometry(escala * 0.55, escala * 0.9, 4), mat);
    tail.rotation.z = Math.PI / 2;
    tail.position.x = escala * 1.5;
    g.add(tail);
    const fin = new THREE.Mesh(new THREE.ConeGeometry(escala * 0.2, escala * 0.4, 3), mat);
    fin.position.set(-escala * 0.2, escala * 0.75, 0);
    g.add(fin);
    return g;
}

// ─── Fondo marino procedural (totalmente generativo, como espacio) ────────

function _crearFondoMarinoTD(radio, scene) {
    const rng = (a, b) => a + Math.random() * (b - a);

    // Sobrescribir cielo y niebla para aspecto submarino (va después de aplicarCielo)
    scene.background = new THREE.Color(0x031a28);
    scene.fog = new THREE.Fog(0x031a28, 3.6, radio - 5.6 - 1.0);
    scene.add(new THREE.AmbientLight(0x1a5070, 0.55));

    // ── Rayos de luz desde la superficie (inspirado en cielo_magico / aurora) ──
    const RAYO_COLS = [0x60c8ff, 0x40aaee, 0x80d8ff, 0x30a8e0];
    const N_RAYOS = 10;
    for (let i = 0; i < N_RAYOS; i++) {
        const ang      = (i / N_RAYOS) * Math.PI * 2 + rng(-0.4, 0.4);
        const r_rayo   = rng(1.0, 5.5);
        const altoRayo = rng(4.0, 8.0);
        const mat = new THREE.MeshBasicMaterial({
            color: RAYO_COLS[Math.floor(Math.random() * RAYO_COLS.length)],
            transparent: true, opacity: rng(0.04, 0.09),
            side: THREE.DoubleSide, depthWrite: false, fog: false,
        });
        const rayo = new THREE.Mesh(new THREE.ConeGeometry(rng(0.6, 1.8), altoRayo, 6, 1, true), mat);
        rayo.rotation.z = Math.PI;  // base arriba (ancho en superficie), ápice abajo
        const baseY = altoRayo * 0.5 + rng(4.0, 7.0);
        rayo.position.set(r_rayo * Math.sin(ang), baseY, r_rayo * Math.cos(ang));
        scene.add(rayo);
        _floatingObjects.push({ type: 'ray', mesh: rayo, baseY, mat,
            baseOp: mat.opacity, freq: rng(0.15, 0.30), phase: rng(0, Math.PI * 2), amp: rng(0.1, 0.25) });
    }

    // ── Burbujas ascendentes (3 nubes de Points con velocidades distintas) ──
    for (let g = 0; g < 3; g++) {
        const N = 110;
        const pos = new Float32Array(N * 3);
        for (let i = 0; i < N; i++) {
            const r_b = rng(0.5, radio * 0.78);
            const ang = Math.random() * Math.PI * 2;
            pos[i*3]   = r_b * Math.sin(ang);
            pos[i*3+1] = rng(0, 11.0);
            pos[i*3+2] = r_b * Math.cos(ang);
        }
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
        const pts = new THREE.Points(geo, new THREE.PointsMaterial({
            color: 0xaaddff, size: 0.07, transparent: true, opacity: 0.5, fog: false,
        }));
        scene.add(pts);
        _floatingObjects.push({ type: 'rising', mesh: pts, speed: rng(0.20, 0.50), maxY: 11.0 });
    }

    // ── Peces flotantes (repartidos por todo el cilindro) ──
    const PECES_COLS = [0xff5500, 0x0077ff, 0xffcc00, 0xff2299, 0x00ccaa, 0xff8800, 0xee3311];
    const N_PECES = 28;
    for (let i = 0; i < N_PECES; i++) {
        const r_f   = rng(radio * 0.10, radio * 0.88);
        const ang   = Math.random() * Math.PI * 2;
        const pez   = _crearPezProcedural(PECES_COLS[Math.floor(Math.random() * PECES_COLS.length)], rng(0.12, 0.32));
        const baseY = rng(0.6, 7.0);
        pez.position.set(r_f * Math.sin(ang), baseY, r_f * Math.cos(ang));
        pez.rotation.y = ang + Math.PI;
        scene.add(pez);
        _floatingObjects.push({ type: 'float', mesh: pez, baseY,
            freq: rng(0.15, 0.40), phase: rng(0, Math.PI * 2), amp: rng(0.1, 0.35) });
    }

    // ── Coral en el suelo (pequeños racimos, dispersos por todo el fondo) ──
    const CORAL_COLS = [0xff4422, 0xff7700, 0xff88bb, 0xffaa44, 0xee2255, 0xff6644];
    const N_CORAL_SUELO = 30;
    for (let i = 0; i < N_CORAL_SUELO; i++) {
        const r_c  = rng(radio * 0.05, radio * 0.94);
        const ang  = Math.random() * Math.PI * 2;
        const color = CORAL_COLS[Math.floor(Math.random() * CORAL_COLS.length)];
        const mat  = new THREE.MeshLambertMaterial({ color });
        const g    = new THREE.Group();
        // Tronco central
        const nRamas = 2 + Math.floor(Math.random() * 3);
        const altoBase = rng(0.15, 0.55);
        g.add(new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.07, altoBase, 5), mat));
        // Ramas cortas
        for (let b = 0; b < nRamas; b++) {
            const rama = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.04, rng(0.1, 0.3), 4), mat);
            rama.position.set(rng(-0.12, 0.12), altoBase * 0.5 + rng(0, 0.12), rng(-0.12, 0.12));
            rama.rotation.set(rng(-0.6, 0.6), rng(0, Math.PI * 2), rng(-0.5, 0.5));
            g.add(rama);
        }
        g.position.set(r_c * Math.sin(ang), altoBase / 2, r_c * Math.cos(ang));
        scene.add(g);
    }

    // ── Kelp (cilindros altos que se balancean, anillo medio-exterior) ──
    const N_KELP = 22;
    for (let i = 0; i < N_KELP; i++) {
        const r_k = rng(radio * 0.35, radio * 0.97);
        const ang = Math.random() * Math.PI * 2;
        const alto = rng(0.8, 2.0);
        const kelp = new THREE.Mesh(
            new THREE.CylinderGeometry(0.04, 0.07, alto, 5),
            new THREE.MeshLambertMaterial({ color: 0x1f5c10 })
        );
        const baseY = alto / 2;
        kelp.position.set(r_k * Math.sin(ang), baseY, r_k * Math.cos(ang));
        scene.add(kelp);
        _floatingObjects.push({ type: 'sway', mesh: kelp, baseY,
            freq: rng(0.25, 0.55), phase: rng(0, Math.PI * 2), amp: rng(0.06, 0.16) });
    }

    console.log(`[WorldWeaver] Fondo marino: ${N_PECES} peces, ${N_CORAL_SUELO} corales, ${N_KELP} kelp, ${N_RAYOS} rayos de luz`);
}

// ─── Actualización de objetos animados (llamar desde animate()) ──────────

function actualizarFlotacion(t) {
    for (const obj of _floatingObjects) {
        switch (obj.type) {
            case 'rising':
                // Burbuja asciende y vuelve al fondo en bucle
                obj.mesh.position.y = (t * obj.speed * 1.8) % obj.maxY;
                break;
            case 'float':
            case 'sway':
                obj.mesh.position.y = obj.baseY + Math.sin(t * obj.freq + obj.phase) * obj.amp;
                break;
            case 'ray':
                // Pulsa opacidad + movimiento sutil (como aurora)
                obj.mat.opacity = Math.max(0.01, obj.baseOp + Math.sin(t * obj.freq + obj.phase) * 0.028);
                obj.mesh.position.y = obj.baseY + Math.sin(t * obj.freq * 0.5 + obj.phase) * obj.amp;
                break;
            case 'spin':
                // Asteroide: gira lentamente + flota
                obj.mesh.rotation.y = t * obj.rotSpeed;
                obj.mesh.rotation.x = Math.sin(t * obj.rotSpeed * 0.7 + obj.phase) * 0.4;
                obj.mesh.position.y = obj.baseY + Math.sin(t * obj.freq + obj.phase) * obj.amp;
                break;
            case 'agua': {
                // Olas: desplaza el eje Z de cada vértice del plano (que tras rotar es la
                // altura) con dos senos cruzados; recalcula normales para que reflejen la luz.
                const pos = obj.mesh.geometry.attributes.position;
                for (let i = 0; i < pos.count; i++) {
                    const x = pos.getX(i), y = pos.getY(i);
                    pos.setZ(i, Math.sin(x * 0.30 + t * 1.0) * obj.amp
                              + Math.cos(y * 0.40 + t * 0.80) * obj.amp
                              + Math.sin((x + y) * 0.80 + t * 1.7) * obj.amp * 0.4);  // rizo fino
                }
                pos.needsUpdate = true;
                obj.mesh.geometry.computeVertexNormals();
                break;
            }
        }
    }
}

// ─── Barco (tipo_ambiente 'barco') ────────────────────────────────────────
// Plataforma-cubierta de madera sobre el agua, en 3 variantes (balsa / barco / galeón),
// elegidas determinísticamente por la escena. Fija window._BARCO_DECK_H/R (los lee
// index.html para la altura de cámara, el clamp y la barrera física).
function _hashCadena(s) {
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
}

// Timón fijo de poly.pizza (Wood Wheel, CC-BY) — siempre el mismo, gira en el loop.
const _URL_TIMON = 'https://static.poly.pizza/8fcaf8e9-720e-4d93-95f9-ab15769745eb.glb';

const _VARIANTES_BARCO = {
    balsa:  { H: 1.5, R: 5.6, mastiles: 1, hull: 0x6b4a2e, deck: 0x9a7548 },
    barco:  { H: 2.1, R: 6.2, mastiles: 1, hull: 0x5e3f26, deck: 0x8a6a44 },
    galeon: { H: 2.8, R: 6.8, mastiles: 2, hull: 0x4a3320, deck: 0x7a5a38, popa: true },
};

// Elige la variante de barco y fija window._BARCO_DECK_H/R. DEBE llamarse ANTES de
// cargar los objetos (para que la elevación a cubierta use la altura correcta y no la
// por defecto, que dejaba objetos hundidos en modelos cacheados).
let _barcoVariante = null;
function _prepararBarco() {
    const tipos = ['balsa', 'barco', 'galeon'];
    // El Constructor fija la variante (y coloca la rejilla de cubierta con su radio).
    // Si está, la usamos para que casco y rejilla coincidan; si no (mundos antiguos),
    // caemos al hash de siempre.
    let nombre = SCENE_GRAPH.variante_barco;
    if (!nombre || !_VARIANTES_BARCO[nombre]) {
        const semilla = (SCENE_GRAPH.id_escena || 'barco') + ((SCENE_GRAPH.cielo && SCENE_GRAPH.cielo.color_fondo) || '');
        nombre = tipos[_hashCadena(semilla) % 3];
    }
    _barcoVariante = _VARIANTES_BARCO[nombre];
    window._BARCO_DECK_H = _barcoVariante.H;
    window._BARCO_DECK_R = SCENE_GRAPH.radio_cubierta ?? _barcoVariante.R;
}

function _crearBarco(scene) {
    if (!_barcoVariante) _prepararBarco();
    const v = _barcoVariante;
    const H = v.H, R = v.R;
    console.log(`[WorldWeaver] Barco: variante H=${H}, R=${R}`);

    const matCasco = new THREE.MeshLambertMaterial({ color: v.hull });
    const matCub   = new THREE.MeshLambertMaterial({ color: v.deck });
    const matBarra = new THREE.MeshLambertMaterial({ color: 0x3a2818 });

    // Casco (cilindro cónico): su TOPE coincide con el plano de cubierta (y=H), para que
    // los objetos apoyen sobre la cubierta y no queden hundidos en un "cuenco".
    const casco = new THREE.Mesh(new THREE.CylinderGeometry(R, R * 0.78, H + 0.9, 30), matCasco);
    casco.position.y = H - (H + 0.9) / 2; casco.receiveShadow = true; scene.add(casco);

    // Cubierta
    const cub = new THREE.Mesh(new THREE.CircleGeometry(R * 0.98, 30), matCub);
    cub.rotation.x = -Math.PI / 2; cub.position.y = H + 0.02; cub.receiveShadow = true; scene.add(cub);

    // Baranda: aro + postes
    const aro = new THREE.Mesh(new THREE.TorusGeometry(R * 0.97, 0.06, 8, 40), matBarra);
    aro.rotation.x = Math.PI / 2; aro.position.y = H + 0.6; scene.add(aro);
    for (let i = 0; i < 18; i++) {
        const a = i / 18 * Math.PI * 2;
        const poste = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.6, 6), matBarra);
        poste.position.set(Math.cos(a) * R * 0.97, H + 0.3, Math.sin(a) * R * 0.97);
        scene.add(poste);
    }

    // Castillo de popa elevado (galeón): plataforma a popa (+Z)
    if (v.popa) {
        const popa = new THREE.Mesh(new THREE.BoxGeometry(R * 1.1, 1.0, R * 0.7), matCasco);
        popa.position.set(0, H + 0.5, R * 0.55); scene.add(popa);
        const popaCub = new THREE.Mesh(new THREE.BoxGeometry(R * 1.05, 0.1, R * 0.65), matCub);
        popaCub.position.set(0, H + 1.0, R * 0.55); scene.add(popaCub);
    }

    // Mástiles + velas
    const matVela = new THREE.MeshLambertMaterial({ color: 0xeee6d2, side: THREE.DoubleSide });
    const zs = v.mastiles === 2 ? [-R * 0.35, R * 0.3] : [R * 0.05];
    for (let m = 0; m < v.mastiles; m++) {
        const z = zs[m], altoM = 5.0 + (v.popa ? 1.6 : 0);
        const mastil = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.17, altoM, 8), matBarra);
        mastil.position.set(0, H + altoM / 2, z); scene.add(mastil);
        const vela = new THREE.Mesh(new THREE.PlaneGeometry(R * 1.0, 2.9), matVela);
        vela.position.set(0, H + altoM * 0.6, z - 0.12); scene.add(vela);
    }

    // Timón: modelo poly.pizza FIJO (Wood Wheel), de pie sobre la cubierta y QUIETO.
    // El modelo es un DISCO (rueda); puede venir authored tumbado o de canto, así que
    // lo orientamos y escalamos según sus dimensiones reales en vez de asumir nada:
    //   1) ponerlo VERTICAL mirando al jugador (eje fino del disco → Z),
    //   2) escalar por el DIÁMETRO a ~1.3 m (un timón de barco), NUNCA por size.y
    //      (en una rueda fina tumbada, size.y es el grosor → la agrandaba gigante).
    if (window.THREE && THREE.GLTFLoader) {
        new THREE.GLTFLoader().load(_URL_TIMON, (gltf) => {
            const wheel = gltf.scene;

            // 1) Orientar de pie. El eje FINO (menor dimensión) es el eje de la rueda;
            //    debe apuntar en Z para que la cara del timón mire al jugador.
            let size = new THREE.Box3().setFromObject(wheel).getSize(new THREE.Vector3());
            if (size.y <= size.x && size.y <= size.z)       wheel.rotation.x = Math.PI / 2; // tumbada → levantar
            else if (size.x <= size.y && size.x <= size.z)  wheel.rotation.y = Math.PI / 2; // de canto lateral → girar
            // (si el eje fino ya es Z, se queda de pie mirando al jugador)
            wheel.updateMatrixWorld(true);

            // 2) Escalar por el diámetro (mayor dimensión ya orientada) a ~1.3 m.
            size = new THREE.Box3().setFromObject(wheel).getSize(new THREE.Vector3());
            wheel.scale.setScalar(1.3 / Math.max(size.x, size.y, size.z, 0.01));
            wheel.updateMatrixWorld(true);

            // 3) Centrar en XZ y apoyar la base en y=0 del grupo (ya escalado/rotado).
            const box = new THREE.Box3().setFromObject(wheel);
            const center = box.getCenter(new THREE.Vector3());
            wheel.position.set(-center.x, -box.min.y, -center.z);

            wheel.traverse(c => { if (c.isMesh) { c.castShadow = true; } });
            const g = new THREE.Group();
            g.add(wheel);
            g.position.set(0, H + 0.05, -R * 0.88);   // apoyado en cubierta, casi en el borde de proa (junto a la baranda)
            scene.add(g);
        }, undefined, () => { /* si falla la carga, simplemente no hay timón */ });
    }
    // (Los barriles/cofres y demás objetos de cubierta los pone el Director como
    //  decorados poly.pizza, colocados en la cubierta; no usamos props procedurales.)
}

// Vida submarina bajo la superficie (peces + algas), visible a través del agua translúcida.
// No interactiva (pura ambientación). Reutiliza la animación de _floatingObjects.
function _crearVidaSubmarina(radio, scene) {
    const rng = (a, b) => a + Math.random() * (b - a);
    const cols = [0xe88a3c, 0xd0c040, 0x8aa0c0, 0xc05550, 0xddddee];
    for (let i = 0; i < 16; i++) {
        const pez = new THREE.Mesh(
            new THREE.ConeGeometry(0.18, 0.6, 6),
            new THREE.MeshLambertMaterial({ color: cols[i % cols.length] })
        );
        pez.rotation.z = Math.PI / 2;
        const r = rng(2.0, radio * 0.6), a = rng(0, Math.PI * 2), baseY = rng(-3.6, -0.7);
        pez.position.set(Math.cos(a) * r, baseY, Math.sin(a) * r);
        pez.rotation.y = rng(0, Math.PI * 2);
        scene.add(pez);
        _floatingObjects.push({ type: 'float', mesh: pez, baseY, freq: rng(0.4, 0.9), phase: rng(0, 6), amp: rng(0.12, 0.3) });
    }
    for (let i = 0; i < 8; i++) {
        const h = rng(1.6, 3.2);
        const alga = new THREE.Mesh(
            new THREE.PlaneGeometry(0.32, h),
            new THREE.MeshLambertMaterial({ color: 0x2f6a3a, side: THREE.DoubleSide, transparent: true, opacity: 0.85 })
        );
        const r = rng(3, radio * 0.7), a = rng(0, Math.PI * 2);
        alga.position.set(Math.cos(a) * r, -4.6 + h / 2, Math.sin(a) * r);
        scene.add(alga);
        _floatingObjects.push({ type: 'float', mesh: alga, baseY: alga.position.y, freq: rng(0.3, 0.6), phase: rng(0, 6), amp: 0.12 });
    }
}

// ─── Función principal ────────────────────────────────────────────────────

function cargarSceneGraph(sceneGraph, scene) {
    const idEscena = sceneGraph.id_escena;
    const radio    = sceneGraph.radio_escena ?? 18.0;

    // Registrar tipo de ambiente activo (usado por crearModelo3D para flotación)
    _tipoAmbiente = sceneGraph.tipo_ambiente;
    // Barco: fijar la altura/radio de cubierta ANTES de cargar objetos, para que se
    // eleven a la cubierta correcta (no a la altura por defecto → no quedan hundidos).
    if (_tipoAmbiente === 'barco') _prepararBarco();

    let modelos3d = 0, billboards = 0;

    for (const nodo of sceneGraph.nodos) {
        if (nodo.tipo === 'fondo') {
            // Interiores construidos → habitación en caja (paredes + techo + puerta/ventanas).
            // Cueva (tipo_ambiente 'cueva') se deja como vacío + relleno ambiental.
            // En exteriores el cielo lo gestiona scene.background + sky.js.
            if (_tipoAmbiente === 'habitacion' || _tipoAmbiente === 'interior' || _tipoAmbiente === 'interior_grande') {
                scene.add(crearHabitacion(nodo, radio, sceneGraph.cielo.tipo));
            }
        } else if (nodo.tipo === 'suelo') {
            scene.add(crearSuelo(nodo, idEscena, radio, sceneGraph.tipo_ambiente, sceneGraph.cielo.tipo, sceneGraph.color_suelo, sceneGraph.tipo_suelo));
        } else if (nodo.gltf_url) {
            crearModelo3D(nodo, scene);  // asíncrono
            modelos3d++;
        } else if (nodo.tipo !== 'ambiente') {
            scene.add(crearBillboard(nodo));  // fallback (no para nodos de relleno sin modelo)
            billboards++;
        }
    }

    // Generación procedural para tipos de ambiente especiales
    if (_tipoAmbiente === 'espacio' || _tipoAmbiente === 'superficie_planeta') {
        _crearEspacioProcedural(radio, scene);
    } else if (_tipoAmbiente === 'bajo_el_agua') {
        _crearFondoMarinoTD(radio, scene);
    } else if (_tipoAmbiente === 'barco') {
        _crearBarco(scene);
        _crearVidaSubmarina(radio, scene);
    }

    // Techo de nubes bajas ('otro'): oculta lo alto (un tallo/torre gigante que se pierde).
    if (sceneGraph.tipo_techo === 'nubes_bajas') {
        scene.add(_crearTechoNubes(radio));
    }

    console.log(
        `[WorldWeaver] Escena '${idEscena}' (${sceneGraph.tipo_escena}, r=${radio}): ` +
        `${modelos3d} modelos 3D, ${billboards} billboards fallback`
    );

    return { update: actualizarFlotacion };
}