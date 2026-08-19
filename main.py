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
        
        # Resolver explícitamente entidades de origen y destino del REPLICATION_MAP
        logger.info("Resolviendo entidades de origen y destino del REPLICATION_MAP...")
        from telethon.utils import get_peer_id
        
        resolved_replication_map = {}
        for source_key, configs in REPLICATION_MAP.items():
            cfg_list = configs if isinstance(configs, list) else [configs]
            resolved_source_id = source_key
            try:
                source_entity = await client.get_entity(source_key)
                resolved_source_id = get_peer_id(source_entity)
                title = getattr(source_entity, 'title', str(source_key))
                logger.info(f"  ✓ Origen resuelto: {source_key} -> {resolved_source_id} ('{title}')")
            except Exception as e:
                logger.warning(f"  ✗ No se pudo resolver entidad origen {source_key}: {e}")

            resolved_cfgs = []
            for cfg in cfg_list:
                cfg_copy = dict(cfg)
                dest_val = cfg_copy.get('dest')
                try:
                    dest_entity = await client.get_entity(dest_val)
                    resolved_dest_id = get_peer_id(dest_entity)
                    cfg_copy['dest'] = resolved_dest_id
                    title = getattr(dest_entity, 'title', str(dest_val))
                    logger.info(f"  ✓ Destino resuelto: {dest_val} -> {resolved_dest_id} ('{title}')")
                except Exception as e:
                    logger.warning(f"  ✗ No se pudo resolver entidad destino {dest_val}: {e}")
                resolved_cfgs.append(cfg_copy)

            resolved_replication_map[resolved_source_id] = resolved_cfgs
            if resolved_source_id != source_key:
                resolved_replication_map[source_key] = resolved_cfgs
        
        logger.info("Resolución de entidades completada.")
        
        # Inicializar Cache de Ediciones
        message_cache.load_cache()
        asyncio.create_task(message_cache.cache_cleaner_loop())
        logger.info("Caché de mensajes y loop de limpieza (600s) iniciados.")
        
        replicator = TelegramReplicator(client, resolved_replication_map)
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
