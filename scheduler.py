"""
TAREAS PROGRAMADAS
Gestiona anuncios automáticos diarios, semanales, mensuales y anuales
Con lógica de recuperación para arranques tardíos.
"""

import logging
from datetime import datetime, timedelta, time
from telegram.ext import ContextTypes
from collections import defaultdict

from config import TIMEZONE, DAILY_ANNOUNCE_TIME, WEEKLY_ANNOUNCE_TIME
from game_data import game_data
from utils import (
    format_daily_announcement,
    format_weekly_announcement,
    format_monthly_announcement,
    format_yearly_announcement
)

logger = logging.getLogger(__name__)


# ========================
# VERIFICACIÓN DIARIA
# ========================

async def schedule_daily_check(context: ContextTypes.DEFAULT_TYPE):
    """Verifica y anuncia los resultados diarios"""
    try:
        logger.info(" Ejecutando verificación diaria...")

        chat_id = context.job.chat_id
        today = datetime.now(TIMEZONE).date()
        today_str = today.strftime('%Y-%m-%d')

        # Obtener datos de hoy
        if today_str not in game_data.daily_games:
            logger.info(" No hay participantes hoy")
            return

        game = game_data.daily_games[today_str]
        participants = game.get('participants', {})

        if not participants:
            # Sin participantes
            result = {
                'date': today_str,
                'wordle_id': game['wordle_id'],
                'winners': [],
                'best_score': None,
                'total_participants': 0,
                'reason': 'no_participants',
                'has_participants': False
            }
        else:
            # Calcular ganadores
            best_score = min(p['attempts'] for p in participants.values())
            winners = [
                (user_id, data['username'])
                for user_id, data in participants.items()
                if data['attempts'] == best_score
            ]

            result = {
                'date': today_str,
                'wordle_id': game['wordle_id'],
                'winners': winners,
                'best_score': best_score,
                'total_participants': len(participants),
                'reason': 'daily_announcement',
                'has_participants': True
            }

            # Actualizar estadísticas de ganadores
            for user_id, _ in winners:
                if user_id in game_data.player_stats:
                    game_data.player_stats[user_id]['daily_wins'] += 1

        # Marcar como anunciado
        game['announced'] = True
        game['announce_time'] = datetime.now(TIMEZONE).isoformat()
        game['winners'] = result['winners']

        # Enviar anuncio
        announcement = format_daily_announcement(result)
        await context.bot.send_message(
            chat_id=chat_id,
            text=announcement,
            parse_mode='Markdown'
        )

        game_data.save_data()
        logger.info(f" Anuncio diario enviado para {today_str}")

    except Exception as e:
        logger.error(f" Error en schedule_daily_check: {e}", exc_info=True)


# ========================
# VERIFICACIÓN SEMANAL (CON RECUPERACIÓN)
# ========================

