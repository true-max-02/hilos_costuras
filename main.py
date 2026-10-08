import os
import secrets
import sqlite3
from contextlib import closing

from flask import Flask, g, render_template

app = Flask(__name__)

# La clave se lee del entorno. Si falta, se genera una temporal (solo sirve para desarrollo).
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

BD = os.path.join(app.root_path, "tienda.db")

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



@app.route("/coleccion")
def coleccion():
    prendas = bd().execute(
        "SELECT * FROM prendas WHERE visible = 1 ORDER BY orden, id"
    ).fetchall()
    return render_template("coleccion.html", prendas=prendas)


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
