import os
import asyncio
import logging
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv
from replicator import TelegramReplicator
from config import REPLICATION_MAP

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
        logging.FileHandler("history_sender_v2.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("HistorySenderV2")

load_dotenv()

# --- CREDENCIALES ---
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
SESSION_STRING = os.getenv('SESSION_STRING')

async def send_filtered_history(limit_per_group=50):
    """
    Recupera los últimos mensajes del historial, aplica los filtros oficiales
    de TelegramReplicator (incluyendo IA y traducción) y los envía.
    """
    logger.info(f"Iniciando envío de historial (últimos {limit_per_group} mensajes) con FILTROS e IA...")
    
    if not API_ID or not API_HASH or not SESSION_STRING:
        logger.error("Credenciales incompletas en el archivo .env")
        return

    client = TelegramClient(StringSession(SESSION_STRING), int(API_ID), API_HASH)
    
    try:
        await client.start()
        logger.info("Conexión con Telegram establecida.")

        # Instanciamos el replicador oficial para usar su lógica de procesamiento completa
        replicator = TelegramReplicator(client, REPLICATION_MAP)

        for s_id, cfg in REPLICATION_MAP.items():
            name = cfg['name']
            priority = cfg['priority']
            
            logger.info(f"--- Procesando historial de: {name} (Source: {s_id}) ---")
            
            try:
                # 1. Recuperar historial
                messages = await client.get_messages(s_id, limit=limit_per_group)
                if not messages:
                    logger.info(f"No se encontraron mensajes en {name}")
                    continue

                logger.info(f"Encontrados {len(messages)} mensajes. Procesando de más antiguo a más reciente...")

                # Procesar de más viejo a más nuevo
                for msg in reversed(messages):
                    if not msg.text:
                        continue

                    # Usamos el pipeline oficial del replicador
                    # process_message maneja Hard -> Logical -> AI -> Publish -> DB
                    await replicator.process_message(msg, priority, cfg)
                    
                    # Pequeño delay para no saturar la API de IA ni Telegram
                    await asyncio.sleep(3) 
            
            except Exception as e:
                logger.error(f"Error procesando grupo {name}: {e}")
                continue

        logger.info("Proceso de envío de historial completado.")

    except Exception as e:
        logger.error(f"Error general en el cliente: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(send_filtered_history(50))
