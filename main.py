import hmac
import os
import secrets
import sqlite3
import time
import warnings
from contextlib import closing
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from PIL import Image, ImageOps

app = Flask(__name__)

# La clave se lee del entorno. Si falta, se genera una temporal (solo sirve para desarrollo).
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Dos fotos de celular por formulario, con margen
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

# Acceso al panel. Para la demo queda admin / admin; en producción se define en el entorno.
ADMIN_USUARIO = os.environ.get("ADMIN_USUARIO", "admin")
ADMIN_CLAVE = os.environ.get("ADMIN_CLAVE", "admin")

BD = os.path.join(app.root_path, "tienda.db")

# Fotos subidas desde el panel (carpeta fuera de git)
SUBIDAS = "uploads/trabajos"          # dentro de static/
CARPETA_SUBIDAS = os.path.join(app.static_folder, *SUBIDAS.split("/"))
FORMATOS_FOTO = {"JPEG", "PNG", "WEBP"}
TAMANO_FOTO = (1200, 1500)            # 4:5, igual que la cortina
Image.MAX_IMAGE_PIXELS = 50_000_000   # frena imágenes gigantes hechas para colgar el servidor

ESQUEMA = """
CREATE TABLE IF NOT EXISTS trabajos (
    id INTEGER PRIMARY KEY,
    titulo TEXT NOT NULL,
    detalle TEXT NOT NULL DEFAULT '',
    foto_antes TEXT NOT NULL,      -- ruta dentro de static/
    foto_despues TEXT NOT NULL,
    orden INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS prendas (
    id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,      -- para la dirección de la ficha
    descripcion TEXT NOT NULL DEFAULT '',
    precio INTEGER NOT NULL CHECK (precio >= 0),   -- pesos chilenos
    foto TEXT NOT NULL,             -- ruta dentro de static/
    tallas TEXT NOT NULL DEFAULT '',   -- separadas por coma: "S,M,L"
    stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    visible INTEGER NOT NULL DEFAULT 1,
    orden INTEGER NOT NULL DEFAULT 0   -- la primera es la destacada
);
"""

# Trabajos de muestra para la demo; se cambian por fotos reales desde el panel
TRABAJOS_DEMO = [
    ("Basta de pantalón", "Acortamos 14 cm y rehicimos la basta con costura a tono.",
     "demo/pantalon-antes.svg", "demo/pantalon-despues.svg"),
    ("Cambio de cierre", "Cierre nuevo de metal, cosido en la misma línea del original.",
     "demo/cierre-antes.svg", "demo/cierre-despues.svg"),
    ("Rodilla rota", "Parche por dentro y puntadas visibles estilo sashiko.",
     "demo/rodilla-antes.svg", "demo/rodilla-despues.svg"),
    ("Ajuste de camisa", "Entallamos el cuerpo con pinzas y acortamos las mangas.",
     "demo/camisa-antes.svg", "demo/camisa-despues.svg"),
]

# Prendas de muestra (fotos provisorias hechas con IA); se cambian desde el panel
PRENDAS_DEMO = [
    ("Chaqueta de retazos", "chaqueta-de-retazos",
     "Mezclilla con parches de otras telas, cosidos a la vista con hilo crudo.",
     54990, "demo/coleccion/chaqueta-retazos.webp", "S,M,L", 3),
    ("Chaleco tejido", "chaleco-tejido",
     "Tejido a mano en lana cruda, con ribetes azules y botones de madera.",
     39990, "demo/coleccion/chaleco-tejido.webp", "S,M,L", 4),
    ("Falda terracota", "falda-terracota",
     "Lino lavado, corte en A y largo midi, con bolsillos a los lados.",
     34990, "demo/coleccion/falda-terracota.webp", "XS,S,M,L", 5),
]


def preparar_bd():
    with closing(sqlite3.connect(BD)) as conexion, conexion:
        conexion.executescript(ESQUEMA)
        if not conexion.execute("SELECT 1 FROM trabajos LIMIT 1").fetchone():
            conexion.executemany(
                "INSERT INTO trabajos (titulo, detalle, foto_antes, foto_despues, orden) VALUES (?, ?, ?, ?, ?)",
                [(*trabajo, orden) for orden, trabajo in enumerate(TRABAJOS_DEMO)],
            )
        if not conexion.execute("SELECT 1 FROM prendas LIMIT 1").fetchone():
            conexion.executemany(
                "INSERT INTO prendas (nombre, slug, descripcion, precio, foto, tallas, stock, orden)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(*prenda, orden) for orden, prenda in enumerate(PRENDAS_DEMO)],
            )


def bd():
    if "bd" not in g:
        g.bd = sqlite3.connect(BD)
        g.bd.row_factory = sqlite3.Row
    return g.bd


