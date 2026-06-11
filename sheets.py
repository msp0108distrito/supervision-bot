import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# ── Configuración ─────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")  # ID del Google Sheet
CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS", "credentials.json")

# Cabeceras de la hoja
HEADERS = [
    "ID", "Nombre", "Usuario Telegram", "Destino",
    "Fecha", "Hora Salida", "Lat Salida", "Lon Salida",
    "Hora Llegada", "Lat Llegada", "Lon Llegada", "Duración"
]

def get_client():
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)

def get_hoja():
    client = get_client()
    sh = client.open_by_key(SPREADSHEET_ID)
    mes = datetime.now().strftime("%Y-%m")  # Hoja por mes: "2025-01"
    try:
        hoja = sh.worksheet(mes)
    except gspread.WorksheetNotFound:
        hoja = sh.add_worksheet(title=mes, rows=1000, cols=15)
        hoja.append_row(HEADERS)
        # Formato de cabecera (negrita)
        hoja.format("A1:L1", {"textFormat": {"bold": True}})
    return hoja

def registrar_salida(nombre, username, destino, hora_salida, lat, lon, mov_id):
    hoja = get_hoja()
    fecha = hora_salida[:10]
    hora = hora_salida[11:19]
    fila = [
        mov_id, nombre, f"@{username}", destino,
        fecha, hora, lat, lon,
        "", "", "", ""  # llegada vacía por ahora
    ]
    hoja.append_row(fila)

def registrar_llegada(mov_id, hora_llegada, lat, lon, duracion):
    hoja = get_hoja()
    # Buscar la fila con ese mov_id
    ids = hoja.col_values(1)  # columna ID
    try:
        fila_num = ids.index(str(mov_id)) + 1
    except ValueError:
        # Si no encuentra el ID, no hace nada
        return

    hora = hora_llegada[11:19]
    # Actualizar columnas de llegada: I (9), J (10), K (11), L (12)
    hoja.update_cell(fila_num, 9, hora)
    hoja.update_cell(fila_num, 10, lat)
    hoja.update_cell(fila_num, 11, lon)
    hoja.update_cell(fila_num, 12, duracion)

def get_reporte():
    """Retorna la URL del Google Sheet"""
    return f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"
