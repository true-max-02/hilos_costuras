import hmac
import os
import secrets
import sqlite3
import time
import warnings
from contextlib import closing
from datetime import date, timedelta
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

CREATE TABLE IF NOT EXISTS reservas (
    id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL,
    telefono TEXT NOT NULL,         -- solo dígitos, con código de país: 56912345678
    correo TEXT NOT NULL DEFAULT '',
    servicio TEXT NOT NULL,         -- clave de SERVICIOS
    detalle TEXT NOT NULL,
    fecha TEXT NOT NULL,            -- AAAA-MM-DD
    franja TEXT NOT NULL,           -- clave de FRANJAS
    estado TEXT NOT NULL DEFAULT 'nueva',   -- clave de ESTADOS
    creada TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
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

# Agenda de arreglos: lo que se puede pedir, cuándo, y cómo avanza cada reserva
SERVICIOS = {
    "basta": "Basta",
    "cierre": "Cambio de cierre",
    "ajuste": "Ajuste",
    "reparacion": "Reparación",
    "otro": "Otro arreglo",
}
FRANJAS = {"manana": ("Mañana", "10 a 13 h"), "tarde": ("Tarde", "15 a 19 h")}
ESTADOS = {"nueva": "Nueva", "confirmada": "Confirmada", "lista": "Lista para retirar"}
# Desde cada estado, el botón que la hace avanzar: (estado siguiente, texto del botón)
AVANCE = {"nueva": ("confirmada", "Confirmar hora"), "confirmada": ("lista", "Marcar lista")}
DIAS_PARA_RESERVAR = 60
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def reservas_demo():
    """Reservas de muestra para que el panel no parta vacío en la demo.
    Las fechas se cuentan desde hoy y nunca caen en domingo."""
    hoy = date.today()

    def dia(n):
        fecha = hoy + timedelta(days=n)
        return (fecha + timedelta(days=1) if fecha.weekday() == 6 else fecha).isoformat()

    return [
        ("Javiera Muñoz", "56900000001", "", "basta",
         "Jeans negros, acortar unos 4 cm. Los uso con zapatillas.", dia(1), "manana", "nueva"),
        ("Tomás Reyes", "56900000002", "tomas.reyes@example.com", "cierre",
         "Chaqueta de cuero con el cierre separado abajo.", dia(2), "tarde", "confirmada"),
        ("Carmen Soto", "56900000003", "", "ajuste",
         "Vestido de fiesta: entallar la cintura y subir un poco los tirantes.", dia(4), "manana", "nueva"),
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
        if not conexion.execute("SELECT 1 FROM reservas LIMIT 1").fetchone():
            conexion.executemany(
                "INSERT INTO reservas (nombre, telefono, correo, servicio, detalle, fecha, franja, estado)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                reservas_demo(),
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


@app.template_filter("fecha_larga")
def fecha_larga(texto):
    """2026-10-15 -> jueves 15 de octubre"""
    fecha = date.fromisoformat(texto)
    return f"{DIAS[fecha.weekday()]} {fecha.day} de {MESES[fecha.month - 1]}"


@app.template_filter("fecha_corta")
def fecha_corta(texto):
    """2026-10-15 -> jue 15 oct"""
    fecha = date.fromisoformat(texto)
    return f"{DIAS[fecha.weekday()][:3]} {fecha.day} {MESES[fecha.month - 1][:3]}"


@app.template_filter("telefono")
def telefono(digitos):
    """56912345678 -> +56 9 1234 5678"""
    if len(digitos) == 11 and digitos.startswith("569"):
        return f"+56 9 {digitos[3:7]} {digitos[7:]}"
    return "+" + digitos


app.jinja_env.globals.update(servicios=SERVICIOS, franjas=FRANJAS, estados=ESTADOS, avance=AVANCE)


def pagina_arreglos(**extra):
    trabajos = bd().execute("SELECT * FROM trabajos ORDER BY orden, id").fetchall()
    hoy = date.today()
    extra.setdefault("datos", {})
    extra.setdefault("errores", {})
    return render_template(
        "arreglos.html", trabajos=trabajos,
        fecha_min=(hoy + timedelta(days=1)).isoformat(),
        fecha_max=(hoy + timedelta(days=DIAS_PARA_RESERVAR)).isoformat(),
        **extra,
    )


@app.route("/arreglos")
def arreglos():
    # Recién agendada: se muestra la ficha de confirmación en vez del formulario
    reserva = None
    if "reserva_hecha" in session:
        reserva = bd().execute("SELECT * FROM reservas WHERE id = ?",
                               (session.pop("reserva_hecha"),)).fetchone()
    # Los servicios de la portada llegan con el arreglo ya elegido (?servicio=basta)
    return pagina_arreglos(reserva=reserva, datos={"servicio": request.args.get("servicio", "")})


def limpiar_telefono(texto):
    """Deja solo los dígitos, con código de país. Acepta "9 1234 5678", "+56 9 1234 5678"..."""
    digitos = "".join(c for c in texto if c.isdigit())
    if len(digitos) == 9 and digitos.startswith("9"):
        digitos = "56" + digitos
    elif len(digitos) == 8:
        digitos = "569" + digitos
    if not 10 <= len(digitos) <= 15:
        raise ValueError
    return digitos


def correo_valido(correo):
    """Revisión simple: algo@dominio.algo, sin espacios."""
    usuario, arroba, dominio = correo.rpartition("@")
    return (bool(usuario and arroba) and "@" not in usuario and "." in dominio.strip(".")
            and len(correo) <= 120 and not any(c.isspace() for c in correo))


def error_fecha(texto):
    """Devuelve qué tiene de malo el día elegido, o None si sirve."""
    try:
        fecha = date.fromisoformat(texto)
    except ValueError:
        return "Elige el día en que traerás la prenda."
    hoy = date.today()
    if fecha <= hoy:
        return "Elige un día a partir de mañana."
    if fecha > hoy + timedelta(days=DIAS_PARA_RESERVAR):
        return f"Por ahora se puede pedir hora hasta {DIAS_PARA_RESERVAR} días adelante."
    if fecha.weekday() == 6:
        return "Los domingos el taller está cerrado; elige otro día."
    return None


def leer_reserva(formulario):
    """Revisa el formulario de la agenda. Devuelve (datos, errores por campo)."""
    datos = {campo: formulario.get(campo, "").strip()
             for campo in ("nombre", "telefono", "correo", "servicio", "detalle", "fecha", "franja")}
    errores = {}
    if not datos["nombre"]:
        errores["nombre"] = "Escribe tu nombre."
    elif len(datos["nombre"]) > 80:
        errores["nombre"] = "El nombre va hasta 80 letras."
    try:
        datos["telefono_limpio"] = limpiar_telefono(datos["telefono"])
    except ValueError:
        # Espacios que no se cortan, para que el ejemplo no quede partido en dos líneas
        errores["telefono"] = "Revisa el número; por ejemplo: +56 9 1234 5678."
    if datos["correo"] and not correo_valido(datos["correo"]):
        errores["correo"] = "Revisa el correo, o déjalo en blanco."
    if datos["servicio"] not in SERVICIOS:
        errores["servicio"] = "Elige qué arreglo necesitas."
    if not datos["detalle"]:
        errores["detalle"] = "Cuéntanos qué necesita tu prenda."
    elif len(datos["detalle"]) > 500:
        errores["detalle"] = "Resúmelo en 500 letras como máximo."
    if mensaje := error_fecha(datos["fecha"]):
        errores["fecha"] = mensaje
    if datos["franja"] not in FRANJAS:
        errores["franja"] = "Elige mañana o tarde."
    return datos, errores


@app.route("/arreglos/agendar", methods=["GET", "POST"])
def agendar():
    if request.method == "GET":
        return redirect(url_for("arreglos", _anchor="agendar"))
    # Trampa para robots: un campo escondido que una persona nunca llena
    if request.form.get("sitio_web"):
        return redirect(url_for("arreglos", _anchor="agendar"))
    datos, errores = leer_reserva(request.form)
    if errores:
        return pagina_arreglos(datos=datos, errores=errores), 400
    conexion = bd()
    cursor = conexion.execute(
        "INSERT INTO reservas (nombre, telefono, correo, servicio, detalle, fecha, franja)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (datos["nombre"], datos["telefono_limpio"], datos["correo"], datos["servicio"],
         datos["detalle"], datos["fecha"], datos["franja"]),
    )
    conexion.commit()
    session["reserva_hecha"] = cursor.lastrowid
    return redirect(url_for("arreglos", _anchor="agendar"))


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
            if request.endpoint == "agendar":
                # Al cliente se le devuelve su formulario lleno, con un token nuevo
                return pagina_arreglos(datos=request.form, errores={
                    "general": "La página llevaba mucho rato abierta. Revisa tus datos y envía de nuevo."}), 400
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


# Reservas que llegan desde "Agenda tu arreglo"

def reservas_nuevas():
    return bd().execute("SELECT COUNT(*) FROM reservas WHERE estado = 'nueva'").fetchone()[0]


app.jinja_env.globals["reservas_nuevas"] = reservas_nuevas


def reserva_o_404(id_reserva):
    reserva = bd().execute("SELECT * FROM reservas WHERE id = ?", (id_reserva,)).fetchone()
    if reserva is None:
        abort(404)
    return reserva


@app.route("/admin/reservas")
@solo_admin
def reservas():
    # Por fecha y horario; las que ya están listas para retirar van al final
    filas = bd().execute(
        "SELECT * FROM reservas ORDER BY estado = 'lista', fecha, franja, id"
    ).fetchall()
    return render_template("admin/reservas.html", reservas=filas)


@app.route("/admin/reservas/<int:id_reserva>/estado", methods=["POST"])
@solo_admin
def reserva_estado(id_reserva):
    reserva = reserva_o_404(id_reserva)
    estado = request.form.get("estado", "")
    if estado in ESTADOS:
        conexion = bd()
        conexion.execute("UPDATE reservas SET estado = ? WHERE id = ?", (estado, id_reserva))
        conexion.commit()
        flash(f"La reserva de {reserva['nombre']} quedó como «{ESTADOS[estado].lower()}».")
    return redirect(url_for("reservas") + f"#reserva-{id_reserva}")


@app.route("/admin/reservas/<int:id_reserva>/borrar", methods=["POST"])
@solo_admin
def reserva_borrar(id_reserva):
    reserva = reserva_o_404(id_reserva)
    conexion = bd()
    conexion.execute("DELETE FROM reservas WHERE id = ?", (id_reserva,))
    conexion.commit()
    flash(f"Borramos la reserva de {reserva['nombre']}.")
    return redirect(url_for("reservas"))



@app.route("/coleccion")
def coleccion():
    prendas = bd().execute(
        "SELECT * FROM prendas WHERE visible = 1 ORDER BY orden, id"
    ).fetchall()
    return render_template("coleccion.html", prendas=prendas)


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
