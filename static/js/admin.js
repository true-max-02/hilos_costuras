// Panel: muestra en la cortina de prueba las fotos elegidas, antes de subirlas.
for (const entrada of document.querySelectorAll("[data-vista]")) {
  const campo = entrada.dataset.vista;
  const img = document.querySelector(`[data-img="${campo}"]`);
  const archivo = document.querySelector(`[data-archivo="${campo}"]`);
  const original = img.getAttribute("src");
  const textoOriginal = archivo.textContent;
  let url;

  entrada.addEventListener("change", () => {
    if (url) URL.revokeObjectURL(url);
    const elegido = entrada.files[0];
    if (elegido) {
      url = URL.createObjectURL(elegido);
      img.src = url;
      archivo.textContent = elegido.name;
    } else {
      url = null;
      if (original) img.src = original; else img.removeAttribute("src");
      archivo.textContent = textoOriginal;
    }
  });
}

// Borrar pide confirmación
for (const formulario of document.querySelectorAll("[data-confirmar]")) {
  formulario.addEventListener("submit", (evento) => {
    if (!confirm(formulario.dataset.confirmar)) evento.preventDefault();
  });
}

// Mientras se suben las fotos, el botón avisa y no se puede apretar dos veces
for (const formulario of document.querySelectorAll("form[enctype='multipart/form-data']")) {
  formulario.addEventListener("submit", () => {
    const boton = formulario.querySelector("button[type='submit']");
    boton.disabled = true;
    boton.textContent = "Subiendo…";
  });
}