@app.teardown_appcontext
def cerrar_bd(_error):
    conexion = g.pop("bd", None)
    if conexion is not None:
        conexion.close()


preparar_bd()

# Colores de lana: (color principal, sombra)
LANAS = {
    "crudo": ("#efe6d2", "#d8cbb0"),
    "azul": ("#3d6aa3", "#2b5186"),
    "mostaza": ("#d6a53c", "#b8892b"),
    "rojo": ("#b2452f", "#8e3423"),
    "cafe": ("#8a5a36", "#6b4428"),
}

# Vueltas de lana de cada pilar: (y inicial, vueltas, separación, lana).
# Las medidas usan el SVG del pilar (100 de ancho por 1400 de alto).
# Las usan el SVG de respaldo (_pilares.html) y el 3D (static/js/pilares3d.js).
# "carrete" es el diseño del pilar 3D como carrete de hilo, de arriba hacia abajo:
# tramos (peso del alto, columnas); cada columna es (parte de la vuelta, tipo, colores).
# Tipos: lana (vueltas de lana: [(peso, lana)]), cinta (cinta tejida con rombos),
# rayas (franjas verticales), retazo (tela cosida), cuadros (retazos en cuadros)
# y faja (cinta que da toda la vuelta).
PILARES = {
    "izq": {
        "inclinacion": 9,
        "bandas": [
            (4, 16, 3.4, "crudo"), (70, 22, 3.2, "azul"), (152, 10, 3.2, "crudo"),
            (196, 26, 3.2, "mostaza"), (290, 8, 3.2, "rojo"), (330, 18, 3.2, "azul"),
            (400, 12, 3.4, "crudo"), (452, 20, 3.2, "rojo"), (530, 14, 3.2, "mostaza"),
            (590, 10, 3.2, "azul"), (660, 6, 3.4, "crudo"),
        ],
        "ovillos": [(304, "mostaza"), (560, "azul")],
        "carrete": [
            (3, [(1, "lana", [(1, "crudo")])]),
            (40, [
                (0.42, "lana", [(1, "azul"), (1.1, "rojo"), (1, "mostaza"), (0.9, "crudo")]),
                (0.2, "cinta", ["crudo", "azul", "rojo"]),
                (0.14, "retazo", "rojo"),
                (0.24, "rayas", ["crudo", "mostaza", "azul", "crudo"]),
            ]),
            (7, [(1, "faja", ["rojo", "crudo", "azul"])]),
            (47, [
                (0.42, "lana", [(1, "mostaza"), (1, "crudo"), (0.7, "mostaza"), (1.2, "cafe")]),
                (0.24, "rayas", ["azul", "crudo", "mostaza", "rojo"]),
                (0.34, "retazo", "crudo"),
            ]),
            (3, [(1, "lana", [(1, "crudo")])]),
        ],
    },
    "der": {
        "inclinacion": -9,
        "bandas": [
            (4, 16, 3.4, "crudo"), (66, 20, 3.2, "mostaza"), (138, 14, 3.2, "crudo"),
            (190, 18, 3.2, "azul"), (254, 22, 3.2, "rojo"), (334, 10, 3.4, "crudo"),
            (374, 24, 3.2, "azul"), (456, 16, 3.2, "mostaza"), (516, 8, 3.2, "rojo"),
            (552, 18, 3.2, "crudo"), (624, 12, 3.2, "azul"),
        ],
        "ovillos": [(230, "azul"), (480, "rojo")],
        "carrete": [
            (3, [(1, "lana", [(1, "crudo")])]),
            (24, [
                (0.45, "lana", [(1, "azul"), (1, "rojo"), (1, "mostaza"), (0.7, "crudo")]),
                (0.17, "rayas", ["crudo", "azul", "mostaza"]),
                (0.38, "lana", [(1.2, "rojo"), (1, "mostaza"), (0.8, "azul")]),
            ]),
            (20, [
                (0.22, "retazo", "crudo"),
                (0.3, "rayas", ["rojo", "mostaza", "azul", "crudo", "rojo"]),
                (0.24, "retazo", "mostaza"),
                (0.24, "cuadros", ["rojo", "azul", "mostaza", "crudo"]),
            ]),
            (6, [(1, "faja", ["azul", "crudo", "rojo"])]),
            (12, [(0.5, "retazo", "cafe"), (0.5, "cinta", ["crudo", "rojo", "azul"])]),
            (32, [
                (0.3, "rayas", ["mostaza", "azul", "rojo", "crudo"]),
                (0.32, "lana", [(1, "rojo"), (1, "mostaza"), (1, "rojo")]),
                (0.38, "rayas", ["azul", "crudo", "rojo", "mostaza", "azul"]),
            ]),
            (3, [(1, "lana", [(1, "rojo")])]),
        ],
    },
}


@app.context_processor
def datos_de_marca():
    return {"lanas": LANAS, "pilares": PILARES}