async def schedule_weekly_check(context: ContextTypes.DEFAULT_TYPE):
    """Verifica y anuncia los resultados semanales (Domingos) o (Lunes Recuperación)"""
    try:
        logger.info(" Ejecutando verificación semanal...")

        chat_id = context.job.chat_id
        now = datetime.now(TIMEZONE)
        today = now.date()
        current_time = now.time()

        # ============================
        # LÓGICA DE RECUPERACIÓN
        # ============================
        # Si es lunes antes del mediodía (ej. 9:00 AM), el bot probablemente 
        # perdió el anuncio del domingo. Calculamos la semana PASADA.
        
        is_recovery = False
        week_start = today
        week_end = today

        if today.weekday() == 0: # 0 = Lunes
            if current_time < time(12, 0):
                logger.info(" RECUPERACIÓN: Detectado Lunes temprano. Calculando semana PASADA.")
                is_recovery = True
                # Domingo anterior es hoy - 1
                # Lunes anterior es hoy - 7
                week_end = today - timedelta(days=1)
                week_start = today - timedelta(days=7)
            else:
                # Lunes después de mediodía no tiene sentido anunciar la semana anterior
                # (Ya pasó mucho tiempo), así que simplemente salimos.
                logger.info(" Es lunes tarde, periodo de recuperación finalizado.")
                return
        
        elif today.weekday() == 6: # 6 = Domingo
            # Lógica estándar: Hoy es Domingo
            days_since_monday = today.weekday()
            week_start = today - timedelta(days=days_since_monday)
            week_end = today
        else:
            # Ni domingo ni lunes, no debería correr el job normal, 
            # pero si fue invocado manualmente o por lógica de arranque, usar semana actual.
            logger.info(" Día entre semana, usando rango actual de lunes a hoy.")
            days_since_monday = today.weekday()
            week_start = today - timedelta(days=days_since_monday)
            week_end = today

        logger.info(f" Semana: {week_start} a {week_end}")

        # Recopilar participantes
        weekly_participants = {}
        games_processed = 0

        # Iterar sobre los días específicos en lugar de todos
        current_date = week_start
        while current_date <= week_end:
            date_str = current_date.strftime('%Y-%m-%d')

            if date_str in game_data.daily_games:
                game = game_data.daily_games[date_str]
                participants = game.get('participants', {})
                games_processed += 1

                for user_id, data in participants.items():
                    if user_id not in weekly_participants:
                        weekly_participants[user_id] = {
                            'username': data['username'],
                            'attempts': [],
                            'days_participated': 0
                        }

                    weekly_participants[user_id]['attempts'].append(data['attempts'])
                    weekly_participants[user_id]['days_participated'] += 1
            
            current_date += timedelta(days=1)

        if not weekly_participants:
            logger.info(" No hay participantes en el rango de fechas.")
            return

        # Calcular ganador semanal
        weekly_stats = {}
        for user_id, data in weekly_participants.items():
            avg_attempts = sum(data['attempts']) / len(data['attempts'])
            weekly_stats[user_id] = {
                'username': data['username'],
                'avg_attempts': avg_attempts,
                'days_participated': data['days_participated'],
                'total_attempts': sum(data['attempts'])
            }

        # Ordenar por promedio
        sorted_weekly = sorted(
            weekly_stats.items(),
            key=lambda x: x[1]['avg_attempts']
        )

        best_avg = sorted_weekly[0][1]['avg_attempts']
        weekly_winners = [
            (user_id, stats['username'])
            for user_id, stats in sorted_weekly
            if stats['avg_attempts'] == best_avg
        ]

        result = {
            'date': f"{week_start} a {week_end}",
            'week_start': week_start,
            'week_end': week_end,
            'winners': weekly_winners,
            'best_avg': best_avg,
            'total_participants': len(weekly_participants),
            'games_processed': games_processed,
            'reason': 'weekly_announcement_recovery' if is_recovery else 'weekly_announcement'
        }

        # Actualizar estadísticas
        for user_id, _ in weekly_winners:
            if user_id in game_data.player_stats:
                game_data.player_stats[user_id]['weekly_wins'] += 1

        # Enviar anuncio
        announcement = format_weekly_announcement(result)
        await context.bot.send_message(
            chat_id=chat_id,
            text=announcement,
            parse_mode='Markdown'
        )

        game_data.save_data()
        logger.info(f" Anuncio semanal enviado - Ganadores: {len(weekly_winners)}")

    except Exception as e:
        logger.error(f" Error en schedule_weekly_check: {e}", exc_info=True)


# ========================
# VERIFICACIÓN MENSUAL (CON RECUPERACIÓN)
# ========================

