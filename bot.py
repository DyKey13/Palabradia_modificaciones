#!/usr/bin/env python3
"""
BOT PRINCIPAL - VERSIÓN DEFINITIVA
Gestión completa del bot Wordle con manejo robusto de errores
"""

import sys
import io

# =============================================================================
# FIX CRÍTICO: FORZAR UTF-8 ANTES DE CARGAR NADA
# Esto evita el error 'utf-8 codec can't encode character' al iniciar
# =============================================================================
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import asyncio
import logging
from datetime import datetime, timedelta
from telegram.ext import Application
from types import SimpleNamespace

import config
from handlers import setup_handlers
from game_data import game_data
from utils import parse_wordle_message, validate_wordle_id, format_daily_announcement

# Configurar logging (Ya stdout está arreglado)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class WordleBot:
    """Clase principal para gestionar el bot Wordle"""
    
    def __init__(self):
        self.application = None
        self.running = False
        self.chat_id = None
        self.last_check = datetime.now(config.TIMEZONE)

    async def initialize(self) -> int:
        """Inicializa el bot y retorna el chat_id del grupo"""
        logger.info("=" * 60)
        logger.info("🤖 WORDLE COMPETITION BOT - Inicializando...")
        logger.info("=" * 60)

        # Validar token
        if not config.TOKEN:
            logger.error("❌ ERROR: TELEGRAM_BOT_TOKEN no configurado en .env")
            sys.exit(1)

        logger.info("✅ Token de Telegram configurado")

        try:
            # Crear aplicación
            self.application = Application.builder().token(config.TOKEN).build()

            # Configurar handlers
            setup_handlers(self.application)

            # Inicializar aplicación
            await self.application.initialize()

            # Obtener información del bot
            bot_info = await self.application.bot.get_me()
            logger.info(f"✅ Bot: {bot_info.first_name} (@{bot_info.username})")

            # Detectar grupo
            chat_id = await self.detect_group()
            if not chat_id:
                logger.error("❌ No se pudo obtener ID del grupo")
                return None

            self.chat_id = chat_id
            logger.info(f"✅ Grupo detectado: ID {chat_id}")

            # Configurar tareas programadas
            await self.setup_jobs(chat_id)

            # ==========================================
            # ORDEN CRÍTICO: Procesar pendientes ANTES de verificar ganadores
            # Esto permite recuperar datos de hoy y ayer al arrancar
            # ==========================================
            await self.process_pending_updates(chat_id)
            
            # ==========================================
            # VERIFICACIÓN Y RECUPERACIÓN DE ANUNCIOS
            # ==========================================
            await self.check_all_pending_announcements(chat_id)

            # Enviar mensaje de inicio
            await self.send_startup_message(chat_id)

            return chat_id

        except Exception as e:
            logger.error(f"❌ Error durante inicialización: {e}", exc_info=True)
            return None

    async def detect_group(self) -> int:
        """Detecta el grupo automáticamente esperando un mensaje"""
        logger.info("\n🔍 Detectando grupo...")
        logger.info("💬 Envía un mensaje en el grupo ahora...")

        max_attempts = 30
        for attempt in range(max_attempts):
            try:
                updates = await self.application.bot.get_updates(timeout=5)
                
                for update in updates:
                    if update.message and update.message.chat.type in ['group', 'supergroup']:
                        chat_id = update.message.chat.id
                        chat_title = update.message.chat.title
                        logger.info(f"✅ Grupo detectado: {chat_title} (ID: {chat_id})")
                        return chat_id

                if (attempt + 1) % 5 == 0:
                    logger.info(f"⏳ Esperando... ({attempt + 1}/{max_attempts})")

            except Exception as e:
                logger.warning(f"⚠️ Error detectando grupo: {e}")

            await asyncio.sleep(1)

        logger.error("❌ Timeout: No se detectó grupo en 30 segundos")
        return None

    async def check_all_pending_announcements(self, chat_id: int):
        """
        Verifica anuncios pendientes de HOY y AYER (Recuperación)
        """
        try:
            logger.info("🔄 Verificando anuncios pendientes...")
            
            today = datetime.now(config.TIMEZONE).date()
            today_str = today.strftime('%Y-%m-%d')
            yesterday_str = (today - timedelta(days=1)).strftime('%Y-%m-%d')

            # 1. Verificar HOY (Estándar)
            # La función de game_data ya maneja la lógica de 5 participantes o 7PM
            logger.info("🔄 Verificando ganadores de hoy según reglas...")
            result_today = game_data.check_and_get_daily_winners()
            
            if result_today and result_today.get('winners'):
                announcement = format_daily_announcement(result_today)
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=announcement,
                    parse_mode='Markdown'
                )

            # 2. Verificar AYER (Recuperación si el bot estuvo apagado)
            if yesterday_str in game_data.daily_games:
                yesterday_game = game_data.daily_games[yesterday_str]
                if not yesterday_game.get('announced', False) and yesterday_game.get('participants'):
                    logger.info(f"📅 Anuncio pendiente encontrado para AYER: {yesterday_str}")
                    await self._force_daily_announcement(chat_id, yesterday_str, yesterday_game)
            
            # 3. Verificar Anuncios Periódicos (Semanal, Mensual, Anual)
            await self._check_pending_periodic_announcements(chat_id, today)
            
            logger.info("✅ Verificación de anuncios completada")

        except Exception as e:
            logger.error(f"❌ Error en check_all_pending_announcements: {e}", exc_info=True)

    async def _check_pending_periodic_announcements(self, chat_id: int, today):
        """Verifica anuncios semanales, mensuales y anuales pendientes y los ejecuta si es necesario"""
        try:
            from scheduler import (
                schedule_weekly_check,
                schedule_monthly_check,
                schedule_yearly_check
            )

            # Crear un contexto dummy seguro
            dummy_context = SimpleNamespace(
                bot=self.application.bot,
                job=SimpleNamespace(chat_id=chat_id)
            )

            now_time = datetime.now(config.TIMEZONE).time()
            
            # ============================
            # VERIFICACIÓN SEMANAL (DOMINGO)
            # ============================
            # Si es Domingo Y la hora actual es >= 20:00, anunciar.
            if today.weekday() == 6 and now_time >= config.WEEKLY_ANNOUNCE_TIME:
                logger.info("🔄 Ejecutando anuncio semanal pendiente...")
                await schedule_weekly_check(dummy_context)
            
            # Caso de seguridad: Si es lunes temprano y el bot estaba apagado ayer noche
            elif today.weekday() == 0 and now_time.hour < 12:
                logger.info("🔄 Revisión de lunes por la mañana: Verificando semanal del domingo...")
                await schedule_weekly_check(dummy_context)

            # ============================
            # VERIFICACIÓN MENSUAL (ÚLTIMO DÍA)
            # ============================
            # Si mañana cambia de mes (hoy es el último) Y la hora actual es >= 20:00
            next_day = today + timedelta(days=1)
            if next_day.month != today.month and now_time >= config.MONTHLY_ANNOUNCE_TIME:
                logger.info("🔄 Ejecutando anuncio mensual pendiente...")
                await schedule_monthly_check(dummy_context)

            # ============================
            # VERIFICACIÓN ANUAL (31 DIC)
            # ============================
            if today.month == 12 and today.day == 31 and now_time >= config.YEARLY_ANNOUNCE_TIME:
                logger.info("🔄 Ejecutando anuncio anual pendiente...")
                await schedule_yearly_check(dummy_context)

        except Exception as e:
            logger.warning(f"⚠️ Error verificando anuncios periódicos: {e}")

    async def _force_daily_announcement(self, chat_id: int, date_str: str, game: dict):
        """Fuerza un anuncio diario (usado para ayer o retrasos)"""
        try:
            participants = game.get('participants', {})
            
            if not participants:
                result = {
                    'date': date_str,
                    'wordle_id': game['wordle_id'],
                    'winners': [],
                    'best_score': None,
                    'total_participants': 0,
                    'reason': 'late_no_participants',
                    'has_participants': False
                }
            else:
                best_score = min(p['attempts'] for p in participants.values())
                winners = [
                    (user_id, data['username'])
                    for user_id, data in participants.items()
                    if data['attempts'] == best_score
                ]
                
                result = {
                    'date': date_str,
                    'wordle_id': game['wordle_id'],
                    'winners': winners,
                    'best_score': best_score,
                    'total_participants': len(participants),
                    'reason': 'late_announcement',
                    'has_participants': True
                }

            # Actualizar estadísticas (si no se habían actualizado antes)
            for user_id, _ in result['winners']:
                if user_id in game_data.player_stats:
                    game_data.player_stats[user_id]['daily_wins'] += 1

            # Marcar como anunciado
            game['announced'] = True
            game['announce_time'] = datetime.now(config.TIMEZONE).isoformat()
            game['winners'] = result['winners']

            # Enviar anuncio
            announcement = f"🔙 **ANUNCIO RETRASADO/RECUPERADO**\n\n" + format_daily_announcement(result)
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=announcement,
                parse_mode='Markdown'
            )
            
            game_data.save_data()
            logger.info(f"✅ Anuncio enviado para {date_str}")

        except Exception as e:
            logger.error(f"❌ Error en _force_daily_announcement: {e}", exc_info=True)

    async def setup_jobs(self, chat_id: int):
        """Configura las tareas programadas"""
        try:
            from scheduler import (
                schedule_daily_check,
                schedule_weekly_check,
                schedule_monthly_check,
                schedule_yearly_check,
                schedule_daily_cleanup
            )

            job_queue = self.application.job_queue
            if not job_queue:
                logger.warning("⚠️ Job queue no disponible")
                return

            # Anuncio diario
            job_queue.run_daily(
                schedule_daily_check,
                time=config.DAILY_ANNOUNCE_TIME,
                days=tuple(range(7)),
                chat_id=chat_id,
                name="daily_announcement"
            )

            # Anuncio semanal (domingos)
            job_queue.run_daily(
                schedule_weekly_check,
                time=config.WEEKLY_ANNOUNCE_TIME,
                days=(6,),
                chat_id=chat_id,
                name="weekly_announcement"
            )

            # Anuncio mensual (último día del mes)
            job_queue.run_monthly(
                schedule_monthly_check,
                when=config.MONTHLY_ANNOUNCE_TIME,
                chat_id=chat_id,
                name="monthly_announcement"
            )

            # Anuncio anual (31 de diciembre)
            job_queue.run_daily(
                schedule_yearly_check,
                time=config.YEARLY_ANNOUNCE_TIME,
                days=tuple(range(7)),
                chat_id=chat_id,
                name="yearly_announcement"
            )

            # Limpieza diaria
            job_queue.run_daily(
                schedule_daily_cleanup,
                time=config.DAILY_CLEANUP_TIME,
                days=tuple(range(7)),
                chat_id=chat_id,
                name="daily_cleanup"
            )

            logger.info(f"✅ {len(job_queue.jobs())} trabajos programados correctamente")

        except Exception as e:
            logger.error(f"❌ Error configurando jobs: {e}", exc_info=True)

    async def send_startup_message(self, chat_id: int):
        """Envía mensaje de bienvenida al grupo"""
        try:
            message = (
                "🎮 **WORDLE BOT ACTIVADO** 🎮\n\n"
                "✅ *Conectado y escuchando mensajes*\n\n"
                "📝 *Formato requerido:*\n"
                "```\n"
                "Palabra del día #1467 4/6\n"
                "```\n\n"
                "🔧 *Comandos disponibles:*\n"
                "/help - Ver formato y ayuda\n"
                "/today - Estado actual\n"
                "/stats - Tus estadísticas\n"
                "/leaderboard - Tabla de líderes\n"
            )

            await self.application.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode='Markdown'
            )
            logger.info("✅ Mensaje de inicio enviado")

        except Exception as e:
            logger.error(f"❌ Error enviando mensaje de inicio: {e}", exc_info=True)

    async def process_pending_updates(self, chat_id: int):
        """Procesa updates pendientes del backlog"""
        try:
            logger.info("🔁 Procesando updates pendientes...")
            
            updates = await self.application.bot.get_updates(timeout=1)
            found_count = 0
            registered_count = 0
            last_id = None

            for update in updates:
                try:
                    last_id = update.update_id
                    
                    if not getattr(update, 'message', None):
                        continue

                    msg = update.message
                    if msg.chat.type not in ['group', 'supergroup']:
                        continue

                    text = msg.text or ''
                    parsed = parse_wordle_message(text)
                    
                    if not parsed:
                        continue

                    found_count += 1
                    wordle_id, attempts = parsed
                    is_valid, error_msg = validate_wordle_id(wordle_id)

                    if not is_valid:
                        continue

                    user_id = str(msg.from_user.id)
                    username = msg.from_user.first_name

                    # IMPORTANTE: allow_previous_day=True permite recoger el juego de ayer al arrancar
                    success, response = game_data.register_participation(
                        user_id=user_id,
                        username=username,
                        wordle_id=wordle_id,
                        attempts=attempts,
                        allow_previous_day=True 
                    )

                    if success:
                        registered_count += 1
                        try:
                            await self.application.bot.send_message(
                                chat_id=msg.chat.id,
                                text=response,
                                parse_mode='Markdown'
                            )
                        except Exception as e:
                            logger.warning(f"⚠️ Error respondiendo: {e}")

                except Exception as e:
                    logger.warning(f"⚠️ Error procesando update {getattr(update, 'update_id', '?')}: {e}")

            # Limpiar updates procesados
            if last_id is not None:
                try:
                    await self.application.bot.get_updates(offset=last_id + 1)
                    logger.info(f"✅ Updates limpiados hasta ID {last_id}")
                except Exception as e:
                    logger.warning(f"⚠️ Error limpiando updates: {e}")

            logger.info(f"✅ Resumen: {found_count} encontrados, {registered_count} registrados")

        except Exception as e:
            logger.error(f"❌ Error procesando updates pendientes: {e}", exc_info=True)

    async def run(self):
        """Ejecuta el bot principal"""
        try:
            # Inicializar
            chat_id = await self.initialize()
            if not chat_id:
                logger.error("❌ No se pudo inicializar el bot")
                return

            # Iniciar aplicación
            await self.application.start()

            logger.info("\n" + "=" * 60)
            logger.info("🚀 BOT INICIADO CORRECTAMENTE")
            logger.info("=" * 60)
            logger.info(f"📱 GRUPO ID: {chat_id}")
            logger.info(f"⏰ Anuncio diario: {config.DAILY_ANNOUNCE_TIME.strftime('%H:%M')}")
            logger.info(f"📅 Anuncio semanal: Domingos {config.WEEKLY_ANNOUNCE_TIME.strftime('%H:%M')}")
            logger.info("=" * 60)

            # Iniciar polling
            self.running = True
            await self.application.updater.start_polling(
                drop_pending_updates=False,
                timeout=30,
                poll_interval=2.0,
                allowed_updates=['message', 'callback_query']
            )

            logger.info("📡 Bot escuchando mensajes...")

            # Mantener bot activo
            while self.running:
                await asyncio.sleep(5)

        except KeyboardInterrupt:
            logger.info("👋 Interrupción por teclado")
        except Exception as e:
            logger.error(f"❌ Error crítico: {e}", exc_info=True)
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Apaga el bot elegantemente"""
        try:
            logger.info("\n🔴 Apagando bot...")
            self.running = False

            if self.application:
                logger.info("💾 Guardando datos...")
                game_data.save_data()

                logger.info("🛑 Deteniendo aplicación...")
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()

            logger.info("✅ Bot apagado correctamente")

        except Exception as e:
            logger.error(f"❌ Error durante shutdown: {e}", exc_info=True)


def main():
    """Punto de entrada principal"""
    # Loop policy para Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    bot = WordleBot()
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("\n👋 Programa terminado por usuario")
    except Exception as e:
        logger.error(f"❌ Error crítico: {e}", exc_info=True)


if __name__ == '__main__':
    main()