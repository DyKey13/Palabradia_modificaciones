#!/usr/bin/env python3
"""
BOT LIGERO - 'La Palabra del Día'
Optimizado para bajo consumo (teléfono viejo)
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, date
from telegram import Update
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters
)

# --- Configuración básica ---
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Cargar .env de forma robusta (sin librerías externas) ---
def load_env():
    env = {}
    # Obtiene la ruta de la carpeta donde está este script
    base_path = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(base_path, ".env")
    
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Ignorar comentarios y líneas vacías
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    # Limpiar espacios, comillas y posibles saltos de línea invisibles
                    env[key.strip()] = val.strip().strip('"').strip("'")
        
        # Log para confirmar que leyó las llaves (sin mostrar el token por seguridad)
        if env:
            logger.info(f"✅ Variables cargadas: {list(env.keys())}")
            
    except FileNotFoundError:
        logger.error(f"❌ Archivo .env no encontrado en: {env_path}")
        sys.exit(1)
    return env

ENV = load_env()
TOKEN = ENV.get("TELEGRAM_BOT_TOKEN")
GROUP_ID = ENV.get("GROUP_ID")

if not TOKEN or not GROUP_ID:
    logger.error("❌ Faltan TELEGRAM_BOT_TOKEN o GROUP_ID en .env")
    sys.exit(1)

# --- Estado del juego ---
STATE_FILE = "estado.json"

def load_state():
    today = str(date.today())
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data.get("dia") == today:
                return data
    except Exception as e:
        logger.warning(f"⚠️ No se pudo cargar estado: {e}")
    return {"dia": today, "participaciones": {}}

def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"❌ Error al guardar estado: {e}")

# --- Procesar participación ---
def parse_wordle(text: str):
    """Extrae intentos de 'Palabra del día #1234 X/6'"""
    import re
    match = re.search(r'Palabra\s+del\s+d[íi]a\s+#\d+\s+(\d+)/6', text, re.IGNORECASE)
    if match:
        attempts = int(match.group(1))
        if 1 <= attempts <= 6:
            return attempts
        elif attempts == 0:  # perdió todos los intentos
            return 7  # representamos "X" como 7
    return None

async def process_participation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or f"user{user_id}"
    text = update.message.text

    attempts = parse_wordle(text)
    if attempts is None:
        return  # no es una participación válida

    # Registrar participación
    if user_id not in state["participaciones"]:
        state["participaciones"][user_id] = {
            "username": username,
            "attempts": attempts,
            "timestamp": update.message.date.isoformat()
        }
        save_state(state)
        logger.info(f"✅ Nueva participación: @{username} ({attempts}/6)")

        # ✅ Responder al jugador
        await update.message.reply_text(f"✅ Participación registrada: {attempts if attempts <= 6 else 'X'}/6")

        # Verificar si ya hay 5 participaciones → anunciar ganador
        if len(state["participaciones"]) >= 5:
            await announce_daily_winner(state, update)

# --- Anunciar ganador diario ---
async def announce_daily_winner(state, update):
    # Ordenar por intentos (menor = mejor), luego por timestamp
    participants = list(state["participaciones"].items())
    participants.sort(key=lambda x: (x[1]["attempts"], x[1]["timestamp"]))

    winner_id, winner_data = participants[0]
    winner_name = winner_data["username"]
    attempts = winner_data["attempts"]

    result = "🎉 ¡GANADOR DIARIO!\n"
    result += f"🏆 @{winner_name} con {attempts if attempts <= 6 else 'X'}/6\n\n"
    result += "📊 Participantes:\n"
    for i, (uid, data) in enumerate(participants[:5], 1):
        att = data["attempts"]
        result += f"{i}. @{data['username']} → {att if att <= 6 else 'X'}/6\n"

    await update.message.reply_text(result)

# --- Comandos ---
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != GROUP_ID:
        return
    state = load_state()
    user_id = str(update.effective_user.id)
    if user_id in state["participaciones"]:
        data = state["participaciones"][user_id]
        att = data["attempts"]
        msg = f"✅ Tu participación: {att if att <= 6 else 'X'}/6"
    else:
        msg = "❌ Aún no has participado hoy."
    await update.message.reply_text(msg)

async def cmd_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != GROUP_ID:
        return
    state = load_state()
    if not state["participaciones"]:
        await update.message.reply_text("📊 Aún no hay participaciones hoy.")
        return

    participants = sorted(
        state["participaciones"].values(),
        key=lambda x: (x["attempts"], x["timestamp"])
    )
    msg = "🏅 Top 5 de hoy:\n"
    for i, p in enumerate(participants[:5], 1):
        att = p["attempts"]
        msg += f"{i}. @{p['username']} → {att if att <= 6 else 'X'}/6\n"
    await update.message.reply_text(msg)

# --- Handler principal ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != GROUP_ID:
        return  # ignorar otros chats

    text = update.message.text
    if not text:
        return

    # Procesar participación espontánea
    if "palabra del día" in text.lower() and "/6" in text:
        await process_participation(update, context)

# --- Inicio del bot ---
async def main():
    logger.info("🚀 Iniciando bot ligero...")
    app = Application.builder().token(TOKEN).build()

    # Handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("leaderboard", cmd_leaderboard))

    logger.info(f"✅ Bot configurado para el grupo: {GROUP_ID}")
    logger.info("📡 Escuchando mensajes... (modo bajo consumo)")

    # Iniciar polling ligero
    await app.initialize()
    await app.start()
    await app.updater.start_polling(
        drop_pending_updates=False,
        poll_interval=200,
        timeout=10
    )

    # Mantener vivo sin bucles pesados
    try:
        while True:
            await asyncio.sleep(10)
    except KeyboardInterrupt:
        logger.info("👋 Apagando bot...")
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())