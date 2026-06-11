import logging
import os
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from sheets import registrar_salida, registrar_llegada, get_reporte
from db import init_db, guardar_salida, guardar_llegada, get_movimiento_activo, get_todos_movimientos

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Configuración ─────────────────────────────────────────────────────────────
TOKEN = os.getenv("BOT_TOKEN", "8797372101:AAF_qBXiX8jKo2huREVRLfl0IE7JieelQqA")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []

ESTABLECIMIENTOS = [
    "CENTRO URBANO",
    "ZHIMBRUG",
    "CUCHIL",
    "GUEL",
    "SAN BARTOLOME",
    "SARAR",
    "LUDO",
    "JIMA",
    "SAN JOSE DE RARANGA",
    "HOSPITAL SAN SEBASTIAN",
    "OTROS",
]

# ── Estados del ConversationHandler ──────────────────────────────────────────
ELIGIENDO_DESTINO, ESPERANDO_UBICACION_SALIDA = range(2)
ESPERANDO_UBICACION_LLEGADA = 10

# ── Teclados ──────────────────────────────────────────────────────────────────
def teclado_establecimientos():
    filas = [ESTABLECIMIENTOS[i:i+2] for i in range(0, len(ESTABLECIMIENTOS), 2)]
    return ReplyKeyboardMarkup(filas, resize_keyboard=True, one_time_keyboard=True)

