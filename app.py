import os
import sqlite3
import secrets
import base64
from io import BytesIO
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, flash
import qrcode
from PIL import Image


# ============================================================
# CONFIGURACIÓN
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DB = BASE_DIR / "database.db"

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "clave-local-desarrollo"
)


# ============================================================
# BASE DE DATOS
# ============================================================

def get_db():

    conn = sqlite3.connect(DB)

    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS graduados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo_documento TEXT NOT NULL,
            documento TEXT NOT NULL UNIQUE,
            nombre TEXT NOT NULL,
            programa TEXT NOT NULL,
            fecha_graduacion TEXT NOT NULL,
            numero_diploma TEXT DEFAULT '',
            numero_acta TEXT DEFAULT '',
            codigo_verificacion TEXT UNIQUE
        )
    """)

    # --------------------------------------------------------
    # COMPATIBILIDAD CON BASE DE DATOS ANTERIOR
    # --------------------------------------------------------

    columnas = [
        fila["name"]
        for fila in conn.execute(
            "PRAGMA table_info(graduados)"
        ).fetchall()
    ]

    if "numero_diploma" not in columnas:

        conn.execute("""
            ALTER TABLE graduados
            ADD COLUMN numero_diploma TEXT DEFAULT ''
        """)

    if "numero_acta" not in columnas:

        conn.execute("""
            ALTER TABLE graduados
            ADD COLUMN numero_acta TEXT DEFAULT ''
        """)

    if "codigo_verificacion" not in columnas:

        conn.execute("""
            ALTER TABLE graduados
            ADD COLUMN codigo_verificacion TEXT
        """)

    # --------------------------------------------------------
    # CREAR CÓDIGOS PARA REGISTROS ANTIGUOS
    # --------------------------------------------------------

    registros_sin_codigo = conn.execute("""
        SELECT id
        FROM graduados
        WHERE codigo_verificacion IS NULL
           OR codigo_verificacion = ''
    """).fetchall()

    for registro in registros_sin_codigo:

        codigo = secrets.token_urlsafe(18)

        conn.execute("""
            UPDATE graduados
            SET codigo_verificacion = ?
            WHERE id = ?
        """, (
            codigo,
            registro["id"]
        ))

    # --------------------------------------------------------
    # ÍNDICE ÚNICO
    # --------------------------------------------------------

    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
        idx_codigo_verificacion
        ON graduados(codigo_verificacion)
    """)

    conn.commit()

    conn.close()


# ============================================================
# GENERACIÓN DEL QR CON LOGO UNAB
# ============================================================

def qr_data_uri(texto):

    # --------------------------------------------------------
    # CREAR QR CON ALTA CORRECCIÓN DE ERRORES
    # --------------------------------------------------------

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=4
    )

    qr.add_data(texto)

    qr.make(
        fit=True
    )

    imagen_qr = qr.make_image(
        fill_color="black",
        back_color="white"
    ).convert("RGBA")

    # --------------------------------------------------------
    # BUSCAR LOGO UNAB
    # --------------------------------------------------------

    logo_path = (
        BASE_DIR
        / "static"
        / "img"
        / "unab-logo.png"
    )

    if logo_path.exists():

        logo = Image.open(
            logo_path
        ).convert("RGBA")

        # ----------------------------------------------------
        # REDIMENSIONAR LOGO
        # ----------------------------------------------------

        ancho_maximo = int(
            imagen_qr.width * 0.28
        )

        relacion = (
            ancho_maximo
            / logo.width
        )

        nuevo_alto = int(
            logo.height
            * relacion
        )

        logo = logo.resize(
            (
                ancho_maximo,
                nuevo_alto
            ),
            Image.LANCZOS
        )

        # ----------------------------------------------------
        # CREAR FONDO BLANCO PARA EL LOGO
        # ----------------------------------------------------

        margen = 18

        caja_ancho = (
            logo.width
            + margen * 2
        )

        caja_alto = (
            logo.height
            + margen * 2
        )

        caja = Image.new(
            "RGBA",
            (
                caja_ancho,
                caja_alto
            ),
            "white"
        )

        # ----------------------------------------------------
        # COLOCAR LOGO SOBRE FONDO BLANCO
        # ----------------------------------------------------

        caja.alpha_composite(
            logo,
            (
                margen,
                margen
            )
        )

        # ----------------------------------------------------
        # CALCULAR CENTRO DEL QR
        # ----------------------------------------------------

        x = (
            imagen_qr.width
            - caja.width
        ) // 2

        y = (
            imagen_qr.height
            - caja.height
        ) // 2

        # ----------------------------------------------------
        # COLOCAR LOGO EN EL CENTRO DEL QR
        # ----------------------------------------------------

        imagen_qr.alpha_composite(
            caja,
            (
                x,
                y
            )
        )

    # --------------------------------------------------------
    # CONVERTIR QR A BASE64
    # --------------------------------------------------------

    buffer = BytesIO()

    imagen_qr.save(
        buffer,
        format="PNG"
    )

    imagen_base64 = base64.b64encode(
        buffer.getvalue()
    ).decode("ascii")

    return (
        "data:image/png;base64,"
        + imagen_base64
    )