async def schedule_monthly_check(context: ContextTypes.DEFAULT_TYPE):
    """Verifica y anuncia los resultados mensuales"""
    try:
        logger.info(" Ejecutando verificación mensual...")

        chat_id = context.job.chat_id
        now = datetime.now(TIMEZONE)
        today = now.date()
        current_time = now.time()
        
        # Lógica de recuperación
        is_recovery = False
        month_start = today.replace(day=1)
        month_end = today

        # Si es día 1 antes del mediodía
        if today.day == 1 and current_time < time(12, 0):
            logger.info(" RECUPERACIÓN: Detectado día 1 temprano. Calculando mes PASADO.")
            is_recovery = True
            month_end = today - timedelta(days=1)
            month_start = month_end.replace(day=1)
        else:
            # Último día del mes
            if today.month == 12:
                next_month = today.replace(year=today.year + 1, month=1, day=1)
            else:
                next_month = today.replace(month=today.month + 1, day=1)
            month_end = next_month - timedelta(days=1)
            # Si hoy no es el último día, no anunciar (a menos que sea forzado)
            if month_end != today and not is_recovery:
                logger.info(" No es fin de mes, no anuncia mensual.")
                return

        logger.info(f" Mes: {month_start.strftime('%B %Y')}")

        # Recopilar datos
        monthly_participants = {}
        games_processed = 0
        current_date = month_start

        while current_date <= month_end:
            date_str = current_date.strftime('%Y-%m-%d')

            if date_str in game_data.daily_games:
                game = game_data.daily_games[date_str]
                participants = game.get('participants', {})
                if participants:
                    games_processed += 1

                    for user_id, data in participants.items():
                        if user_id not in monthly_participants:
                            monthly_participants[user_id] = {
                                'username': data['username'],
                                'attempts': [],
                                'days_participated': 0
                            }
                        monthly_participants[user_id]['attempts'].append(data['attempts'])
                        monthly_participants[user_id]['days_participated'] += 1
            current_date += timedelta(days=1)

        if not monthly_participants:
            logger.info(" No hay participantes este mes.")
            return

        # Calcular ganador
        monthly_stats = {}
        for user_id, data in monthly_participants.items():
            avg_attempts = sum(data['attempts']) / len(data['attempts'])
            monthly_stats[user_id] = {
                'username': data['username'],
                'avg_attempts': avg_attempts,
                'days_participated': data['days_participated'],
                'total_attempts': sum(data['attempts'])
            }

        sorted_monthly = sorted(monthly_stats.items(), key=lambda x: x[1]['avg_attempts'])
        best_avg = sorted_monthly[0][1]['avg_attempts']
        monthly_winners = [
            (user_id, stats['username'])
            for user_id, stats in sorted_monthly
            if stats['avg_attempts'] == best_avg
        ]

        result = {
            'date': month_start.strftime('%B %Y'),
            'month': month_start.month,
            'year': month_start.year,
            'winners': monthly_winners,
            'best_avg': best_avg,
            'total_participants': len(monthly_participants),
            'games_processed': games_processed,
            'reason': 'monthly_announcement_recovery' if is_recovery else 'monthly_announcement'
        }

        for winner in monthly_winners:
            if winner[0] in game_data.player_stats:
                game_data.player_stats[winner[0]]['monthly_wins'] += 1

        announcement = format_monthly_announcement(result)
        await context.bot.send_message(chat_id=chat_id, text=announcement, parse_mode='Markdown')
        game_data.save_data()
        logger.info(f" Anuncio mensual enviado - Ganadores: {len(monthly_winners)}")

    except Exception as e:
        logger.error(f" Error en schedule_monthly_check: {e}", exc_info=True)


# ========================
# VERIFICACIÓN ANUAL (CON RECUPERACIÓN)
# ========================

