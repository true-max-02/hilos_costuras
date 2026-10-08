// Pilares 3D: cilindros de madera envueltos en lana, con ovillos y hebras colgando.
// Giran apenas solos y un poco más al bajar por la página.
// Si WebGL falla, queda el SVG de respaldo que ya está en la página.
import * as THREE from "three";

const { lanas, pilares } = JSON.parse(document.getElementById("datos-pilares").textContent);
const quieto = matchMedia("(prefers-reduced-motion: reduce)").matches;

// El SVG del pilar mide 100 x 1400; en 3D, 100 de ancho = diámetro 2 (radio 1).
const RADIO = 1;
const SVG_A_MUNDO = 0.02;
const PX_POR_UNIDAD = 82;                         // resolución de la textura
const SVG_A_PX = SVG_A_MUNDO * PX_POR_UNIDAD;
const TEX_ANCHO = 512;                            // ≈ 2πR × 82, una vuelta completa
const TEX_ALTO = 2304;
const ALTO_TEXTURA = TEX_ALTO / PX_POR_UNIDAD;    // unidades de mundo que cubre la textura
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

// Dibuja una línea en la textura repitiéndola a ambos lados, para que cierre la vuelta sin costura
function lineaEnVuelta(g, x1, y1, x2, y2) {
  for (const dx of [-TEX_ANCHO, 0, TEX_ANCHO]) {
    g.beginPath();
    g.moveTo(x1 + dx, y1);
    g.lineTo(x2 + dx, y2);
    g.stroke();
  }
}

function texturaPilar(datos, lado) {
  const lienzo = document.createElement("canvas");
  lienzo.width = TEX_ANCHO;
  lienzo.height = TEX_ALTO;
  const g = lienzo.getContext("2d");
  const r = azar(lado === "izq" ? 7 : 13);

  // Madera con veta vertical
  g.fillStyle = "#e0c393";
  g.fillRect(0, 0, TEX_ANCHO, TEX_ALTO);
  for (let i = 0; i < 70; i++) {
    const x = r() * TEX_ANCHO;
    g.strokeStyle = `rgba(150, 110, 62, ${0.06 + r() * 0.12})`;
    g.lineWidth = 0.6 + r() * 1.8;
    g.beginPath();
    g.moveTo(x, 0);
    for (let y = 0; y <= TEX_ALTO; y += 160) g.lineTo(x + Math.sin(y * 0.004 + i) * 4, y);
    g.stroke();
  }

  // Vueltas de lana: anillos rectos, para que los bordes de cada banda queden parejos
  g.lineCap = "round";
  for (const [y0, n, sep, lana] of datos.bandas) {
    const [color, sombra] = lanas[lana];
    const paso = sep * SVG_A_PX;
    for (let i = 0; i < n; i++) {
      const y = (y0 + i * sep) * SVG_A_PX;
      g.fillStyle = sombra;
      g.fillRect(0, y - paso * 0.52, TEX_ANCHO, paso * 1.04);
      g.fillStyle = i % 3 === 0 ? sombra : color;
      g.fillRect(0, y - paso * 0.36, TEX_ANCHO, paso * 0.72);
      g.fillStyle = "rgba(255, 255, 255, .22)";
      g.fillRect(0, y - paso * 0.25, TEX_ANCHO, paso * 0.2);
      // Fibras más oscuras sueltas: al girar el pilar se ve que dan la vuelta
      g.fillStyle = sombra;
      for (let k = 0; k < 5; k++) g.fillRect(r() * TEX_ANCHO, y - paso * 0.3, 10 + r() * 40, paso * 0.4);
    }
  }

  // Hebras sueltas en diagonal: al girar el pilar se nota que dan la vuelta
  const nombres = Object.keys(lanas);
  const fin = Math.max(...datos.bandas.map(([y0, n, sep]) => y0 + n * sep)) * SVG_A_PX;
  for (let i = 0; i < 7; i++) {
    const [color, sombra] = lanas[nombres[Math.floor(r() * nombres.length)]];
    const x = r() * TEX_ANCHO;
    const y = 60 + r() * (fin - 300);
    const caida = (180 + r() * 160) * (r() < 0.5 ? 1 : -1);
    g.strokeStyle = sombra; g.lineWidth = 4;
    lineaEnVuelta(g, x, y, x + TEX_ANCHO * 0.5, y + Math.abs(caida));
    g.strokeStyle = color; g.lineWidth = 2.6;
    lineaEnVuelta(g, x, y, x + TEX_ANCHO * 0.5, y + Math.abs(caida));
  }

  const textura = new THREE.CanvasTexture(lienzo);
  textura.colorSpace = THREE.SRGBColorSpace;
  textura.wrapS = THREE.RepeatWrapping;
  textura.wrapT = THREE.ClampToEdgeWrapping;   // abajo se estira la madera lisa
  return textura;
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

  const textura = texturaPilar(datos, lado);
  textura.anisotropy = renderer.capabilities.getMaxAnisotropy();
  const madera = new THREE.MeshStandardMaterial({
    map: textura, bumpMap: textura, bumpScale: 2.5, roughness: 0.85,
  });
  const cilindro = new THREE.Mesh(new THREE.BufferGeometry(), madera);
  giro.add(cilindro);

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

    // El cilindro llena todo el alto de la ventana; la textura se apoya arriba
    const largo = Math.max(ALTO_TEXTURA, medioAlto * 2 + 0.5);
    cilindro.geometry.dispose();
    cilindro.geometry = new THREE.CylinderGeometry(RADIO, RADIO, largo, 96, 1, true);
    cilindro.position.y = medioAlto - largo / 2;
    textura.repeat.y = largo / ALTO_TEXTURA;
    textura.offset.y = 1 - textura.repeat.y;

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
