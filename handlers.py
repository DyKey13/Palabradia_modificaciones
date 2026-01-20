"""
MANEJADORES DE COMANDOS Y MENSAJES
Gestiona todas las interacciones del usuario con el bot
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters

from game_data import game_data
from utils import (
    parse_wordle_message,
    validate_wordle_id,
    format_leaderboard,
    format_player_stats,
    format_daily_announcement
)

logger = logging.getLogger(__name__)


# ========================
# COMANDOS DE USUARIO
# ========================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start - Bienvenida"""
    try:
        message = (
            "🎮 **Bienvenido a WORDLE BOT** 🎮\n\n"
            "Este bot registra tus intentos diarios de Wordle y mantiene un ranking.\n\n"
            "📝 **Cómo usar:**\n"
            "Solo envía tu resultado en el formato:\n"
            "`Palabra del día #1467 4/6`\n\n"
            "📊 **Comandos disponibles:**\n"
            "/help - Ayuda y formato\n"
            "/today - Estado del juego de hoy\n"
            "/stats - Tus estadísticas personales\n"
            "/leaderboard - Ranking global\n"
        )
        await update.message.reply_text(message, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error en start_command: {e}", exc_info=True)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /help - Ayuda"""
    try:
        message = (
            "📖 **AYUDA - FORMATO REQUERIDO**\n\n"
            "El bot detecta automáticamente resultados en este formato:\n\n"
            "`Palabra del día #1467 4/6`\n\n"
            "**Donde:**\n"
            "• `Palabra del día` - Nombre del juego\n"
            "• `#1467` - ID del juego (número)\n"
            "• `4/6` - Tus intentos / Máximo intentos\n\n"
            "**Ejemplo válido:**\n"
            "```\n"
            "Palabra del día #1500 3/6\n"
            "```\n\n"
            "**Notas:**\n"
            "✅ Solo se aceptan intentos del 1 al 6\n"
            "✅ El ID debe ser un número válido\n"
            "✅ Se registra automáticamente\n"
            "✅ Un intento por día\n"
        )
        await update.message.reply_text(message, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error en help_command: {e}", exc_info=True)


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /today - Estado actual del juego"""
    try:
        result = game_data.get_today_status()
        
        if not result:
            await update.message.reply_text("📅 No hay datos para hoy todavía.")
            return

        message = (
            f"📅 **ESTADO DE HOY**\n\n"
            f"🎮 Palabra del día: #{result['wordle_id']}\n"
            f"👥 Participantes: {result['total_participants']}\n"
        )

        if result.get('best_score'): 
            message += f"🏆 Mejor score: {result['best_score']}/6\n"

        if result['winners']:
            winners_list = ", ".join([f"@{name}" for _, name in result['winners']])
            message += f"⭐ Ganadores: {winners_list}\n"

        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error en today_command: {e}", exc_info=True)
        await update.message.reply_text("❌ Error obteniendo estado de hoy.")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /stats - Estadísticas del usuario"""
    try:
        user_id = str(update.effective_user.id)
        stats = game_data.get_player_stats(user_id)

        if not stats:
            await update.message.reply_text("📊 No tienes estadísticas aún. ¡Comienza a jugar!")
            return

        message = format_player_stats(user_id, stats)
        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error en stats_command: {e}", exc_info=True)
        await update.message.reply_text("❌ Error obteniendo estadísticas.")


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /leaderboard - Tabla de líderes"""
    try:
        leaderboard = game_data.get_leaderboard(limit=10)
        
        if not leaderboard:
            await update.message.reply_text("🏆 Leaderboard vacío. ¡Sé el primero!")
            return

        message = format_leaderboard(leaderboard)
        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error en leaderboard_command: {e}", exc_info=True)
        await update.message.reply_text("❌ Error obteniendo leaderboard.")


# ========================
# COMANDOS ADMINISTRATIVOS
# ========================

async def announce_daily_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /announce_daily - Fuerza anuncio diario"""
    try:
        # Verificar si es admin (simplificado, ajustar según seguridad)
        # Aquí no estamos usando una lista de estricta de IDs por simplicidad en la respuesta
        # pero podrías agregar: if update.effective_user.id not in config.ADMIN_IDS: return
        
        from scheduler import schedule_daily_check
        dummy_context = type('obj', (object,), {
            'bot': context.bot,
            'job': type('obj', (object,), {'chat_id': update.effective_chat.id})()
        })()

        await schedule_daily_check(dummy_context)
        await update.message.reply_text("✅ Anuncio diario forzado.")

    except Exception as e:
        logger.error(f"Error en announce_daily_admin: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {e}")


# ========================
# MANEJADOR DE MENSAJES
# ========================

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa mensajes con resultados de Wordle"""
    try:
        if not update.message or not update.message.text:
            return

        text = update.message.text
        parsed = parse_wordle_message(text)

        if not parsed:
            return

        wordle_id, attempts = parsed

        # Validar Wordle ID
        is_valid, error_msg = validate_wordle_id(wordle_id)
        if not is_valid:
            await update.message.reply_text(
                f"❌ {error_msg}",
                parse_mode='Markdown'
            )
            return

        # Registrar participación
        user_id = str(update.effective_user.id)
        username = update.effective_user.first_name

        success, response = game_data.register_participation(
            user_id=user_id,
            username=username,
            wordle_id=wordle_id,
            attempts=attempts
        )

        # Responder al usuario
        await update.message.reply_text(response, parse_mode='Markdown')

        # Verificar si hay ganadores (Anuncio inmediato si se cumple condición)
        result = game_data.check_and_get_daily_winners()
        if result and result.get('winners'):
            announcement = format_daily_announcement(result)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=announcement,
                parse_mode='Markdown'
            )

    except Exception as e:
        logger.error(f"Error en message_handler: {e}", exc_info=True)


# ========================
# CONFIGURACIÓN DE HANDLERS
# ========================

def setup_handlers(application):
    """Registra todos los handlers en la aplicación"""
    try:
        # Comandos de usuario
        application.add_handler(CommandHandler('start', start_command))
        application.add_handler(CommandHandler('help', help_command))
        application.add_handler(CommandHandler('today', today_command))
        application.add_handler(CommandHandler('stats', stats_command))
        application.add_handler(CommandHandler('leaderboard', leaderboard_command))

        # Comandos administrativos
        application.add_handler(CommandHandler('announce_daily', announce_daily_admin))

        # Manejador de mensajes
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            message_handler
        ))

        logger.info("✅ Handlers configurados correctamente")

    except Exception as e:
        logger.error(f"❌ Error configurando handlers: {e}", exc_info=True)