@app.template_filter("pesos")
def pesos(valor):
    """34990 -> $34.990"""
    return "$" + f"{valor:,}".replace(",", ".")


@app.route("/")
def inicio():
    return render_template("inicio.html")


@app.route("/arreglos")
def arreglos():
    trabajos = bd().execute("SELECT * FROM trabajos ORDER BY orden, id").fetchall()
    return render_template("arreglos.html", trabajos=trabajos)


# ---------- Panel de administración ----------

def token_csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


app.jinja_env.globals["token_csrf"] = token_csrf


@app.before_request
def revisar_csrf():
    # Todo formulario que cambia algo debe traer el token de la sesión
    if request.method == "POST":
        if (request.content_length or 0) > app.config["MAX_CONTENT_LENGTH"]:
            abort(413)
        enviado = request.form.get("csrf", "")
        if not hmac.compare_digest(enviado, session.get("csrf", "")):
            # Pasa si la sesión venció o se reinició el servidor: se vuelve a intentar
            flash("La sesión venció. Vuelve a intentarlo.")
            return redirect(url_for("panel") if session.get("admin") else url_for("entrar"))


def solo_admin(vista):
    @wraps(vista)
    def envuelta(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("entrar", siguiente=request.path))
        return vista(*args, **kwargs)
    return envuelta


@app.route("/admin/entrar", methods=["GET", "POST"])
def entrar():
    if request.method == "POST":
        usuario = request.form.get("usuario", "")
        clave = request.form.get("clave", "")
        # Se comparan los dos siempre, para no revelar cuál de los dos falló
        bien_usuario = hmac.compare_digest(usuario.encode(), ADMIN_USUARIO.encode())
        bien_clave = hmac.compare_digest(clave.encode(), ADMIN_CLAVE.encode())
        if bien_usuario and bien_clave:
            session.clear()   # sesión nueva al entrar
            session["admin"] = True
            siguiente = request.args.get("siguiente", "")
            # Solo se vuelve a páginas del panel, nunca a otro sitio
            if not siguiente.startswith("/admin"):
                siguiente = url_for("panel")
            return redirect(siguiente)
        time.sleep(1)   # frena a quien intente adivinar la clave
        flash("Usuario o clave incorrectos.")
    return render_template("admin/entrar.html")


@app.route("/admin/salir", methods=["POST"])
def salir():
    session.clear()
    return redirect(url_for("entrar"))


@app.errorhandler(413)
def demasiado_grande(_error):
    flash("Las fotos pesan demasiado: entre las dos deben sumar menos de 25 MB.")
    return redirect(url_for("panel"))


