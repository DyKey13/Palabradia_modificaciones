"""
UTILIDADES Y FUNCIONES AUXILIARES
Funciones para parsear mensajes, validar datos y formatear anuncios
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict

import config

logger = logging.getLogger(__name__)


# ========================
# PARSING DE MENSAJES
# ========================

def parse_wordle_message(text: str) -> Optional[Tuple[int, int]]:
    """
    Parsea un mensaje de Wordle y extrae ID y número de intentos.
    SOLO ACEPTA el formato: "La palabra del día #XXXX Y/6"
    NO acepta variantes como "tildes", "frase", "paises", etc.

    Args:
        text: Texto del mensaje
        
    Returns:
        Tupla (wordle_id, attempts) o None si no es válido
    """
    try:
        if not text or not isinstance(text, str):
            return None

        # Patrón para buscar EXACTAMENTE "La palabra del día #número intentos/6"
        # ^\s* - Principio de la cadena, posibles espacios iniciales
        # La\s+palabra\s+del\s+día\s+#(\d+)\s+(\d)/6
        # \s*$ - Posibles espacios finales, fin de la cadena
        # re.IGNORECASE para ignorar mayúsculas/minúsculas en la parte fija
        pattern = r'^\s*La\s+palabra\s+del\s+día\s+#(\d+)\s+(\d)/6\s*$'

        match = re.search(pattern, text, re.IGNORECASE)

        if not match:
            # logger.debug(f"No match para 'La palabra del día': {text}") # Opcional: para depurar
            return None

        wordle_id = int(match.group(1))
        attempts = int(match.group(2))

        # Validar que los intentos sean entre 1 y 6
        if not (1 <= attempts <= 6):
            logger.debug(f"Intentos fuera de rango (1-6): {attempts}")
            return None

        logger.debug(f"✅ Mensaje parseado: ID={wordle_id}, Intentos={attempts}")
        return (wordle_id, attempts)

    except Exception as e:
        logger.debug(f"Error parseando mensaje: {e}")
        return None


# ========================
# VALIDACIÓN DE DATOS
# ========================

def validate_wordle_id(wordle_id: int) -> Tuple[bool, str]:
    """
    Valida que un ID de Wordle sea válido
    
    Args:
        wordle_id: ID a validar
        
    Returns:
        Tupla (es_válido, mensaje_error)
    """
    try:
        # ID debe ser número positivo
        if not isinstance(wordle_id, int) or wordle_id <= 0:
            return False, "❌ ID de Wordle debe ser un número positivo"

        # Calcular ID esperado aproximadamente
        # Wordle comenzó el 21 de noviembre de 2021 (ID 1)
        start_date = datetime(2021, 11, 21, tzinfo=config.TIMEZONE)
        today = datetime.now(config.TIMEZONE)
        expected_id = 1 + (today - start_date).days

        # Permitir IDs ligeramente en el futuro (máximo 7 días)
        max_allowed_id = expected_id + 7
        min_allowed_id = max(1, expected_id - 365)  # Hasta 1 año atrás

        if wordle_id < min_allowed_id:
            return False, f"❌ ID muy antiguo (mínimo: {min_allowed_id})"

        if wordle_id > max_allowed_id:
            return False, f"❌ ID en el futuro (máximo: {max_allowed_id})"

        logger.debug(f"✅ ID validado: {wordle_id}")
        return True, "ID válido"

    except Exception as e:
        logger.warning(f"Error validando ID: {e}")
        return False, "❌ Error validando ID"


# ========================
# FORMATEO DE ANUNCIOS
# ========================

def format_daily_announcement(result: Dict) -> str:
    """
    Formatea el anuncio de ganadores diarios
    
    Args:
        result: Diccionario con datos del ganador diario
        
    Returns:
        Texto formateado para Telegram
    """
    try:
        date = result['date']
        wordle_id = result['wordle_id']
        winners = result['winners']
        best_score = result['best_score']
        total_participants = result['total_participants']
        has_participants = result.get('has_participants', True)

        if not has_participants or not winners:
            message = (
                f"📅 **RESULTADOS DEL DÍA**\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🎮 Palabra del día: #{wordle_id}\n"
                f"📆 Fecha: {date}\n"
                f"👥 Participantes: {total_participants}\n\n"
                f"📭 *Sin participantes hoy* 😢\n\n"
                f"¡Vuelve mañana a participar!"
            )
        else:
            # Formatear lista de ganadores
            winners_text = ""
            if len(winners) == 1:
                user_id, username = winners[0]
                winners_text = f"🏆 **Ganador**: @{username}"
            else:
                winners_names = ", ".join([f"@{name}" for _, name in winners])
                winners_text = f"🏆 **Ganadores**: {winners_names}"

            message = (
                f"📅 **RESULTADOS DEL DÍA**\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🎮 Palabra del día: #{wordle_id}\n"
                f"📆 Fecha: {date}\n"
                f"👥 Participantes: {total_participants}\n"
                f"⭐ Mejor score: {best_score}/6\n\n"
                f"{winners_text}\n\n"
                f"¡Felicidades! 🎉"
            )

        return message

    except Exception as e:
        logger.error(f"Error formateando anuncio diario: {e}", exc_info=True)
        return "❌ Error generando anuncio"


def format_weekly_announcement(result: Dict) -> str:
    """
    Formatea el anuncio de ganadores semanales
    
    Args:
        result: Diccionario con datos del ganador semanal
        
    Returns:
        Texto formateado para Telegram
    """
    try:
        date_range = result['date']
        week_start = result['week_start']
        week_end = result['week_end']
        winners = result['winners']
        best_avg = result['best_avg']
        total_participants = result['total_participants']
        games_processed = result['games_processed']

        if not winners:
            message = (
                f"📊 **RESULTADOS SEMANALES**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📆 Semana: {date_range}\n"
                f"🎮 Juegos: {games_processed}\n"
                f"👥 Participantes: {total_participants}\n\n"
                f"📭 *Sin suficientes datos esta semana* 😢"
            )
        else:
            # Formatear lista de ganadores
            if len(winners) == 1:
                user_id, username = winners[0]
                winners_text = f"🏆 **Campeón semanal**: @{username}"
            else:
                winners_names = ", ".join([f"@{name}" for _, name in winners])
                winners_text = f"🏆 **Campeones semanales**: {winners_names}"

            message = (
                f"📊 **RESULTADOS SEMANALES**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📆 Semana: {date_range}\n"
                f"🎮 Juegos analizados: {games_processed}\n"
                f"👥 Participantes totales: {total_participants}\n"
                f"📈 Mejor promedio: {best_avg:.2f}/6\n\n"
                f"{winners_text}\n\n"
                f"¡Excelente desempeño esta semana! 🌟"
            )

        return message

    except Exception as e:
        logger.error(f"Error formateando anuncio semanal: {e}", exc_info=True)
        return "❌ Error generando anuncio semanal"


def format_monthly_announcement(result: Dict) -> str:
    """
    Formatea el anuncio de ganadores mensuales
    
    Args:
        result: Diccionario con datos del ganador mensual
        
    Returns:
        Texto formateado para Telegram
    """
    try:
        date = result['date']
        month = result['month']
        year = result['year']
        winners = result['winners']
        best_avg = result['best_avg']
        total_participants = result['total_participants']
        games_processed = result['games_processed']

        # Nombre del mes en español
        months_es = {
            1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
            5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
            9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
        }
        month_name = months_es.get(month, "")

        if not winners:
            message = (
                f"🏅 **RESULTADOS MENSUALES**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📅 Mes: {month_name} {year}\n"
                f"🎮 Juegos: {games_processed}\n"
                f"👥 Participantes: {total_participants}\n\n"
                f"📭 *Sin suficientes datos este mes* 😢"
            )
        else:
            # Formatear lista de ganadores
            if len(winners) == 1:
                user_id, username = winners[0]
                winners_text = f"🥇 **Rey del mes**: @{username}"
            else:
                winners_names = ", ".join([f"@{name}" for _, name in winners])
                winners_text = f"🥇 **Reyes del mes**: {winners_names}"

            message = (
                f"🏅 **RESULTADOS MENSUALES**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📅 Mes: {month_name} {year}\n"
                f"🎮 Juegos analizados: {games_processed}\n"
                f"👥 Participantes totales: {total_participants}\n"
                f"📊 Mejor promedio: {best_avg:.2f}/6\n\n"
                f"{winners_text}\n\n"
                f"¡Fantástico desempeño durante el mes! 👑"
            )

        return message

    except Exception as e:
        logger.error(f"Error formateando anuncio mensual: {e}", exc_info=True)
        return "❌ Error generando anuncio mensual"


def format_yearly_announcement(result: Dict) -> str:
    """
    Formatea el anuncio de ganadores anuales
    
    Args:
        result: Diccionario con datos del ganador anual
        
    Returns:
        Texto formateado para Telegram
    """
    try:
        date = result['date']
        year = result['year']
        winners = result['winners']
        best_avg = result['best_avg']
        total_participants = result['total_participants']
        games_processed = result['games_processed']

        if not winners:
            message = (
                f"🎖️ **RESULTADOS ANUALES**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📅 Año: {year}\n"
                f"🎮 Juegos: {games_processed}\n"
                f"👥 Participantes: {total_participants}\n\n"
                f"📭 *Sin suficientes datos este año* 😢"
            )
        else:
            # Formatear lista de ganadores
            if len(winners) == 1:
                user_id, username = winners[0]
                winners_text = f"🏆 **Leyenda del año**: @{username}"
            else:
                winners_names = ", ".join([f"@{name}" for _, name in winners])
                winners_text = f"🏆 **Leyendas del año**: {winners_names}"

            message = (
                f"🎖️ **RESULTADOS ANUALES**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📅 Año: {year}\n"
                f"🎮 Juegos analizados: {games_processed}\n"
                f"👥 Participantes totales: {total_participants}\n"
                f"🌟 Mejor promedio: {best_avg:.2f}/6\n\n"
                f"{winners_text}\n\n"
                f"¡Eres una LEYENDA de Wordle! 🌟👑"
            )

        return message

    except Exception as e:
        logger.error(f"Error formateando anuncio anual: {e}", exc_info=True)
        return "❌ Error generando anuncio anual"


# ========================
# FORMATEO DE ESTADÍSTICAS
# ========================

def format_leaderboard(leaderboard: List[Dict]) -> str: # Cambiado el tipo de hint
    """
    Formatea el leaderboard de jugadores

    Args:
        leaderboard: Lista de diccionarios con estadísticas de jugadores

    Returns:
        Texto formateado para Telegram
    """
    try:
        if not leaderboard:
            return (
                "🏆 **TABLA DE LÍDERES**\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "📭 *Leaderboard vacío*\n\n"
                "¡Sé el primero en participar! 🚀"
            )

        message = "🏆 **TABLA DE LÍDERES TOP 10**\n"
        message += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        for idx, player_data in enumerate(leaderboard[:10], 1): # Cambiado aquí
            # Accedemos a los campos del diccionario
            user_id = player_data.get('user_id', 'N/A')
            username = player_data.get('username', 'Usuario')
            daily_wins = player_data.get('daily_wins', 0)
            weekly_wins = player_data.get('weekly_wins', 0)
            monthly_wins = player_data.get('monthly_wins', 0)
            yearly_wins = player_data.get('yearly_wins', 0)
            total_participations = player_data.get('total_games', 0) # Asumiendo que es total_games
            # average_attempts = player_data.get('average_attempts', 0) # No se devuelve actualmente

            # Medalla según posición
            if idx == 1:
                medal = "🥇"
            elif idx == 2:
                medal = "🥈"
            elif idx == 3:
                medal = "🥉"
            else:
                medal = f"#{idx}"

            # Calcular promedio (si se tuviera average_attempts en el futuro)
            # avg_attempts_val = average_attempts if average_attempts > 0 else 0
            avg_attempts_val = 0 # Placeholder por ahora

            message += (
                f"{medal} **@{username}**\n" # Asegúrate de manejar usernames sin @ si es necesario
                f"   🏅 Victorias diarias: {daily_wins}\n"
                f"   📊 Victorias semanales: {weekly_wins}\n"
                f"   📈 Victorias mensuales: {monthly_wins}\n"
                f"   🌟 Victorias anuales: {yearly_wins}\n"
                f"   🎮 Participaciones: {total_participations}\n"
                f"   📉 Promedio: {avg_attempts_val:.2f}/6\n\n" # Mostrará 0.00 por ahora
            )

        return message

    except Exception as e:
        logger.error(f"Error formateando leaderboard: {e}", exc_info=True)
        return "❌ Error generando leaderboard"

def format_player_stats(user_id: str, stats: Dict) -> str:
    """
    Formatea las estadísticas de un jugador
    
    Args:
        user_id: ID del usuario
        stats: Diccionario de estadísticas
        
    Returns:
        Texto formateado para Telegram
    """
    try:
        username = stats.get('username', 'Usuario')
        daily_wins = stats.get('daily_wins', 0)
        weekly_wins = stats.get('weekly_wins', 0)
        monthly_wins = stats.get('monthly_wins', 0)
        yearly_wins = stats.get('yearly_wins', 0)
        total_participations = stats.get('total_participations', 0)
        average_attempts = stats.get('average_attempts', 0)
        best_score = stats.get('best_score', None)
        worst_score = stats.get('worst_score', None)

        message = f"📊 **ESTADÍSTICAS DE @{username}**\n"
        message += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        message += f"🏅 *Victorias*\n"
        message += f"   🎯 Diarias: {daily_wins}\n"
        message += f"   📅 Semanales: {weekly_wins}\n"
        message += f"   📆 Mensuales: {monthly_wins}\n"
        message += f"   🌍 Anuales: {yearly_wins}\n\n"

        message += f"📈 *Desempeño*\n"
        message += f"   🎮 Participaciones: {total_participations}\n"
        message += f"   📊 Promedio de intentos: {average_attempts:.2f}/6\n"

        if best_score:
            message += f"   🌟 Mejor score: {best_score}/6\n"

        if worst_score:
            message += f"   📉 Peor score: {worst_score}/6\n"

        # Porcentaje de victorias
        if total_participations > 0:
            win_rate = (daily_wins / total_participations) * 100
            message += f"\n   🎯 Tasa de victorias: {win_rate:.1f}%\n"

        return message

    except Exception as e:
        logger.error(f"Error formateando stats: {e}", exc_info=True)
        return "❌ Error generando estadísticas"


# ========================
# FUNCIONES AUXILIARES
# ========================

def get_days_until_next_announcement(announcement_type: str) -> int:
    """
    Calcula días hasta el próximo anuncio
    
    Args:
        announcement_type: 'daily', 'weekly', 'monthly', 'yearly'
        
    Returns:
        Número de días
    """
    try:
        today = datetime.now(config.TIMEZONE).date()

        if announcement_type == 'daily':
            return 0  # Cada día

        elif announcement_type == 'weekly':
            # Próximo domingo
            days_until_sunday = (6 - today.weekday()) % 7
            return days_until_sunday if days_until_sunday > 0 else 7

        elif announcement_type == 'monthly':
            # Último día del mes
            if today.month == 12:
                next_month = today.replace(year=today.year + 1, month=1, day=1)
            else:
                next_month = today.replace(month=today.month + 1, day=1)
            last_day = next_month - timedelta(days=1)
            return (last_day - today).days

        elif announcement_type == 'yearly':
            # 31 de diciembre
            end_of_year = today.replace(month=12, day=31)
            return (end_of_year - today).days

        return 0

    except Exception as e:
        logger.warning(f"Error calculando días: {e}")
        return 0


def format_time_remaining(days: int) -> str:
    """
    Formatea tiempo restante de forma legible
    
    Args:
        days: Número de días
        
    Returns:
        Texto formateado
    """
    try:
        if days == 0:
            return "hoy"
        elif days == 1:
            return "mañana"
        else:
            return f"en {days} días"

    except Exception as e:
        logger.warning(f"Error formateando tiempo: {e}")
        return "próximamente"


def calculate_average_attempts(attempts_list: List[int]) -> float:
    """
    Calcula el promedio de intentos
    
    Args:
        attempts_list: Lista de intentos
        
    Returns:
        Promedio
    """
    try:
        if not attempts_list:
            return 0.0

        return sum(attempts_list) / len(attempts_list)

    except Exception as e:
        logger.warning(f"Error calculando promedio: {e}")
        return 0.0


def get_emoji_for_score(attempts: int) -> str:
    """
    Devuelve un emoji basado en el score
    
    Args:
        attempts: Número de intentos (1-6)
        
    Returns:
        Emoji apropiado
    """
    emoji_map = {
        1: "🌟",  # Perfecto
        2: "⭐",  # Excelente
        3: "✨",  # Muy bueno
        4: "👍",  # Bueno
        5: "🤔",  # Pasable
        6: "😅",  # Justo
    }
    return emoji_map.get(attempts, "❓")