// Cortina de antes y después: al correrla hacia la derecha se ve la prenda arreglada.
// Funciona con mouse, dedo y teclado (flechas, Inicio, Fin).
const sinMovimiento = matchMedia("(prefers-reduced-motion: reduce)").matches;

for (const cortina of document.querySelectorAll("[data-cortina]")) {
  const tela = cortina.querySelector(".cortina__tela");
  let abierto = 12;          // % desde la izquierda donde cuelga la cortina
  let arrastrando = false;
  let ultimoX = 0;
  let ultimoT = 0;
  let calma;

  const poner = (valor) => {
    abierto = Math.min(100, Math.max(0, valor));
    cortina.style.setProperty("--abierto", `${abierto}%`);
    tela.setAttribute("aria-valuenow", Math.round(abierto));
    // Cada etiqueta aparece solo cuando su lado tiene espacio
    cortina.classList.toggle("cortina--ver-despues", abierto > 24);
    cortina.classList.toggle("cortina--ver-antes", abierto < 76);
  };

  const desdePuntero = (evento) => {
    const caja = cortina.getBoundingClientRect();
    poner(((evento.clientX - caja.left) / caja.width) * 100);
  };

  // La tela se inclina según qué tan rápido se tira, y vuelve a caer al soltarla
  const tirar = (evento) => {
    if (sinMovimiento) return;
    const ahora = performance.now();
    const velocidad = (evento.clientX - ultimoX) / Math.max(ahora - ultimoT, 1);
    ultimoX = evento.clientX;
    ultimoT = ahora;
    cortina.style.setProperty("--tiron", Math.max(-1, Math.min(1, velocidad * 0.6)).toFixed(2));
    clearTimeout(calma);
    calma = setTimeout(() => cortina.style.setProperty("--tiron", 0), 90);
  };

  const terminar = () => {
    arrastrando = false;
    cortina.classList.remove("cortina--moviendo");
    cortina.style.setProperty("--tiron", 0);
  };

  cortina.addEventListener("pointerdown", (evento) => {
    arrastrando = true;
    cortina.setPointerCapture(evento.pointerId);
    cortina.classList.add("cortina--moviendo");
    ultimoX = evento.clientX;
    ultimoT = performance.now();
    desdePuntero(evento);
    tela.focus({ preventScroll: true });
  });
  cortina.addEventListener("pointermove", (evento) => {
    if (!arrastrando) return;
    desdePuntero(evento);
    tirar(evento);
  });
  cortina.addEventListener("pointerup", terminar);
  cortina.addEventListener("pointercancel", terminar);

  tela.addEventListener("keydown", (evento) => {
    const pasos = { ArrowRight: 5, ArrowUp: 5, ArrowLeft: -5, ArrowDown: -5, PageUp: 20, PageDown: -20 };
    if (evento.key in pasos) poner(abierto + pasos[evento.key]);
    else if (evento.key === "Home") poner(0);
    else if (evento.key === "End") poner(100);
    else return;
    evento.preventDefault();
  });

  poner(abierto);
}
