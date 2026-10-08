// Pilares 3D: carretes de hilo con tapas de madera, envueltos en lana, cintas y retazos,
// con ovillos y hebras colgando.
// Giran apenas solos y un poco más al bajar por la página.
// Si WebGL falla, queda el SVG de respaldo que ya está en la página.
import * as THREE from "three";

const { lanas, pilares } = JSON.parse(document.getElementById("datos-pilares").textContent);
const quieto = matchMedia("(prefers-reduced-motion: reduce)").matches;

// El SVG del pilar mide 100 x 1400; en 3D, 100 de ancho = diámetro 2 (radio 1).
const RADIO = 1;
const SVG_A_MUNDO = 0.02;
const PX_POR_UNIDAD = 82;                         // resolución de la textura
const TEX_ANCHO = 512;                            // ≈ 2πR × 82, una vuelta completa
const TEX_ALTO_MAX = 4096;                        // tope de alto de la textura del cuerpo
const RELIEVE = 0.14;                             // cuánto sobresale lo más alto del relieve
const MEDIO_ANCHO_VISTA = 1.3;                    // medio ancho del pilar en pantalla (el cilindro mide 1)
const AIRE = 30;                                  // px extra hacia el contenido, para que no se corten los ovillos

// Aleatorio con semilla: cada pilar sale siempre igual
function azar(semilla) {
  return () => {
    semilla |= 0; semilla = (semilla + 0x6d2b79f5) | 0;
    let t = Math.imul(semilla ^ (semilla >>> 15), 1 | semilla);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ---------- Textura del carrete ----------
// Se pinta para el alto real del cuerpo (entre las tapas), así nada se estira.

const VUELTA = 7;     // grosor en px de cada vuelta de lana

// Trama de tela: líneas finas cruzadas
function trama(g, x, y, w, h, tono, paso = 4) {
  g.fillStyle = tono;
  for (let v = y; v < y + h; v += paso) g.fillRect(x, v, w, 1);
  for (let u = x; u < x + w; u += paso) g.fillRect(u, y, 1, h);
}

// Reparte el alto entre las bandas según su peso: [inicio, alto, lana]
function repartir(bandas, y, h) {
  const total = bandas.reduce((t, [peso]) => t + peso, 0);
  let inicio = y;
  return bandas.map(([peso, lana]) => {
    const alto = (h * peso) / total;
    inicio += alto;
    return [inicio - alto, alto, lana];
  });
}

// Puntada recta alrededor de un rectángulo
function pespunte(g, x, y, w, h, color) {
  g.save();
  g.strokeStyle = color;
  g.lineWidth = 1.6;
  g.setLineDash([6, 5]);
  g.strokeRect(x + 5, y + 5, w - 10, h - 10);
  g.restore();
}

// Un pintor por cada tipo de columna de "carrete" (ver PILARES en main.py)
const pintores = {
  // Vueltas de lana apiladas en bandas; cada vuelta es una hebra torcida
  lana(g, x, y, w, h, bandas, r) {
    for (const [inicio, alto, lana] of repartir(bandas, y, h)) {
      const [color, sombra] = lanas[lana];
      g.fillStyle = color;
      g.fillRect(x, inicio, w, alto);
      for (let v = inicio; v < inicio + alto; v += VUELTA) {
        // Torsión: trazos en diagonal, oscuros y claros, a lo largo de la vuelta
        const corrido = r() * 4;
        for (const [tono, dx, grosor] of [[sombra, 0, 1.6], ["rgba(255, 255, 255, .3)", 1.8, 0.9]]) {
          g.strokeStyle = tono;
          g.lineWidth = grosor;
          g.beginPath();
          for (let u = x - VUELTA + corrido + dx; u < x + w; u += 3.6) {
            g.moveTo(u, v + VUELTA);
            g.lineTo(u + VUELTA * 0.8, v);
          }
          g.stroke();
        }
        // Surco entre vueltas
        g.fillStyle = "rgba(40, 25, 10, .35)";
        g.fillRect(x, v + VUELTA - 1, w, 1);
      }
      // Sombra en los bordes de la banda: se ve redondeada, como un rollo
      const borde = g.createLinearGradient(0, inicio, 0, inicio + alto);
      borde.addColorStop(0, "rgba(40, 25, 10, .45)");
      borde.addColorStop(0.18, "rgba(40, 25, 10, 0)");
      borde.addColorStop(0.45, "rgba(255, 255, 255, .08)");
      borde.addColorStop(0.82, "rgba(40, 25, 10, 0)");
      borde.addColorStop(1, "rgba(40, 25, 10, .5)");
      g.fillStyle = borde;
      g.fillRect(x, inicio, w, alto);
    }
  },

  // Cinta tejida vertical, con bordes y una cadena de rombos
  cinta(g, x, y, w, h, [fondo, borde, rombo]) {
    g.fillStyle = lanas[fondo][0];
    g.fillRect(x, y, w, h);
    trama(g, x, y, w, h, "rgba(90, 60, 30, .10)", 3);
    g.fillStyle = lanas[borde][0];
    for (const [dx, ancho] of [[2, 4], [9, 2], [w - 6, 4], [w - 11, 2]]) g.fillRect(x + dx, y, ancho, h);
    const cx = x + w / 2;
    const mitad = w * 0.3;
    const alto = w * 0.75;
    for (let v = y; v < y + h; v += alto) {
      const cy = v + alto / 2;
      for (const [escala, color] of [[0.95, borde], [0.6, rombo], [0.25, fondo]]) {
        g.beginPath();
        g.moveTo(cx, cy - (alto / 2) * escala);
        g.lineTo(cx + mitad * escala, cy);
        g.lineTo(cx, cy + (alto / 2) * escala);
        g.lineTo(cx - mitad * escala, cy);
        g.closePath();
        g.fillStyle = lanas[color][0];
        g.fill();
      }
    }
  },

  // Franjas verticales tejidas
  rayas(g, x, y, w, h, colores) {
    const ancho = w / colores.length;
    colores.forEach((lana, i) => {
      const [color, sombra] = lanas[lana];
      const u = x + i * ancho;
      g.fillStyle = color;
      g.fillRect(u, y, ancho, h);
      g.fillStyle = sombra;
      for (let v = y; v < y + h; v += 3) g.fillRect(u, v, ancho, 1);
      g.fillStyle = "rgba(255, 255, 255, .25)";
      g.fillRect(u + 1, y, 1.5, h);
    });
  },

  // Tela cosida encima, con su pespunte
  retazo(g, x, y, w, h, lana) {
    const [color, sombra] = lanas[lana];
    g.fillStyle = color;
    g.fillRect(x, y, w, h);
    trama(g, x, y, w, h, "rgba(60, 40, 20, .13)");
    pespunte(g, x, y, w, h, lana === "crudo" ? lanas.rojo[0] : lanas.crudo[0]);
    g.fillStyle = sombra;
    g.fillRect(x, y, 2, h);
  },

  // Retazos pequeños en cuadros, de a dos por fila
  cuadros(g, x, y, w, h, colores) {
    const lado = w / 2;
    let i = 0;
    for (let v = y; v < y + h; v += lado, i++) {
      for (let u = 0; u < 2; u++, i++) {
        const lana = colores[i % colores.length];
        const alto = Math.min(lado, y + h - v);
        g.fillStyle = lanas[lana][0];
        g.fillRect(x + u * lado, v, lado, alto);
        trama(g, x + u * lado, v, lado, alto, "rgba(60, 40, 20, .12)");
        pespunte(g, x + u * lado, v, lado, alto, lana === "crudo" ? lanas.azul[1] : lanas.crudo[0]);
      }
    }
  },

  // Faja tejida que da toda la vuelta: bordes, franjas y zigzag
  faja(g, x, y, w, h, [borde, fondo, dibujo]) {
    g.fillStyle = lanas[fondo][0];
    g.fillRect(x, y, w, h);
    trama(g, x, y, w, h, "rgba(90, 60, 30, .10)", 3);
    g.fillStyle = lanas[borde][0];
    g.fillRect(x, y, w, h * 0.16);
    g.fillRect(x, y + h * 0.84, w, h * 0.16);
    g.fillStyle = lanas[dibujo][0];
    g.fillRect(x, y + h * 0.22, w, h * 0.06);
    g.fillRect(x, y + h * 0.72, w, h * 0.06);
    // El paso divide la vuelta en partes iguales, para que el zigzag cierre sin costura
    const paso = w / Math.round(w / (h * 0.5));
    g.strokeStyle = lanas[borde][1];
    g.lineWidth = h * 0.08;
    g.beginPath();
    for (let i = 0; i * paso <= w; i++) g.lineTo(x + i * paso, y + h * (i % 2 ? 0.38 : 0.62));
    g.stroke();
  },
};

// ---------- Relieve ----------
// Mapa en grises del mismo tamaño que la textura: blanco sobresale, negro queda hundido.
// Lo usa el cilindro para abultarse (desplazamiento) y para su sombreado (bump).

const gris = (n) => `rgb(${n}, ${n}, ${n})`;

// Bulto redondeado de arriba hacia abajo, de `base` en los bordes a `cima` al centro
function bulto(a, x, y, w, h, base, cima) {
  const degradado = a.createLinearGradient(0, y, 0, y + h);
  for (const t of [0, 0.1, 0.25, 0.5, 0.75, 0.9, 1]) {
    degradado.addColorStop(t, gris(Math.round(base + (cima - base) * Math.sin(t * Math.PI))));
  }
  a.fillStyle = degradado;
  a.fillRect(x, y, w, h);
}

const relieves = {
  lana(a, x, y, w, h, bandas) {
    for (const [inicio, alto] of repartir(bandas, y, h)) {
      bulto(a, x, inicio, w, alto, 90, 255);
      // Surcos entre vueltas, para que el bump marque cada hebra
      a.fillStyle = "rgba(0, 0, 0, .18)";
      for (let v = inicio; v < inicio + alto; v += VUELTA) a.fillRect(x, v + VUELTA - 1.5, w, 1.5);
    }
  },
  cinta(a, x, y, w, h) { a.fillStyle = gris(70); a.fillRect(x, y, w, h); },
  rayas(a, x, y, w, h) { a.fillStyle = gris(55); a.fillRect(x, y, w, h); },
  retazo(a, x, y, w, h) {
    a.fillStyle = gris(85); a.fillRect(x, y, w, h);
    a.fillStyle = gris(60); a.fillRect(x, y, 3, h);
  },
  cuadros(a, x, y, w, h) { a.fillStyle = gris(80); a.fillRect(x, y, w, h); },
  faja(a, x, y, w, h) { bulto(a, x, y, w, h, 110, 190); },
};

// Cordón torcido junto a cada tapa
function cordon(g, y, alto) {
  g.fillStyle = lanas.crudo[1];
  g.fillRect(0, y, TEX_ANCHO, alto);
  g.strokeStyle = lanas.crudo[0];
  g.lineWidth = alto * 0.35;
  for (let x = 0; x < TEX_ANCHO + alto; x += TEX_ANCHO / 64) {
    g.beginPath();
    g.moveTo(x - alto * 0.7, y + alto);
    g.lineTo(x, y);
    g.stroke();
  }
}

function lienzo2d(alto) {
  const lienzo = document.createElement("canvas");
  lienzo.width = TEX_ANCHO;
  lienzo.height = alto;
  return lienzo.getContext("2d");
}

// Devuelve dos texturas del mismo tamaño: el color y el relieve
function texturaCarrete(tramos, lado, altoPx) {
  const g = lienzo2d(altoPx);
  const a = lienzo2d(altoPx);
  const r = azar(lado === "izq" ? 7 : 13);

  const borde = 12;   // alto de cada cordón
  const util = altoPx - borde * 2;
  const total = tramos.reduce((t, [peso]) => t + peso, 0);
  let y = borde;
  for (const [peso, columnas] of tramos) {
    const alto = (util * peso) / total;
    let x = 0;
    for (const [parte, tipo, colores] of columnas) {
      const ancho = TEX_ANCHO * parte;
      for (const [c, pintar] of [[g, pintores[tipo]], [a, relieves[tipo]]]) {
        c.save();
        c.beginPath();
        c.rect(x, y, ancho, alto);
        c.clip();
        pintar(c, x, y, ancho, alto, colores, r);
        c.restore();
      }
      // Sombra entre columnas, para que se vean como piezas distintas
      const sombra = g.createLinearGradient(x + ancho - 8, 0, x + ancho, 0);
      sombra.addColorStop(0, "rgba(40, 25, 10, 0)");
      sombra.addColorStop(1, "rgba(40, 25, 10, .4)");
      g.fillStyle = sombra;
      g.fillRect(x + ancho - 8, y, 8, alto);
      x += ancho;
    }
    g.fillStyle = "rgba(40, 25, 10, .4)";
    g.fillRect(0, y + alto - 2, TEX_ANCHO, 2);
    y += alto;
  }
  for (const y0 of [0, altoPx - borde]) {
    cordon(g, y0, borde);
    bulto(a, 0, y0, TEX_ANCHO, borde, 80, 200);
  }

  return [g, a].map((c, i) => {
    const textura = new THREE.CanvasTexture(c.canvas);
    if (i === 0) textura.colorSpace = THREE.SRGBColorSpace;
    textura.wrapS = THREE.RepeatWrapping;
    return textura;
  });
}

// ---------- Tapas de madera ----------

const TAPA_ALTO = 0.5;
const TAPA_RADIO = 1.27;

function texturaMadera() {
  const lienzo = document.createElement("canvas");
  lienzo.width = 256;
  lienzo.height = 64;
  const g = lienzo.getContext("2d");
  const r = azar(5);
  g.fillStyle = "#c99b63";
  g.fillRect(0, 0, 256, 64);
  for (let i = 0; i < 40; i++) {
    g.strokeStyle = `rgba(120, 80, 40, ${0.08 + r() * 0.18})`;
    g.lineWidth = 0.5 + r() * 1.5;
    const y = r() * 64;
    g.beginPath();
    g.moveTo(0, y);
    for (let x = 0; x <= 256; x += 16) g.lineTo(x, y + Math.sin(x * 0.03 + i) * 2);
    g.stroke();
  }
  const textura = new THREE.CanvasTexture(lienzo);
  textura.colorSpace = THREE.SRGBColorSpace;
  textura.wrapS = THREE.RepeatWrapping;
  return textura;
}

// Disco con el borde redondeado, girado alrededor del eje del pilar
function crearTapa(material) {
  const m = TAPA_ALTO / 2;
  const perfil = [
    [0, -m], [TAPA_RADIO - 0.12, -m], [TAPA_RADIO - 0.04, -m + 0.04], [TAPA_RADIO, -m + 0.12],
    [TAPA_RADIO, m - 0.12], [TAPA_RADIO - 0.04, m - 0.04], [TAPA_RADIO - 0.12, m], [0, m],
  ].map(([x, y]) => new THREE.Vector2(x, y));
  return new THREE.Mesh(new THREE.LatheGeometry(perfil, 64), material);
}

function texturaOvillo(lana) {
  const [color, sombra] = lanas[lana];
  const lienzo = document.createElement("canvas");
  lienzo.width = 256;
  lienzo.height = 128;
  const g = lienzo.getContext("2d");
  g.fillStyle = color;
  g.fillRect(0, 0, 256, 128);
  // Tres grupos de vueltas onduladas que se cruzan, como un ovillo enrollado
  for (const [fase, alto, tono] of [[0, 18, sombra], [2.1, 26, "rgba(255,255,255,.35)"], [4.2, 14, sombra]]) {
    g.strokeStyle = tono;
    g.lineWidth = 1.6;
    for (let k = -2; k < 18; k++) {
      g.beginPath();
      for (let x = 0; x <= 256; x += 4) {
        const y = k * 8 + Math.sin((x / 256) * Math.PI * 2 + fase) * alto;
        x === 0 ? g.moveTo(x, y) : g.lineTo(x, y);
      }
      g.stroke();
    }
  }
  const textura = new THREE.CanvasTexture(lienzo);
  textura.colorSpace = THREE.SRGBColorSpace;
  textura.wrapS = THREE.RepeatWrapping;
  return textura;
}

// Hebra que cuelga desde la superficie del pilar; se mece desde su punto de amarre
function hebraColgante(angulo, y, largo, lana, r) {
  const pivote = new THREE.Object3D();
  pivote.position.set(Math.sin(angulo) * RADIO, y, Math.cos(angulo) * RADIO);
  pivote.rotation.y = angulo;
  const puntos = [];
  for (let i = 0; i <= 6; i++) {
    const t = i / 6;
    puntos.push(new THREE.Vector3(Math.sin(t * 5 + r() * 2) * 0.06, -t * largo, 0.04 + Math.sin(t * Math.PI) * 0.12));
  }
  const material = new THREE.MeshStandardMaterial({ color: lanas[lana][0], roughness: 0.9 });
  const tubo = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(puntos), 48, 0.035, 8), material);
  const nudo = new THREE.Mesh(new THREE.SphereGeometry(0.07, 12, 10), material);
  nudo.position.copy(puntos[puntos.length - 1]);
  pivote.add(tubo, nudo);
  pivote.userData.fase = r() * Math.PI * 2;
  return pivote;
}

