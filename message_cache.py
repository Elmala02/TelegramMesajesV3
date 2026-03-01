import json
import time
import os
import asyncio
import logging

# Configurar logging para este módulo
logger = logging.getLogger(__name__)

CACHE_FILE = "messages_cache.json"
EXPIRATION_TIME = 600  # 10 minutos (600 segundos)
CLEANUP_INTERVAL = 60  # 60 segundos

# El cache almacena: { original_msg_id: [ {"replicated_id": id, "chat_id": id, "timestamp": ts}, ... ] }
_cache = {}

def load_cache():
    """Carga el cache desde el archivo JSON si existe."""
    global _cache
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding='utf-8') as f:
                data = json.load(f)
                # JSON serializa keys como strings, convertir de vuelta a int
                _cache = {int(k): v for k, v in data.items()}
                logger.info(f"💾 Cache cargado desde JSON: {len(_cache)} mensajes registrados.")
        except Exception as e:
            logger.error(f"❌ Error al cargar messages_cache.json: {e}")
            _cache = {}
    else:
        logger.info("ℹ️ No se encontró messages_cache.json, iniciando cache vacío.")
        _cache = {}

def save_cache():
    """Guarda el estado actual del cache en el archivo JSON."""
    try:
        with open(CACHE_FILE, "w", encoding='utf-8') as f:
            json.dump(_cache, f)
    except Exception as e:
        logger.error(f"❌ Error al guardar cache en JSON: {e}")

def add_message(original_id, replicated_msg_obj):
    """
    Agrega un mapeo de mensaje replicado al cache.
    replicated_msg_obj es el objeto mensaje devuelto por client.send_message.
    """
    orig_id = int(original_id)
    if orig_id not in _cache:
        _cache[orig_id] = []
    
    _cache[orig_id].append({
        "replicated_id": int(replicated_msg_obj.id),
        "chat_id": int(replicated_msg_obj.chat_id),
        "timestamp": time.time()
    })
    # Nota: No guardamos el JSON aquí para mantener eficiencia.

def get_message(original_id):
    """Retorna la lista de mapeos para un mensaje original si existe en cache."""
    return _cache.get(int(original_id))

def clean_cache():
    """Limpia los mensajes que han superado el tiempo de expiración."""
    global _cache
    now = time.time()
    initial_count = len(_cache)
    
    new_cache = {}
    for orig_id, mappings in _cache.items():
        # Mantener solo los mapeos que no han expirado (600 segundos)
        valid_mappings = [m for m in mappings if now - m["timestamp"] < EXPIRATION_TIME]
        if valid_mappings:
            new_cache[orig_id] = valid_mappings
            
    _cache = new_cache
    
    if initial_count != len(_cache):
        logger.info(f"🧹 Limpieza de cache completada. {initial_count - len(_cache)} entradas eliminadas.")
        save_cache()

async def cache_cleaner_loop():
    """Bucle asíncrono que ejecuta la limpieza periódica cada minuto."""
    logger.info("🕒 Proceso de limpieza automática de cache iniciado.")
    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL)
            clean_cache()
        except asyncio.CancelledError:
            # Intentar guardar al cancelar la tarea
            save_cache()
            break
        except Exception as e:
            logger.error(f"❌ Error en cache_cleaner_loop: {e}")
