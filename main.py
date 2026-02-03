import os
import asyncio
import logging
from telethon import TelegramClient
from dotenv import load_dotenv
from replicator import TelegramReplicator

# Load environment variables
load_dotenv()

API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
SESSION_NAME = os.getenv('SESSION_NAME', 'replicator_session')
DEST_CHANNEL = os.getenv('DESTINATION_CHANNEL_ID')

# --- SOURCE CONFIGURATION (ID -> Priority) ---
# 1 = Highest, 4 = Lowest
SOURCE_MAP = {
    -1002148227049: 1,  # GTS VIP
    -1002310215234: 2,  # 44's Clup
    -1002108856565: 3,  # Gold Trader Sunny
    -1003020297428: 4,  # FXKINGS SIGNALS
    -1003759405936: 5   # Test Channel (New)
}

def parse_channel_id(val):
    if not val: return None
    try:
        return int(val)
    except ValueError:
        return val

async def main():
    if not API_ID or not API_HASH:
        print("Error: API_ID and API_HASH missing in .env")
        return

    if not DEST_CHANNEL:
        print("Error: DESTINATION_CHANNEL_ID must be set in .env")
        return

    dst = parse_channel_id(DEST_CHANNEL)

    print("Starting Antigraviti Multi-Source System...")
    print(f"Sources Configured: {len(SOURCE_MAP)}")
    for sid, prio in SOURCE_MAP.items():
        print(f" - Source {sid}: Priority {prio}")
    
    from telethon.sessions import StringSession
    
    # Check for String Session (Vercel/Cloud)
    SESSION_STRING = os.getenv('SESSION_STRING')
    
    if SESSION_STRING:
        print("Using Session String from Environment...")
        client = TelegramClient(StringSession(SESSION_STRING), int(API_ID), API_HASH)
    else:
        print(f"Using File Session '{SESSION_NAME}'...")
        client = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)
    
    await client.start()
    
    replicator = TelegramReplicator(client, SOURCE_MAP, dst)
    await replicator.start()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nService stopped by user.")
    except Exception as e:
        print(f"\nFatal error: {e}")
