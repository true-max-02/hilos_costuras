# Hilos & Arreglos

Página web de un taller que hace ropa de diseño propia y arreglos de ropa.
Cada prenda se diseña y se cose en el local, y también se hacen ajustes,
bastas, cierres y reparaciones.

## Qué tiene

- **Inicio** (`/`): presentación del taller con su identidad visual. A cada
  lado hay un pilar de madera envuelto en lanas de colores, hecho en 3D con
  Three.js. Entre los dos pilares cruza una tabla con el letrero
  "Arreglos de ropa".
- **Arreglos** (`/arreglos`): galería de antes y después con una cortina
  deslizable que se puede mover con el mouse, con el dedo o con el teclado.
  Más abajo está la sección para agendar.
- En celular, o si el navegador no tiene WebGL, los pilares se muestran como
  SVG y se adelgazan hasta quedar como un borde.
- Las animaciones respetan la opción "reducir movimiento" del sistema.

Más adelante se agregarán el catálogo, el carrito y el panel de administración.

## Tecnologías

- Python + Flask
- SQLite (la base `tienda.db` se crea sola al iniciar)
- Plantillas Jinja2, más CSS y JavaScript sin frameworks
- Three.js r169, incluido en `static/vendor/` en lugar de cargarse desde un CDN

## Cómo ejecutarlo

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python main.py
```

Luego abre <http://127.0.0.1:5000>.

### Variables de entorno

| Variable      | Para qué sirve                                                        |
|---------------|-----------------------------------------------------------------------|
| `SECRET_KEY`  | Clave de Flask. Si falta, se genera una temporal (solo para desarrollo). |
| `FLASK_DEBUG` | Con el valor `1` activa el modo depuración.                           |

## Estructura

```
main.py                 rutas, base de datos y colores de las lanas
templates/
  base.html             marco común de todas las páginas
  _pilares.html         pilares, tabla y letrero en SVG (respaldo)
  inicio.html
  arreglos.html
static/
  css/estilos.css
  js/pilares3d.js       pilares 3D
  js/cortina.js         cortina de antes y después
  demo/                 ilustraciones de muestra de la galería
  vendor/               Three.js
```

Las imágenes de `static/demo/` son ilustraciones de muestra. Se reemplazarán
por fotos reales del taller.
