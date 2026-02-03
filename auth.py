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

    from telethon.sessions import StringSession

    # Use StringSession if available, or just create one to export
    # For auth.py, we want force interactive login to GENERATE the string
    async with TelegramClient(StringSession(), int(API_ID), API_HASH) as client:
        me = await client.get_me()
        print(f"\nSuccessfully logged in as: {me.first_name} (@{me.username})")
        
        # EXPORT SESSION STRING
        session_string = client.session.save()
        print("Done! Here is your SESSION_STRING for Vercel/Env:")
        print("-" * 40)
        print(session_string)
        print("-" * 40)
        print("COPY THE STRING ABOVE AND PASTE IT AS 'SESSION_STRING' IN VERCEL ENV VARIABLES.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")