# ============================================================
# PÁGINA PRINCIPAL
# ============================================================

@app.route(
    "/",
    methods=["GET", "POST"]
)
def inicio():

    if request.method == "POST":

        tipo = request.form.get(
            "tipo_consultante",
            ""
        ).strip()

        documento = request.form.get(
            "documento_consultante",
            ""
        ).strip()

        nombre = request.form.get(
            "nombre_consultante",
            ""
        ).strip()

        if not tipo or not documento or not nombre:

            flash(
                "Todos los campos son obligatorios."
            )

            return redirect(
                url_for("inicio")
            )

        return redirect(
            url_for(
                "consulta",
                tipo=tipo,
                documento=documento,
                nombre=nombre
            )
        )

    return render_template(
        "inicio.html"
    )


# ============================================================
# CONSULTA PÚBLICA
# ============================================================

@app.route(
    "/consulta",
    methods=["GET", "POST"]
)
def consulta():

    consultante = {

        "tipo": request.args.get(
            "tipo",
            ""
        ),

        "documento": request.args.get(
            "documento",
            ""
        ),

        "nombre": request.args.get(
            "nombre",
            ""
        )
    }

    if request.method == "POST":

        autorizacion = request.form.get(
            "autorizacion"
        )

        if autorizacion != "si":

            flash(
                "Debe aceptar la autorización para continuar."
            )

            return redirect(
                url_for(
                    "consulta",
                    **consultante
                )
            )

        datos = {

            "tipo": request.form.get(
                "tipo_graduado",
                ""
            ).strip(),

            "documento": request.form.get(
                "documento_graduado",
                ""
            ).strip(),

            "programa": request.form.get(
                "programa",
                ""
            ).strip(),

            "fecha": request.form.get(
                "fecha_graduacion",
                ""
            ).strip()
        }

        if not all(
            datos.values()
        ):

            flash(
                "Todos los campos son obligatorios."
            )

            return redirect(
                url_for(
                    "consulta",
                    **consultante
                )
            )

        conn = get_db()

        registro = conn.execute("""
            SELECT *
            FROM graduados
            WHERE tipo_documento = ?
              AND documento = ?
              AND programa = ?
              AND fecha_graduacion = ?
        """, (
            datos["tipo"],
            datos["documento"],
            datos["programa"],
            datos["fecha"]
        )).fetchone()

        conn.close()

        return render_template(
            "resultado.html",
            consultante=consultante,
            datos=datos,
            resultado=registro
        )

    return render_template(
        "consulta.html",
        consultante=consultante
    )


# ============================================================
# REGISTRO DE GRADUADOS
# ============================================================

