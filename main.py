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
SOURCE_CHANNEL = os.getenv('SOURCE_CHANNEL_ID')
DEST_CHANNEL = os.getenv('DESTINATION_CHANNEL_ID')

def parse_channel_id(val):
    """Helper to convert string IDs to integers if they look like numbers."""
    if not val:
        return None
    try:
        return int(val)
    except ValueError:
        return val  # Return as string (username)

async def main():
    if not API_ID or not API_HASH:
        print("Error: API_ID and API_HASH missing in .env")
        return

    if not SOURCE_CHANNEL or not DEST_CHANNEL:
        print("Error: SOURCE_CHANNEL_ID and DESTINATION_CHANNEL_ID must be set in .env")
        return

    # Convert IDs if needed
    src = parse_channel_id(SOURCE_CHANNEL)
    dst = parse_channel_id(DEST_CHANNEL)

    print("Starting Telegram Replicator Service...")
    
    # Initialize Client
    client = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)
    
    await client.start()
    
    replicator = TelegramReplicator(client, src, dst)
    await replicator.start()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nService stopped by user.")
    except Exception as e:
        print(f"\nFatal error: {e}")
