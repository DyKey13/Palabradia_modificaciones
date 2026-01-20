import pytz
from datetime import time
import os
from dotenv import load_dotenv
import logging

# Cargar variables de entorno
load_dotenv()

# Token de Telegram (obligatorio)
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("❌ ERROR: TELEGRAM_BOT_TOKEN no encontrado en .env")

# Configuración del grupo (se puede detectar automáticamente o poner manual)
GRUPO_ID = os.getenv('GRUPO_ID')
if GRUPO_ID:
    GRUPO_ID = int(GRUPO_ID)

# Zona horaria
TIMEZONE = pytz.timezone('America/Caracas')

# Horarios configurados
DAILY_ANNOUNCE_TIME = time(19, 0, 0)      # 7:00 PM
WEEKLY_ANNOUNCE_TIME = time(20, 0, 0)     # 8:00 PM (domingos)
MONTHLY_ANNOUNCE_TIME = time(20, 0, 0)    # 8:00 PM (último día del mes)
YEARLY_ANNOUNCE_TIME = time(20, 0, 0)     # 8:00 PM (31 de diciembre)
DAILY_CLEANUP_TIME = time(0, 0, 0)        # 12:00 AM

# Configuración del juego
MIN_PARTICIPANTS_FOR_ANNOUNCE = 5
MAX_ATTEMPTS = 6
WORDLE_START_DATE = (2022, 1, 7)  # Wordle #1

# Rutas de archivos
DATA_DIR = 'data'
DATA_FILE = os.path.join(DATA_DIR, 'wordle_data.json')

# Crear directorio si no existe
os.makedirs(DATA_DIR, exist_ok=True)

# Configuración de logging mejorada
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,  # Cambiado a INFO para mejor debugging
    handlers=[
        logging.FileHandler(os.path.join(DATA_DIR, 'bot.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Lista de administradores (agregar IDs para funciones admin)
ADMIN_IDS = []