@app.route(
    "/registro",
    methods=["GET", "POST"]
)
def registro():

    if request.method == "POST":

        datos = {

            "tipo": request.form.get(
                "tipo_documento",
                ""
            ).strip(),

            "documento": request.form.get(
                "documento",
                ""
            ).strip(),

            "nombre": request.form.get(
                "nombre",
                ""
            ).strip(),

            "programa": request.form.get(
                "programa",
                ""
            ).strip(),

            "fecha": request.form.get(
                "fecha_graduacion",
                ""
            ).strip(),

            "numero_diploma": request.form.get(
                "numero_diploma",
                ""
            ).strip(),

            "numero_acta": request.form.get(
                "numero_acta",
                ""
            ).strip()
        }

        # ----------------------------------------------------
        # CAMPOS OBLIGATORIOS
        # ----------------------------------------------------

        if not all(
            datos.values()
        ):

            flash(
                "Todos los campos son obligatorios."
            )

            return redirect(
                url_for("registro")
            )

        # ----------------------------------------------------
        # GENERAR CÓDIGO ÚNICO
        # ----------------------------------------------------

        codigo = secrets.token_urlsafe(
            18
        )

        conn = get_db()

        try:

            cursor = conn.execute("""
                INSERT INTO graduados (
                    tipo_documento,
                    documento,
                    nombre,
                    programa,
                    fecha_graduacion,
                    numero_diploma,
                    numero_acta,
                    codigo_verificacion
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datos["tipo"],
                datos["documento"],
                datos["nombre"],
                datos["programa"],
                datos["fecha"],
                datos["numero_diploma"],
                datos["numero_acta"],
                codigo
            ))

            conn.commit()

            nuevo_id = cursor.lastrowid

        except sqlite3.IntegrityError:

            conn.rollback()

            conn.close()

            flash(
                "Ya existe un registro con ese número de documento."
            )

            return redirect(
                url_for("registro")
            )

        conn.close()

        # ----------------------------------------------------
        # IR A PANTALLA DEL QR
        # ----------------------------------------------------

        return redirect(
            url_for(
                "registro_qr",
                graduado_id=nuevo_id
            )
        )

    return render_template(
        "registro.html"
    )


# ============================================================
# LISTA DE REGISTROS
# ============================================================

@app.route(
    "/registro/lista"
)
def lista_registros():

    conn = get_db()

    registros = conn.execute("""
        SELECT *
        FROM graduados
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "lista_registros.html",
        registros=registros
    )


# ============================================================
# GENERAR QR DEL GRADUADO
# ============================================================

@app.route(
    "/registro/qr/<int:graduado_id>"
)
def registro_qr(
    graduado_id
):

    conn = get_db()

    graduado = conn.execute("""
        SELECT *
        FROM graduados
        WHERE id = ?
    """, (
        graduado_id,
    )).fetchone()

    conn.close()

    if not graduado:

        return (
            "Registro no encontrado",
            404
        )

    # --------------------------------------------------------
    # URL QUE QUEDARÁ DENTRO DEL QR
    # --------------------------------------------------------

    verification_url = url_for(
        "verificar_qr",
        codigo=graduado[
            "codigo_verificacion"
        ],
        _external=True
    )

    # --------------------------------------------------------
    # CREAR QR CON LOGO UNAB
    # --------------------------------------------------------

    qr = qr_data_uri(
        verification_url
    )

    return render_template(
        "registro_qr.html",
        graduado=graduado,
        qr=qr,
        verification_url=verification_url
    )


# ============================================================
# VERIFICACIÓN MEDIANTE QR
# ============================================================

@app.route(
    "/verificar/<codigo>"
)
def verificar_qr(
    codigo
):

    conn = get_db()

    graduado = conn.execute("""
        SELECT *
        FROM graduados
        WHERE codigo_verificacion = ?
    """, (
        codigo,
    )).fetchone()

    conn.close()

    return render_template(
        "verificar_qr.html",
        graduado=graduado
    )


# ============================================================
# SALIR
# ============================================================

@app.route(
    "/salir"
)
def salir():

    return "Consulta finalizada."


# ============================================================
# INICIAR APLICACIÓN
# ============================================================

init_db()


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),
        debug=True
    )