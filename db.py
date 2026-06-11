import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "supervision.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS movimientos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            nombre      TEXT NOT NULL,
            username    TEXT,
            destino     TEXT NOT NULL,
            hora_salida TEXT NOT NULL,
            lat_salida  REAL,
            lon_salida  REAL,
            hora_llegada TEXT,
            lat_llegada  REAL,
            lon_llegada  REAL,
            duracion    TEXT,
            sheets_row  INTEGER
        )
    """)
    conn.commit()
    conn.close()
    print("✅ Base de datos inicializada")

def guardar_salida(user_id, nombre, username, destino, hora_salida, lat, lon):
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO movimientos
           (user_id, nombre, username, destino, hora_salida, lat_salida, lon_salida)
           VALUES (?,?,?,?,?,?,?)""",
        (user_id, nombre, username, destino, hora_salida, lat, lon)
    )
    mov_id = cur.lastrowid
    conn.commit()
    conn.close()
    return mov_id

def guardar_llegada(mov_id, hora_llegada, lat_llegada, lon_llegada):
    conn = get_conn()
    # Calcular duración
    row = conn.execute("SELECT hora_salida FROM movimientos WHERE id=?", (mov_id,)).fetchone()
    duracion = ""
    if row:
        from datetime import datetime
        salida = datetime.strptime(row["hora_salida"], "%Y-%m-%d %H:%M:%S")
        llegada = datetime.strptime(hora_llegada, "%Y-%m-%d %H:%M:%S")
        mins = int((llegada - salida).total_seconds() / 60)
        duracion = f"{mins // 60}h {mins % 60}m"

    conn.execute(
        """UPDATE movimientos SET
           hora_llegada=?, lat_llegada=?, lon_llegada=?, duracion=?
           WHERE id=?""",
        (hora_llegada, lat_llegada, lon_llegada, duracion, mov_id)
    )
    conn.commit()
    conn.close()

def get_movimiento_activo(user_id):
    """Retorna el movimiento sin hora_llegada (viaje en curso)"""
    conn = get_conn()
    row = conn.execute(
        """SELECT * FROM movimientos
           WHERE user_id=? AND hora_llegada IS NULL
           ORDER BY id DESC LIMIT 1""",
        (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def get_todos_movimientos(user_id=None, fecha=None):
    conn = get_conn()
    query = "SELECT * FROM movimientos WHERE 1=1"
    params = []
    if user_id:
        query += " AND user_id=?"
        params.append(user_id)
    if fecha:
        query += " AND hora_salida LIKE ?"
        params.append(f"{fecha}%")
    query += " ORDER BY hora_salida DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
