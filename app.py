import os
import sqlite3
import secrets
import base64
from io import BytesIO
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, flash
import qrcode


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

    # Crear tabla si todavía no existe
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
    # Compatibilidad con la base de datos anterior
    # --------------------------------------------------------

    columnas = [
        fila["name"]
        for fila in conn.execute(
            "PRAGMA table_info(graduados)"
        ).fetchall()
    ]

    # Agregar número de diploma si no existe
    if "numero_diploma" not in columnas:
        conn.execute("""
            ALTER TABLE graduados
            ADD COLUMN numero_diploma TEXT DEFAULT ''
        """)

    # Agregar número de acta si no existe
    if "numero_acta" not in columnas:
        conn.execute("""
            ALTER TABLE graduados
            ADD COLUMN numero_acta TEXT DEFAULT ''
        """)

    # Agregar código de verificación si no existe
    if "codigo_verificacion" not in columnas:
        conn.execute("""
            ALTER TABLE graduados
            ADD COLUMN codigo_verificacion TEXT
        """)

    # --------------------------------------------------------
    # Crear códigos para registros antiguos
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
        """, (codigo, registro["id"]))

    # Índice único para los códigos
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
        idx_codigo_verificacion
        ON graduados(codigo_verificacion)
    """)

    conn.commit()
    conn.close()


# ============================================================
# GENERACIÓN DEL QR
# ============================================================

def qr_data_uri(texto):
    imagen = qrcode.make(texto)

    buffer = BytesIO()
    imagen.save(buffer, format="PNG")

    imagen_base64 = base64.b64encode(
        buffer.getvalue()
    ).decode("ascii")

    return "data:image/png;base64," + imagen_base64


# ============================================================
# PÁGINA PRINCIPAL
# ============================================================

@app.route("/", methods=["GET", "POST"])
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

    return render_template("inicio.html")


# ============================================================
# CONSULTA PÚBLICA
# ============================================================

@app.route("/consulta", methods=["GET", "POST"])
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

        if not all(datos.values()):

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

@app.route("/registro", methods=["GET", "POST"])
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

        # Comprobar campos obligatorios
        if not all(datos.values()):

            flash(
                "Todos los campos son obligatorios."
            )

            return redirect(
                url_for("registro")
            )

        # Generar código único
        codigo = secrets.token_urlsafe(18)

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

        # Después de registrar,
        # llevar directamente a la pantalla del QR
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

@app.route("/registro/lista")
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

@app.route("/registro/qr/<int:graduado_id>")
def registro_qr(graduado_id):

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

    # URL que será almacenada dentro del QR
    verification_url = url_for(
        "verificar_qr",
        codigo=graduado["codigo_verificacion"],
        _external=True
    )

    # Crear imagen QR
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

@app.route("/verificar/<codigo>")
def verificar_qr(codigo):

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

@app.route("/salir")
def salir():

    return "Consulta finalizada."


# ============================================================
# INICIAR APLICACIÓN
# ============================================================

if __name__ == "__main__":

    init_db()

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