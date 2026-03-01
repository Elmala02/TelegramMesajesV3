import os
import asyncio
import logging
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv
from replicator import TelegramReplicator
from config import REPLICATION_MAP
import message_cache

# --- CONFIGURACIÓN DE LOGGING ---
# Forzar encoding UTF-8 para evitar UnicodeEncodeError en Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_execution.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("MainBot")

load_dotenv()

API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
SESSION_STRING = os.getenv('SESSION_STRING')

async def main():
    if not API_ID or not API_HASH or not SESSION_STRING:
        logger.error("Error: Credenciales incompletas (API_ID, API_HASH o SESSION_STRING) en el archivo .env")
        return

    logger.info("--- Iniciando Sistema Multi-Source CLUB 10M ---")
    logger.info(f"Configuraciones Cargadas: {len(REPLICATION_MAP)}")
    for sid, configs in REPLICATION_MAP.items():
        if not isinstance(configs, list): configs = [configs]
        for cfg in configs:
            logger.info(f" - Origen: {cfg['name']} ({sid}) -> Destino: {cfg['dest']} (Topic: {cfg.get('topic', 'N/A')})")
    
    try:
        logger.info("Conectando con Telegram...")
        client = TelegramClient(StringSession(SESSION_STRING), int(API_ID), API_HASH)
        await client.start()
        logger.info("Sesión iniciada con éxito.")
        
        # Inicializar Cache de Ediciones
        message_cache.load_cache()
        asyncio.create_task(message_cache.cache_cleaner_loop())
        logger.info("Caché de mensajes y loop de limpieza (600s) iniciados.")
        
        replicator = TelegramReplicator(client, REPLICATION_MAP)
        logger.info("Replicador inicializado. Escuchando nuevos mensajes...")
        await replicator.start()
        
    except Exception as e:
        logger.error(f"Error fatal durante la ejecución: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Servicio detenido por el usuario.")
    except Exception as e:
        logger.critical(f"Error inesperado en el punto de entrada: {e}")
