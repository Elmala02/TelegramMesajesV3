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
        
        # Resolver explícitamente cada entidad destino del REPLICATION_MAP
        # Esto garantiza que Telethon las reconozca aunque la sesión sea antigua
        logger.info("Resolviendo entidades de destino del REPLICATION_MAP...")
        dest_ids = set()
        for configs in REPLICATION_MAP.values():
            cfg_list = configs if isinstance(configs, list) else [configs]
            for cfg in cfg_list:
                dest_ids.add(cfg['dest'])
        
        for dest_id in dest_ids:
            try:
                entity = await client.get_entity(dest_id)
                title = getattr(entity, 'title', str(dest_id))
                logger.info(f"  ✓ Entidad resuelta: {dest_id} -> '{title}'")
            except Exception as e:
                logger.warning(f"  ✗ No se pudo resolver entidad {dest_id}: {e}")
        
        logger.info("Resolución de entidades completada.")
        
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
