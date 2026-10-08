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


def preparar_bd():
    with closing(sqlite3.connect(BD)) as conexion, conexion:
        conexion.executescript(ESQUEMA)
        if not conexion.execute("SELECT 1 FROM trabajos LIMIT 1").fetchone():
            conexion.executemany(
                "INSERT INTO trabajos (titulo, detalle, foto_antes, foto_despues, orden) VALUES (?, ?, ?, ?, ?)",
                [(*trabajo, orden) for orden, trabajo in enumerate(TRABAJOS_DEMO)],
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
}

# Vueltas de lana de cada pilar: (y inicial, vueltas, separación, lana).
# Las medidas usan el SVG del pilar (100 de ancho por 1400 de alto).
# Las usan el SVG de respaldo (_pilares.html) y el 3D (static/js/pilares3d.js).
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
    },
}


@app.context_processor
def datos_de_marca():
    return {"lanas": LANAS, "pilares": PILARES}


@app.route("/")
def inicio():
    return render_template("inicio.html")


@app.route("/arreglos")
def arreglos():
    trabajos = bd().execute("SELECT * FROM trabajos ORDER BY orden, id").fetchall()
    return render_template("arreglos.html", trabajos=trabajos)


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
