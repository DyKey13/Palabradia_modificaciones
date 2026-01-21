import json
import os
from datetime import datetime, date, timedelta
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Any
import config

class GameData:
    """Maneja todos los datos del juego con mejor error handling"""
    
    def __init__(self, data_file=None):
        self.data_file = data_file or config.DATA_FILE
        self.daily_games: Dict[str, Dict] = {}
        self.player_stats: Dict[str, Dict] = defaultdict(self._default_player_stats)
        self.load_data()
    
    def _default_player_stats(self):
        return {
            'username': '',
            'daily_wins': 0,
            'weekly_wins': 0,
            'monthly_wins': 0,
            'yearly_wins': 0,
            'total_games': 0,
            'best_score': config.MAX_ATTEMPTS + 1,
            'participations': {},
            'first_seen': None
        }
    
    def load_data(self):
        """Carga datos desde archivo JSON con mejor manejo de errores"""
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.daily_games = data.get('daily_games', {})
                stats = data.get('player_stats', {})
                for key, value in stats.items():
                    self.player_stats[key] = value
                config.logger.info("Datos cargados correctamente") # Quitado el emoji
        except FileNotFoundError:
            config.logger.info("📂 Creando nuevo archivo de datos")
            self.save_data()
        except json.JSONDecodeError as e:
            config.logger.error(f"❌ Error decodificando JSON: {e}. Creando respaldo.")
            self._backup_corrupted_file()
            self.save_data()
        except Exception as e:
            config.logger.error(f"❌ Error inesperado cargando datos: {e}")
            self.save_data()
    
    def _backup_corrupted_file(self):
        """Crea respaldo del archivo corrupto"""
        try:
            backup_file = self.data_file + f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            if os.path.exists(self.data_file):
                os.rename(self.data_file, backup_file)
                config.logger.info(f"📦 Respaldo creado: {backup_file}")
        except Exception as e:
            config.logger.error(f"Error creando respaldo: {e}")
    
    def save_data(self):
        """Guarda datos a archivo JSON con validación"""
        try:
            data = {
                'daily_games': self.daily_games,
                'player_stats': dict(self.player_stats),
                'last_updated': datetime.now(config.TIMEZONE).isoformat()
            }
            
            # Usar archivo temporal para evitar corrupción
            temp_file = self.data_file + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Reemplazar archivo original
            if os.path.exists(self.data_file):
                os.remove(self.data_file)
            os.rename(temp_file, self.data_file)
            config.logger.debug("✅ Datos guardados exitosamente")
        except Exception as e:
            config.logger.error(f"❌ Error guardando datos: {e}")
    
    def get_current_date_str(self) -> str:
        """Fecha actual en formato YYYY-MM-DD"""
        return datetime.now(config.TIMEZONE).strftime('%Y-%m-%d')
    
    def get_current_wordle_id(self) -> int:
        """Calcula el Wordle ID actual"""
        start_date = date(*config.WORDLE_START_DATE)
        current_date = datetime.now(config.TIMEZONE).date()
        days_diff = (current_date - start_date).days
        return days_diff + 1
    
    def register_participation(self, user_id: str, username: str, wordle_id: int, attempts: int) -> Tuple[bool, str]:
        """Registra una participación con validación mejorada"""
        try:
            # Validar entrada
            if not user_id or not username:
                return False, "❌ Datos inválidos"
            
            # Si el jugador falló todos los intentos
            if attempts > config.MAX_ATTEMPTS:
                attempts = 7
            
            today = self.get_current_date_str()
            current_id = self.get_current_wordle_id()
            
            if wordle_id != current_id:
                return False, f"⚠️ Este Wordle (#{wordle_id}) no es el de hoy. Hoy es el Wordle #{current_id}."
            
            # --- CORRECCIÓN CRÍTICA AQUÍ ---
            # Verificar hora límite — ¡SIEMPRE rechazar después de las 7 PM!
            now = datetime.now(config.TIMEZONE)
            cutoff = datetime.combine(now.date(), config.DAILY_ANNOUNCE_TIME)
            cutoff = config.TIMEZONE.localize(cutoff)

            if now >= cutoff:
                return False, "⏰ La hora límite para participar hoy ya pasó (7:00 PM)."
            # --- FIN CORRECCIÓN ---

            # Inicializar día si no existe
            if today not in self.daily_games:
                self.daily_games[today] = {
                    'wordle_id': wordle_id,
                    'participants': {},
                    'winners': [],
                    'announced': False,
                    'announce_time': None,
                    'announce_reason': None
                }
            
            daily_game = self.daily_games[today]
            
            # Verificar si ya participó
            if user_id in daily_game['participants']:
                prev = daily_game['participants'][user_id]['attempts']
                return False, f"✅ Ya registré tu participación de hoy ({prev}/6)."
            
            # Registrar
            daily_game['participants'][user_id] = {
                'username': username,
                'attempts': attempts,
                'timestamp': now.isoformat()
            }
            
            # Actualizar estadísticas
            if user_id not in self.player_stats:
                self.player_stats[user_id] = self._default_player_stats()
            
            stats = self.player_stats[user_id]
            stats['username'] = username
            stats['total_games'] += 1
            stats['best_score'] = min(stats['best_score'], attempts)
            stats['participations'][today] = attempts
            
            if not stats['first_seen']:
                stats['first_seen'] = today
            
            self.save_data()
            return True, f"✅ ¡Participación registrada, {username}! Wordle #{wordle_id} en {attempts}/6 intentos."
        
        except Exception as e:
            config.logger.error(f"Error en register_participation: {e}")
            return False, "❌ Error al registrar participación"
    
    def check_and_get_daily_winners(self, date_str: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Determina ganadores del día con validación"""
        try:
            if date_str is None:
                date_str = self.get_current_date_str()
            
            if date_str not in self.daily_games:
                return None
            
            daily_game = self.daily_games[date_str]
            
            # Si ya se anunció, no hacer nada
            if daily_game.get('announced', False):
                return None
            
            participants = daily_game['participants']
            
            # Condición 1: Al menos 5 participantes
            has_min_participants = len(participants) >= config.MIN_PARTICIPANTS_FOR_ANNOUNCE
            
            # Condición 2: Es después de las 7 PM
            now = datetime.now(config.TIMEZONE)
            cutoff = datetime.combine(now.date(), config.DAILY_ANNOUNCE_TIME)
            cutoff = config.TIMEZONE.localize(cutoff)
            is_after_cutoff = now >= cutoff
            
            # Anunciar solo si se cumple alguna condición
            if not (has_min_participants or is_after_cutoff):
                return None
            
            # Determinar ganadores
            winners = []
            best_score = config.MAX_ATTEMPTS + 1
            
            if participants:
                best_score = min(p['attempts'] for p in participants.values())
                winners = [
                    (user_id, data['username'])
                    for user_id, data in participants.items()
                    if data['attempts'] == best_score
                ]
            
            # Preparar resultado
            result = {
                'date': date_str,
                'wordle_id': daily_game['wordle_id'],
                'winners': winners,
                'best_score': best_score if participants else None,
                'total_participants': len(participants),
                'reason': 'min_participants' if has_min_participants and not is_after_cutoff else 'time_cutoff',
                'announce_time': now.isoformat(),
                'has_participants': bool(participants)
            }
            
            # Actualizar datos
            daily_game['winners'] = winners
            daily_game['announced'] = True
            daily_game['announce_time'] = now.isoformat()
            daily_game['announce_reason'] = result['reason']
            
            # Actualizar estadísticas de ganadores
            for user_id, _ in winners:
                if user_id in self.player_stats:
                    self.player_stats[user_id]['daily_wins'] += 1
            
            self.save_data()
            return result
        
        except Exception as e:
            config.logger.error(f"Error en check_and_get_daily_winners: {e}")
            return None
    
    def get_weekly_winners(self) -> Optional[Dict[str, Any]]:
        """Calcula ganadores semanales con mejor lógica"""
        try:
            today = datetime.now(config.TIMEZONE)
            start_of_week = today - timedelta(days=today.weekday())
            start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
            
            week_winners = []
            week_participants = set()
            
            for date_str, game in self.daily_games.items():
                try:
                    game_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    game_datetime = datetime.combine(game_date, datetime.min.time())
                    game_datetime = config.TIMEZONE.localize(game_datetime)
                    
                    if game_datetime >= start_of_week and game.get('winners'):
                        week_winners.extend(game['winners'])
                        week_participants.update(game['participants'].keys())
                except ValueError:
                    config.logger.warning(f"Formato de fecha inválido: {date_str}")
                    continue
            
            if not week_winners:
                return None
            
            # Contar victorias por jugador
            win_counts = defaultdict(int)
            for user_id, _ in week_winners:
                win_counts[user_id] += 1
            
            max_wins = max(win_counts.values()) if win_counts else 0
            
            weekly_winners = []
            for user_id, wins in win_counts.items():
                if wins == max_wins:
                    stats = self.player_stats[user_id]
                    weekly_winners.append({
                        'user_id': user_id,
                        'username': stats['username'] or f"Usuario_{user_id[:6]}",
                        'wins': wins
                    })
            
            # Actualizar estadísticas
            for winner in weekly_winners:
                self.player_stats[winner['user_id']]['weekly_wins'] += 1
            
            self.save_data()
            
            return {
                'period': 'weekly',
                'start_date': start_of_week.strftime('%Y%m%d'),
                'end_date': today.strftime('%Y%m%d'),
                'winners': weekly_winners,
                'max_wins': max_wins,
                'total_participants': len(week_participants),
                'total_games': len(week_winners)
            }
        except Exception as e:
            config.logger.error(f"Error en get_weekly_winners: {e}")
            return None
    
    def get_monthly_winners(self) -> Optional[Dict[str, Any]]:
        """Calcula ganadores mensuales"""
        try:
            today = datetime.now(config.TIMEZONE)
            month_str = today.strftime('%Y-%m')
            month_winners = []
            month_participants = set()
            
            for date_str, game in self.daily_games.items():
                if date_str.startswith(month_str) and game.get('winners'):
                    month_winners.extend(game['winners'])
                    month_participants.update(game['participants'].keys())
            
            if not month_winners:
                return None
            
            win_counts = defaultdict(int)
            for user_id, _ in month_winners:
                win_counts[user_id] += 1
            
            max_wins = max(win_counts.values()) if win_counts else 0
            
            monthly_winners = []
            for user_id, wins in win_counts.items():
                if wins == max_wins:
                    stats = self.player_stats[user_id]
                    monthly_winners.append({
                        'user_id': user_id,
                        'username': stats['username'] or f"Usuario_{user_id[:6]}",
                        'wins': wins
                    })
            
            for winner in monthly_winners:
                self.player_stats[winner['user_id']]['monthly_wins'] += 1
            
            self.save_data()
            
            return {
                'period': 'monthly',
                'month': month_str,
                'month_name': today.strftime('%B'),
                'winners': monthly_winners,
                'max_wins': max_wins,
                'total_participants': len(month_participants),
                'total_games': len(month_winners)
            }
        except Exception as e:
            config.logger.error(f"Error en get_monthly_winners: {e}")
            return None
    
    def get_yearly_winners(self) -> Optional[Dict[str, Any]]:
        """Calcula ganadores anuales"""
        try:
            today = datetime.now(config.TIMEZONE)
            year_str = today.strftime('%Y')
            year_winners = []
            year_participants = set()
            
            for date_str, game in self.daily_games.items():
                if date_str.startswith(year_str) and game.get('winners'):
                    year_winners.extend(game['winners'])
                    year_participants.update(game['participants'].keys())
            
            if not year_winners:
                return None
            
            win_counts = defaultdict(int)
            for user_id, _ in year_winners:
                win_counts[user_id] += 1
            
            max_wins = max(win_counts.values()) if win_counts else 0
            
            yearly_winners = []
            for user_id, wins in win_counts.items():
                if wins == max_wins:
                    stats = self.player_stats[user_id]
                    yearly_winners.append({
                        'user_id': user_id,
                        'username': stats['username'] or f"Usuario_{user_id[:6]}",
                        'wins': wins
                    })
            
            for winner in yearly_winners:
                self.player_stats[winner['user_id']]['yearly_wins'] += 1
            
            self.save_data()
            
            return {
                'period': 'yearly',
                'year': year_str,
                'winners': yearly_winners,
                'max_wins': max_wins,
                'total_participants': len(year_participants),
                'total_games': len(year_winners)
            }
        except Exception as e:
            config.logger.error(f"Error en get_yearly_winners: {e}")
            return None
    
    def get_today_status(self) -> Dict[str, Any]:
        """Obtiene el estado del juego de hoy"""
        today = self.get_current_date_str()
        
        # Asegurarse de que today existe en daily_games
        if today not in self.daily_games:
            # Si no existe, crear una entrada vacía para hoy
            # Esto evita errores si se consulta antes de que alguien participe
            self.daily_games[today] = {
                'wordle_id': self.get_current_wordle_id(),
                'participants': {},
                'winners': [],
                'announced': False,
                'announce_time': None,
                'announce_reason': None
            }

        daily_game = self.daily_games[today]
        participants = daily_game['participants']

        # Ordenar participantes por intentos y luego por timestamp
        sorted_parts = sorted(
            participants.items(),
            key=lambda x: (x[1]['attempts'], x[1]['timestamp'])
        )[:5]

        # Asegurarse de que 'total_participants' es un entero
        total_participants = len(participants)

        return {
            'has_game': True, # Si llegó aquí, el día existe
            'wordle_id': daily_game['wordle_id'],
            'total_participants': total_participants,
            'announced': daily_game.get('announced', False),
            'top_participants': [
                {'username': data['username'], 'attempts': data['attempts']}
                for _, data in sorted_parts
            ],
            'winners': daily_game.get('winners', []) # Asegurarse de que sea una lista
        }
    
    def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Obtiene la tabla de líderes ordenada"""
        active_players = []
        
        for user_id, stats in self.player_stats.items():
            if stats['total_games'] > 0:
                active_players.append({
                    'user_id': user_id,
                    'username': stats['username'] or f"Usuario_{user_id[:6]}",
                    'daily_wins': stats['daily_wins'],
                    'best_score': stats['best_score'],
                    'total_games': stats['total_games'],
                    'weekly_wins': stats['weekly_wins'],
                    'monthly_wins': stats['monthly_wins']
                })
        
        active_players.sort(key=lambda x: (-x['daily_wins'], x['best_score']))
        return active_players[:limit]
    
    def get_player_stats(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene estadísticas de un jugador"""
        if user_id not in self.player_stats:
            return None
        
        stats = self.player_stats[user_id]
        leaderboard = self.get_leaderboard(limit=1000)
        rank = next((i+1 for i, p in enumerate(leaderboard) if p['user_id'] == user_id), len(leaderboard) + 1)
        
        return {
            'username': stats['username'],
            'daily_wins': stats['daily_wins'],
            'weekly_wins': stats['weekly_wins'],
            'monthly_wins': stats['monthly_wins'],
            'yearly_wins': stats['yearly_wins'],
            'total_games': stats['total_games'],
            'best_score': stats['best_score'],
            'participations': len(stats['participations']),
            'first_seen': stats['first_seen'],
            'rank': rank,
            'total_players': len(leaderboard)
        }

import os
game_data = GameData()