async def schedule_yearly_check(context: ContextTypes.DEFAULT_TYPE):
    """Verifica y anuncia los resultados anuales (31 Diciembre)"""
    try:
        logger.info(" Ejecutando verificación anual...")

        chat_id = context.job.chat_id
        now = datetime.now(TIMEZONE)
        today = now.date()
        current_time = now.time()

        is_recovery = False
        year_start = today.replace(month=1, day=1)
        year_end = today

        # Si es 1 de Enero antes del mediodía
        if today.month == 1 and today.day == 1 and current_time < time(12, 0):
            logger.info(" RECUPERACIÓN: Detectado 1 Enero temprano. Calculando año PASADO.")
            is_recovery = True
            year_end = today - timedelta(days=1)
            year_start = year_end.replace(month=1, day=1)
        else:
            # Solo ejecutar el 31 de diciembre
            if not (today.month == 12 and today.day == 31):
                return

        logger.info(f" Año: {year_start.year}")

        yearly_participants = {}
        games_processed = 0
        current_date = year_start

        while current_date <= year_end:
            date_str = current_date.strftime('%Y-%m-%d')

            if date_str in game_data.daily_games:
                game = game_data.daily_games[date_str]
                participants = game.get('participants', {})
                if participants:
                    games_processed += 1

                    for user_id, data in participants.items():
                        if user_id not in yearly_participants:
                            yearly_participants[user_id] = {
                                'username': data['username'],
                                'attempts': [],
                                'days_participated': 0
                            }
                        yearly_participants[user_id]['attempts'].append(data['attempts'])
                        yearly_participants[user_id]['days_participated'] += 1
            current_date += timedelta(days=1)

        if not yearly_participants:
            logger.info(" No hay participantes este año.")
            return

        yearly_stats = {}
        for user_id, data in yearly_participants.items():
            avg_attempts = sum(data['attempts']) / len(data['attempts'])
            yearly_stats[user_id] = {
                'username': data['username'],
                'avg_attempts': avg_attempts,
                'days_participated': data['days_participated'],
                'total_attempts': sum(data['attempts'])
            }

        sorted_yearly = sorted(yearly_stats.items(), key=lambda x: x[1]['avg_attempts'])
        best_avg = sorted_yearly[0][1]['avg_attempts']
        yearly_winners = [
            (user_id, stats['username'])
            for user_id, stats in sorted_yearly
            if stats['avg_attempts'] == best_avg
        ]

        result = {
            'date': str(year_start.year),
            'year': year_start.year,
            'winners': yearly_winners,
            'best_avg': best_avg,
            'total_participants': len(yearly_participants),
            'games_processed': games_processed,
            'reason': 'yearly_announcement_recovery' if is_recovery else 'yearly_announcement'
        }

        for winner in yearly_winners:
            if winner[0] in game_data.player_stats:
                game_data.player_stats[winner[0]]['yearly_wins'] += 1

        announcement = format_yearly_announcement(result)
        await context.bot.send_message(chat_id=chat_id, text=announcement, parse_mode='Markdown')
        game_data.save_data()
        logger.info(f" Anuncio anual enviado - Ganadores: {len(yearly_winners)}")

    except Exception as e:
        logger.error(f" Error en schedule_yearly_check: {e}", exc_info=True)


# ========================
# LIMPIEZA DIARIA
# ========================

async def schedule_daily_cleanup(context: ContextTypes.DEFAULT_TYPE):
    """Limpia datos obsoletos y mantiene la integridad del sistema"""
    try:
        logger.info(" Ejecutando limpieza diaria...")

        today = datetime.now(TIMEZONE).date()
        cleanup_date = today - timedelta(days=90)  # Mantener últimos 90 días
        cleanup_date_str = cleanup_date.strftime('%Y-%m-%d')

        removed_count = 0

        # Eliminar juegos antiguos
        dates_to_remove = [
            date_str for date_str in game_data.daily_games.keys()
            if date_str < cleanup_date_str
        ]

        for date_str in dates_to_remove:
            del game_data.daily_games[date_str]
            removed_count += 1

        game_data.save_data()

        logger.info(f" Limpieza completada - {removed_count} registros antiguos eliminados")

    except Exception as e:
        logger.error(f" Error en schedule_daily_cleanup: {e}", exc_info=True)