def teclado_ubicacion(texto="📍 Enviar mi ubicación"):
    return ReplyKeyboardMarkup(
        [[KeyboardButton(texto, request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

# ── /start ────────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    nombre = update.effective_user.first_name
    await update.message.reply_text(
        f"👋 Hola *{nombre}*\\!\n\n"
        "Este bot registra tus movimientos de supervisión\\.\n\n"
        "Comandos disponibles:\n"
        "🚗 /salida — Registrar salida\n"
        "🏁 /llegada — Registrar llegada\n"
        "📋 /misturnos — Ver tus registros del día\n"
        "📊 /reporte — Reporte mensual \\(solo admin\\)",
        parse_mode="MarkdownV2"
    )

# ── /salida — paso 1: elegir destino ─────────────────────────────────────────
async def salida_inicio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Verificar que no tenga una salida activa sin llegada
    activo = get_movimiento_activo(user_id)
    if activo:
        await update.message.reply_text(
            f"⚠️ Ya tienes una salida activa hacia *{activo['destino']}* "
            f"registrada a las {activo['hora_salida']}.\n\n"
            "Primero registra tu /llegada.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "🚗 *¿A qué establecimiento te diriges?*",
        parse_mode="Markdown",
        reply_markup=teclado_establecimientos()
    )
    return ELIGIENDO_DESTINO

# ── /salida — paso 2: guardar destino y pedir ubicación ──────────────────────
async def salida_destino(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    destino = update.message.text.upper()
    if destino not in ESTABLECIMIENTOS:
        await update.message.reply_text(
            "❌ Destino no válido. Por favor elige de la lista.",
            reply_markup=teclado_establecimientos()
        )
        return ELIGIENDO_DESTINO

    ctx.user_data["destino"] = destino
    await update.message.reply_text(
        f"📍 Destino: *{destino}*\n\n"
        "Ahora comparte tu ubicación actual para confirmar la salida:",
        parse_mode="Markdown",
        reply_markup=teclado_ubicacion("📍 Enviar ubicación de salida")
    )
    return ESPERANDO_UBICACION_SALIDA

# ── /salida — paso 3: registrar con ubicación ─────────────────────────────────
async def salida_ubicacion(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    location = update.message.location
    destino = ctx.user_data.get("destino", "OTROS")
    hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Guardar en base de datos local
    mov_id = guardar_salida(
        user_id=user.id,
        nombre=f"{user.first_name} {user.last_name or ''}".strip(),
        username=user.username or "",
        destino=destino,
        hora_salida=hora,
        lat=location.latitude,
        lon=location.longitude
    )

    # Guardar en Google Sheets
    try:
        registrar_salida(
            nombre=f"{user.first_name} {user.last_name or ''}".strip(),
            username=user.username or str(user.id),
            destino=destino,
            hora_salida=hora,
            lat=location.latitude,
            lon=location.longitude,
            mov_id=mov_id
        )
        sheets_ok = "✅ Guardado en Google Sheets"
    except Exception as e:
        logger.error(f"Error Sheets salida: {e}")
        sheets_ok = "⚠️ Error al guardar en Sheets (guardado localmente)"

    await update.message.reply_text(
        f"✅ *Salida registrada*\n\n"
        f"👤 {user.first_name}\n"
        f"📍 Destino: {destino}\n"
        f"🕐 Hora: {hora}\n"
        f"🗺️ Ubicación: {location.latitude:.4f}, {location.longitude:.4f}\n\n"
        f"{sheets_ok}\n\n"
        "Cuando llegues, usa /llegada para registrar tu arribo.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

# ── /llegada — pedir ubicación ────────────────────────────────────────────────
async def llegada_inicio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    activo = get_movimiento_activo(user_id)

    if not activo:
        await update.message.reply_text(
            "⚠️ No tienes ninguna salida activa registrada.\n"
            "Primero usa /salida."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"🏁 Registrando llegada desde *{activo['destino']}*\n\n"
        "Comparte tu ubicación para confirmar:",
        parse_mode="Markdown",
        reply_markup=teclado_ubicacion("📍 Enviar ubicación de llegada")
    )
    return ESPERANDO_UBICACION_LLEGADA

# ── /llegada — guardar con ubicación ─────────────────────────────────────────
async def llegada_ubicacion(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    location = update.message.location
    hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    activo = get_movimiento_activo(user.id)
    if not activo:
        await update.message.reply_text("⚠️ No hay salida activa. Usa /salida primero.")
        return ConversationHandler.END

    # Calcular duración
    salida_dt = datetime.strptime(activo["hora_salida"], "%Y-%m-%d %H:%M:%S")
    llegada_dt = datetime.strptime(hora, "%Y-%m-%d %H:%M:%S")
    duracion_min = int((llegada_dt - salida_dt).total_seconds() / 60)
    horas = duracion_min // 60
    minutos = duracion_min % 60

    # Guardar en DB
    guardar_llegada(
        mov_id=activo["id"],
        hora_llegada=hora,
        lat_llegada=location.latitude,
        lon_llegada=location.longitude
    )

    # Guardar en Sheets
    try:
        registrar_llegada(
            mov_id=activo["id"],
            hora_llegada=hora,
            lat=location.latitude,
            lon=location.longitude,
            duracion=f"{horas}h {minutos}m"
        )
        sheets_ok = "✅ Actualizado en Google Sheets"
    except Exception as e:
        logger.error(f"Error Sheets llegada: {e}")
        sheets_ok = "⚠️ Error al actualizar en Sheets"

    await update.message.reply_text(
        f"🏁 *Llegada registrada*\n\n"
        f"👤 {user.first_name}\n"
        f"📍 Destino visitado: {activo['destino']}\n"
        f"🕐 Salida: {activo['hora_salida']}\n"
        f"🕐 Llegada: {hora}\n"
        f"⏱️ Duración: {horas}h {minutos}m\n\n"
        f"{sheets_ok}",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

# ── /misturnos ────────────────────────────────────────────────────────────────
async def mis_turnos(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    hoy = datetime.now().strftime("%Y-%m-%d")
    movimientos = get_todos_movimientos(user_id=user.id, fecha=hoy)

    if not movimientos:
        await update.message.reply_text("📋 No tienes registros hoy.")
        return

    texto = f"📋 *Tus movimientos de hoy ({hoy})*\n\n"
    for m in movimientos:
        llegada = m["hora_llegada"] or "⏳ En curso"
        duracion = m.get("duracion", "—")
        texto += (
            f"🏥 *{m['destino']}*\n"
            f"  🚗 Salida: {m['hora_salida'][11:16]}\n"
            f"  🏁 Llegada: {llegada[11:16] if m['hora_llegada'] else '⏳ En curso'}\n\n"
        )

    await update.message.reply_text(texto, parse_mode="Markdown")

# ── /reporte (solo admin) ─────────────────────────────────────────────────────
async def reporte(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ No tienes permisos para este comando.")
        return

    await update.message.reply_text("⏳ Generando reporte, un momento...")
    try:
        url = get_reporte()
        await update.message.reply_text(
            f"📊 *Reporte mensual generado*\n\n"
            f"[Ver en Google Sheets]({url})",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error reporte: {e}")
        await update.message.reply_text(f"❌ Error generando reporte: {e}")

# ── Cancelar conversación ─────────────────────────────────────────────────────
async def cancelar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Operación cancelada.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    # Conversación de SALIDA
    salida_conv = ConversationHandler(
        entry_points=[CommandHandler("salida", salida_inicio)],
        states={
            ELIGIENDO_DESTINO: [MessageHandler(filters.TEXT & ~filters.COMMAND, salida_destino)],
            ESPERANDO_UBICACION_SALIDA: [MessageHandler(filters.LOCATION, salida_ubicacion)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )

    # Conversación de LLEGADA
    llegada_conv = ConversationHandler(
        entry_points=[CommandHandler("llegada", llegada_inicio)],
        states={
            ESPERANDO_UBICACION_LLEGADA: [MessageHandler(filters.LOCATION, llegada_ubicacion)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(salida_conv)
    app.add_handler(llegada_conv)
    app.add_handler(CommandHandler("misturnos", mis_turnos))
    app.add_handler(CommandHandler("reporte", reporte))

    logger.info("Bot iniciado ✅")
    app.run_polling()

if __name__ == "__main__":
    main()