def guardar_foto(archivo):
    """Revisa la foto, la endereza, la recorta a 4:5, le quita los datos ocultos
    (ubicación GPS, modelo del celular...) y la guarda como WebP.
    Devuelve la ruta dentro de static/ o lanza ValueError."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(archivo.stream) as imagen:
                if imagen.format not in FORMATOS_FOTO:
                    raise ValueError("Solo se aceptan fotos JPG, PNG o WebP.")
                imagen = ImageOps.exif_transpose(imagen).convert("RGB")
                imagen = ImageOps.fit(imagen, TAMANO_FOTO, Image.Resampling.LANCZOS)
    except ValueError:
        raise
    except Exception:
        raise ValueError("No se pudo leer una de las fotos. Prueba con un JPG, PNG o WebP.")
    os.makedirs(CARPETA_SUBIDAS, exist_ok=True)
    nombre = secrets.token_hex(12) + ".webp"
    imagen.save(os.path.join(CARPETA_SUBIDAS, nombre), "WEBP", quality=82, method=6)
    return f"{SUBIDAS}/{nombre}"


def borrar_foto(ruta):
    # Solo se borran fotos subidas; las ilustraciones de demo quedan
    if ruta and ruta.startswith(SUBIDAS + "/"):
        try:
            os.remove(os.path.join(app.static_folder, *ruta.split("/")))
        except FileNotFoundError:
            pass
        except OSError as error:
            # En Windows un archivo abierto no se puede borrar; queda suelto pero no se cae nada
            app.logger.warning("No se pudo borrar %s: %s", ruta, error)


def leer_textos():
    titulo = request.form.get("titulo", "").strip()
    detalle = request.form.get("detalle", "").strip()
    if not titulo:
        raise ValueError("Falta el título del trabajo.")
    if len(titulo) > 80 or len(detalle) > 300:
        raise ValueError("El título va hasta 80 letras y el detalle hasta 300.")
    return titulo, detalle


def foto_enviada(campo):
    archivo = request.files.get(campo)
    return archivo if archivo and archivo.filename else None


@app.route("/admin")
@solo_admin
def panel():
    trabajos = bd().execute("SELECT * FROM trabajos ORDER BY orden, id").fetchall()
    return render_template("admin/panel.html", trabajos=trabajos)


@app.route("/admin/trabajos/nuevo", methods=["POST"])
@solo_admin
def trabajo_nuevo():
    nuevas = []
    try:
        titulo, detalle = leer_textos()
        antes, despues = foto_enviada("foto_antes"), foto_enviada("foto_despues")
        if not antes or not despues:
            raise ValueError("Sube las dos fotos: la del antes y la del después.")
        nuevas.append(guardar_foto(antes))
        nuevas.append(guardar_foto(despues))
    except ValueError as error:
        for ruta in nuevas:
            borrar_foto(ruta)
        flash(str(error))
        return render_template("admin/panel.html", trabajos=bd().execute(
            "SELECT * FROM trabajos ORDER BY orden, id").fetchall(),
            borrador={"titulo": request.form.get("titulo", ""),
                      "detalle": request.form.get("detalle", "")}), 400
    conexion = bd()
    # El trabajo nuevo queda primero en la galería
    primero = conexion.execute("SELECT COALESCE(MIN(orden), 0) FROM trabajos").fetchone()[0]
    conexion.execute(
        "INSERT INTO trabajos (titulo, detalle, foto_antes, foto_despues, orden) VALUES (?, ?, ?, ?, ?)",
        (titulo, detalle, nuevas[0], nuevas[1], primero - 1),
    )
    conexion.commit()
    flash(f"Listo: «{titulo}» ya está en la galería de arreglos.")
    return redirect(url_for("panel"))


def trabajo_o_404(id_trabajo):
    trabajo = bd().execute("SELECT * FROM trabajos WHERE id = ?", (id_trabajo,)).fetchone()
    if trabajo is None:
        abort(404)
    return trabajo


@app.route("/admin/trabajos/<int:id_trabajo>", methods=["GET", "POST"])
@solo_admin
def trabajo_editar(id_trabajo):
    trabajo = trabajo_o_404(id_trabajo)
    if request.method == "POST":
        nuevas = {}
        try:
            titulo, detalle = leer_textos()
            for campo in ("foto_antes", "foto_despues"):
                archivo = foto_enviada(campo)
                if archivo:
                    nuevas[campo] = guardar_foto(archivo)
        except ValueError as error:
            for ruta in nuevas.values():
                borrar_foto(ruta)
            flash(str(error))
            return render_template("admin/editar.html", trabajo=trabajo), 400
        conexion = bd()
        conexion.execute(
            "UPDATE trabajos SET titulo = ?, detalle = ?, foto_antes = ?, foto_despues = ? WHERE id = ?",
            (titulo, detalle, nuevas.get("foto_antes", trabajo["foto_antes"]),
             nuevas.get("foto_despues", trabajo["foto_despues"]), id_trabajo),
        )
        conexion.commit()
        # Las fotos reemplazadas ya no se usan
        for campo in nuevas:
            borrar_foto(trabajo[campo])
        flash(f"Guardamos los cambios de «{titulo}».")
        return redirect(url_for("panel"))
    return render_template("admin/editar.html", trabajo=trabajo)


@app.route("/admin/trabajos/<int:id_trabajo>/borrar", methods=["POST"])
@solo_admin
def trabajo_borrar(id_trabajo):
    trabajo = trabajo_o_404(id_trabajo)
    conexion = bd()
    conexion.execute("DELETE FROM trabajos WHERE id = ?", (id_trabajo,))
    conexion.commit()
    borrar_foto(trabajo["foto_antes"])
    borrar_foto(trabajo["foto_despues"])
    flash(f"Borramos «{trabajo['titulo']}».")
    return redirect(url_for("panel"))


@app.route("/admin/trabajos/<int:id_trabajo>/mover", methods=["POST"])
@solo_admin
def trabajo_mover(id_trabajo):
    trabajo_o_404(id_trabajo)
    conexion = bd()
    ids = [fila[0] for fila in conexion.execute("SELECT id FROM trabajos ORDER BY orden, id")]
    pos = ids.index(id_trabajo)
    otra = pos - 1 if request.form.get("hacia") == "arriba" else pos + 1
    if 0 <= otra < len(ids):
        ids[pos], ids[otra] = ids[otra], ids[pos]
        # Se renumera todo para que el orden quede limpio
        conexion.executemany("UPDATE trabajos SET orden = ? WHERE id = ?",
                             [(orden, id_) for orden, id_ in enumerate(ids)])
        conexion.commit()
    return redirect(url_for("panel") + f"#trabajo-{id_trabajo}")



@app.route("/coleccion")
def coleccion():
    prendas = bd().execute(
        "SELECT * FROM prendas WHERE visible = 1 ORDER BY orden, id"
    ).fetchall()
    return render_template("coleccion.html", prendas=prendas)


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