function crearPilar(contenedor) {
  const lado = contenedor.dataset.lado;
  const datos = pilares[lado];
  const r = azar(lado === "izq" ? 21 : 34);

  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.domElement.classList.add(`pilar__lienzo--${lado}`);
  contenedor.appendChild(renderer.domElement);

  const escena = new THREE.Scene();
  escena.add(new THREE.HemisphereLight(0xfff4e2, 0x6b4d30, 0.9));
  const sol = new THREE.DirectionalLight(0xfff0d8, 3.4);
  sol.position.set(-6, 3, 4);
  escena.add(sol);
  const contraluz = new THREE.DirectionalLight(0xffe2c0, 0.8);
  contraluz.position.set(4, 1, -3);
  escena.add(contraluz);

  const camara = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 50);
  camara.position.z = 10;

  const giro = new THREE.Group();
  escena.add(giro);

  // Cuerpo del carrete; la textura se pinta en ajustar(), según el alto de la ventana
  // El relieve abulta las bandas de lana hasta RELIEVE por encima del radio base
  const tela = new THREE.MeshStandardMaterial({ bumpScale: 3, roughness: 0.88, displacementScale: RELIEVE });
  const cilindro = new THREE.Mesh(new THREE.BufferGeometry(), tela);
  giro.add(cilindro);

  const maderaTapa = new THREE.MeshStandardMaterial({ map: texturaMadera(), roughness: 0.6 });
  const tapaArriba = crearTapa(maderaTapa);
  const tapaAbajo = crearTapa(maderaTapa);
  giro.add(tapaArriba, tapaAbajo);

  // Ovillos pegados a la superficie, en ángulos distintos
  const ovillos = datos.ovillos.map(([y, lana], i) => {
    const bola = new THREE.Mesh(
      new THREE.SphereGeometry(0.4, 32, 24),
      new THREE.MeshStandardMaterial({ map: texturaOvillo(lana), roughness: 0.95 }),
    );
    const angulo = (i % 2 ? -0.7 : 0.6) * (lado === "izq" ? 1 : -1);
    bola.position.set(Math.sin(angulo) * (RADIO + 0.28), 0, Math.cos(angulo) * (RADIO + 0.28));
    bola.rotation.set(r() * 3, r() * 3, r() * 3);
    bola.userData.ySvg = y;
    giro.add(bola);
    return bola;
  });

  // Hebras que cuelgan bajo las últimas vueltas
  const colgantes = datos.bandas.slice(-3, -1).map(([y0, n, sep, lana], i) => {
    const hebra = hebraColgante((i ? -0.5 : 0.35) * (lado === "izq" ? 1 : -1), 0, 2 + r() * 1.5, lana, r);
    hebra.userData.ySvg = y0 + n * sep;
    giro.add(hebra);
    return hebra;
  });

  function ajustar() {
    const { clientWidth: ancho, clientHeight: alto } = contenedor;
    if (!ancho || !alto) return;
    // El lienzo es más ancho que el pilar por el lado del contenido; la cámara lo compensa
    renderer.setSize(ancho + AIRE, alto, false);
    const unidadesPorPx = (MEDIO_ANCHO_VISTA * 2) / ancho;
    const extra = AIRE * unidadesPorPx;
    const medioAlto = MEDIO_ANCHO_VISTA * (alto / ancho);
    Object.assign(camara, {
      left: -MEDIO_ANCHO_VISTA - (lado === "der" ? extra : 0),
      right: MEDIO_ANCHO_VISTA + (lado === "izq" ? extra : 0),
      top: medioAlto,
      bottom: -medioAlto,
    });
    camara.updateProjectionMatrix();

    // Una tapa arriba y otra abajo de la ventana; el cuerpo llena el espacio entre ellas
    const margen = 0.05;
    tapaArriba.position.y = medioAlto - margen - TAPA_ALTO / 2;
    tapaAbajo.position.y = -tapaArriba.position.y;
    const largo = medioAlto * 2 - (margen + TAPA_ALTO) * 2;
    cilindro.geometry.dispose();
    const altoPx = Math.min(TEX_ALTO_MAX, Math.round(largo * PX_POR_UNIDAD));
    // Muchos segmentos a lo alto, para que el desplazamiento dibuje cada banda
    const base = RADIO - RELIEVE * 0.45;
    cilindro.geometry = new THREE.CylinderGeometry(base, base, largo, 128, Math.ceil(altoPx / 3), true);

    // La textura se vuelve a pintar solo si cambió el alto
    if (tela.map?.image.height !== altoPx) {
      tela.map?.dispose();
      tela.bumpMap?.dispose();
      const [color, relieve] = texturaCarrete(datos.carrete, lado, altoPx);
      color.anisotropy = renderer.capabilities.getMaxAnisotropy();
      tela.map = color;
      tela.bumpMap = tela.displacementMap = relieve;
      tela.needsUpdate = true;
    }

    for (const objeto of [...ovillos, ...colgantes]) {
      objeto.position.y = medioAlto - objeto.userData.ySvg * SVG_A_MUNDO;
    }
  }
  new ResizeObserver(ajustar).observe(contenedor);
  ajustar();

  contenedor.classList.add("pilar--3d");
  const sentido = lado === "izq" ? 1 : -1;

  return (segundos) => {
    if (!quieto) {
      giro.rotation.y = sentido * (segundos * 0.06 + scrollY * 0.0025);
      for (const hebra of colgantes) {
        hebra.rotation.z = Math.sin(segundos * 1.3 + hebra.userData.fase) * 0.08;
        hebra.rotation.x = Math.sin(segundos * 0.9 + hebra.userData.fase) * 0.05;
      }
    }
    renderer.render(escena, camara);
  };
}

try {
  const dibujos = [...document.querySelectorAll(".pilar")].map(crearPilar);
  const reloj = new THREE.Clock();
  const cuadro = () => {
    const segundos = reloj.getElapsedTime();
    for (const dibujar of dibujos) dibujar(segundos);
    if (!quieto) requestAnimationFrame(cuadro);
  };
  cuadro();
  // Sin animación igual se redibuja al cambiar el tamaño
  if (quieto) addEventListener("resize", () => requestAnimationFrame(cuadro));
} catch (error) {
  // Sin WebGL: se queda el SVG
  console.warn("Pilares 3D no disponibles:", error);
  document.querySelectorAll(".pilar--3d").forEach((p) => p.classList.remove("pilar--3d"));
  document.querySelectorAll(".pilar canvas").forEach((c) => c.remove());
}
