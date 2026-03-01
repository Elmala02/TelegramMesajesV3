import os
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv

load_dotenv()

API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
SESSION_STRING = os.getenv('SESSION_STRING')

async def check():
    client = TelegramClient(StringSession(SESSION_STRING), int(API_ID), API_HASH)
    await client.start()
    
    ids_to_check = [-3737486306, -3807690832, -1003737486306, -1003807690832]
    
    for tid in ids_to_check:
        try:
            entity = await client.get_entity(tid)
            print(f"ID {tid}: ✅ OK ({getattr(entity, 'title', 'No Title')}) type: {type(entity).__name__}")
        except Exception as e:
            print(f"ID {tid}: ❌ ERROR: {e}")
    
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(check())
