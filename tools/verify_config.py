import os
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import ChannelParticipantAdmin, ChannelParticipantCreator
from dotenv import load_dotenv

load_dotenv()

API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
SESSION_STRING = os.getenv('SESSION_STRING')
SESSION_NAME = os.getenv('SESSION_NAME', 'replicator_session')

from config import REPLICATION_MAP

async def verify_permissions():
    if not API_ID or not API_HASH:
        print("Error: API_ID or API_HASH missing")
        return

    if SESSION_STRING:
        client = TelegramClient(StringSession(SESSION_STRING), int(API_ID), API_HASH)
    else:
        client = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)

    await client.start()
    
    print("\n" + "="*50)
    print("REPORTE DE VERIFICACIÓN DE GRUPOS")
    print("="*50 + "\n")

    me = await client.get_me()
    print(f"Usuario: {me.first_name} (@{me.username})\n")

    results = []
    
    # Get all unique destination IDs
    dest_ids = set()
    for configs in REPLICATION_MAP.values():
        if not isinstance(configs, list): configs = [configs]
        for cfg in configs:
            dest_ids.add(cfg['dest'])
    
    print("--- Verificando Destinos ---")
    dest_status = {}
    for d_id in dest_ids:
        try:
            entity = await client.get_entity(d_id)
            print(f"✅ Destino {d_id} encontrado: {entity.title}")
            dest_status[d_id] = True
        except Exception as e:
            print(f"❌ Destino {d_id} ERROR: {e}")
            dest_status[d_id] = False

    print("\n--- Verificando Pares Origen-Destino ---")
    for s_id, configs in REPLICATION_MAP.items():
        if not isinstance(configs, list): configs = [configs]
        for cfg in configs:
            name = cfg['name']
            d_id = cfg['dest']
            topic = cfg.get('topic', 'N/A')
            
            status_src = "PENDIENTE"
            status_dst = "PENDIENTE"
            
            # Check Source
            try:
                src_entity = await client.get_entity(s_id)
                status_src = f"✅ OK ({src_entity.title})"
            except Exception as e:
                status_src = f"❌ ERROR: {e}"
                
            # Check Destination
            if dest_status.get(d_id):
                status_dst = f"✅ OK (Topic {topic})"
            else:
                status_dst = f"❌ ERROR en Canal Destino"
                
            print(f"Par: {name}")
            print(f"  - Origen ({s_id}): {status_src}")
            print(f"  - Destino ({d_id}): {status_dst}")
            print("-" * 30)

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(verify_permissions())
