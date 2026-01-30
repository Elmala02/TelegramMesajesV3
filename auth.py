import os
import asyncio
from telethon import TelegramClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
SESSION_NAME = os.getenv('SESSION_NAME', 'replicator_session')

async def main():
    if not API_ID or not API_HASH:
        print("Error: API_ID and API_HASH must be set in your .env file.")
        return

    print(f"Initializing Telegram Client '{SESSION_NAME}'...")
    print("If this is your first time, you will be asked to enter your phone number and the code you receive.")

    async with TelegramClient(SESSION_NAME, int(API_ID), API_HASH) as client:
        me = await client.get_me()
        print(f"\nSuccessfully logged in as: {me.first_name} (@{me.username})")
        print(f"Session file '{SESSION_NAME}.session' has been created/updated.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")
