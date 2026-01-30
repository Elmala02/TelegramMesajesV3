import os
import logging
import emoji
import re
from telethon import TelegramClient, events
from telethon.tl.types import Message
from deep_translator import GoogleTranslator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TelegramReplicator:
    def __init__(self, client: TelegramClient, source_id, destination_id):
        self.client = client
        self.source_id = source_id
        self.destination_id = destination_id
        
        # Load filtering config
        self.keywords = [k.strip().upper() for k in os.getenv('KEYWORDS', 'BUY,SELL,TP,SL,ENTRY,STOP,CLOSE,LIMIT').split(',')]
        self.promo_triggers = [p.strip().lower() for p in os.getenv('PROMO_TRIGGERS', 'promoción,promo,promocion,publicidad,síguenos,canal,link,@,comments,profits').split(',')]
        self.block_keywords = [b.strip().upper() for b in os.getenv('BLOCK_KEYWORDS', 'VIP,team,smashed,meanwhile,message👇,profits').split(',')]
        
        # Translation config
        self.enable_translation = os.getenv('ENABLE_TRANSLATION', 'False').lower() == 'true'
        self.translator = GoogleTranslator(source='auto', target='es')

    async def start(self):
        """Starts the replicator listener."""
        
        # Verify access to channels
        try:
            logger.info(f"Verifying access to Source: {self.source_id}")
            source_entity = await self.client.get_entity(self.source_id)
            logger.info(f"Source confirmed: {getattr(source_entity, 'title', source_entity)}")

            logger.info(f"Verifying access to Destination: {self.destination_id}")
            dest_entity = await self.client.get_entity(self.destination_id)
            logger.info(f"Destination confirmed: {getattr(dest_entity, 'title', dest_entity)}")
            
            # Store resolved entities to avoid repeated lookups
            self.source_entity = source_entity
            self.dest_entity = dest_entity
            
        except Exception as e:
            logger.error(f"Failed to access channels: {e}")
            logger.error("Please double-check your channel IDs/Usernames in .env and ensure the account joined them.")
            return

        @self.client.on(events.NewMessage(chats=self.source_id))
        async def handler(event):
            await self.process_message(event.message)

        logger.info("Replicator is running. Waiting for new messages...")
        await self.client.run_until_disconnected()

    def translate_text(self, text: str):
        """Translates text to Spanish while protecting specific trading terms."""
        try:
            if not text or not self.enable_translation:
                return text
            
            # Terms that should NOT be translated
            protected_terms = [
                r'\bBUY\b', r'\bSELL\b', r'\bTP\b', r'\bSL\b', 
                r'\bSTOPLOSS\b', r'\bSTOP LOSS\b', r'\bENTRY\b', 
                r'\bLIMIT\b', r'\bORDER\b', r'\bHIT\b'
            ]
            
            # Dictionary to store placeholders and their original values
            placeholders = {}
            protected_text = text

            # 1. Identify and replace terms with placeholders (Case-insensitive match, but preserve original)
            for i, term_pattern in enumerate(protected_terms):
                # We use a lambda to handle case-insensitive replacements while maintaining a map
                def replace_func(match):
                    placeholder = f"__PROTECTED_{i}_{len(placeholders)}__"
                    placeholders[placeholder] = match.group(0)
                    return placeholder
                
                protected_text = re.sub(term_pattern, replace_func, protected_text, flags=re.IGNORECASE)

            # 2. Translate the text with placeholders
            logger.info("Translating message to Spanish (with term protection)...")
            translated_text = self.translator.translate(protected_text)

            # 3. Restore original terms from placeholders
            for placeholder, original_value in placeholders.items():
                translated_text = translated_text.replace(placeholder, original_value)
                # Also handle cases where Google adds spaces around placeholders
                translated_text = translated_text.replace(f" {placeholder} ", f" {original_value} ")

            return translated_text
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return text

    def clean_message_text(self, text: str):
        """
        Applies filtering rules:
        1. Keyword filter (mandatory)
        2. Emoji cleaning
        """
        if not text:
            return None

        # --- Rule 0: Global Block Filter ---
        text_upper = text.upper()
        for block_word in self.block_keywords:
            if block_word in text_upper:
                logger.info(f"Message discarded: Found block keyword '{block_word}'")
                return None

        # --- Rule 1: Keyword Filter (Case-insensitive) ---
        if not any(keyword in text_upper for keyword in self.keywords):
            logger.info("Message ignored: No keywords found.")
            return None

        # --- Rule 2: Emoji Cleaning (DISABLED as per user request) ---
        # text = emoji.replace_emoji(text, replace='')

        # --- Rule 3: Promotion Filter (Truncate from word down) ---
        # Split text into lines to find the trigger word
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line_lower = line.lower()
            # Check if any trigger word is in this line
            found_trigger = False
            for trigger in self.promo_triggers:
                if trigger in line_lower:
                    found_trigger = True
                    break
            
            if found_trigger:
                # Stop processing lines here
                logger.info(f"Promotion detected and truncated at line: '{line.strip()}'")
                break
            else:
                cleaned_lines.append(line)

        final_text = "\n".join(cleaned_lines).strip()
        
        # Cleanup: Remove excessive blank lines
        final_text = re.sub(r'\n\s*\n', '\n', final_text)

        return final_text if final_text else None

    async def process_message(self, message: Message):
        """
        Extracts content, applies filters, translates and sends to destination.
        """
        try:
            # Apply text filtering and cleaning
            original_text = message.text or ""
            cleaned_text = self.clean_message_text(original_text)

            # Check if we should ignore based on keywords
            if not cleaned_text and original_text != "":
                 return
            
            # If no text remains and no media, skip
            if not cleaned_text and not message.media:
                return

            # Apply translation if enabled
            if cleaned_text:
                cleaned_text = self.translate_text(cleaned_text)

            logger.info("Processing valid message...")

            # Handle Media
            if message.media:
                logger.info("Message contains media. Downloading...")
                file_path = await message.download_media()
                
                if file_path:
                    logger.info(f"Media downloaded to {file_path}. Uploading to destination...")
                    await self.client.send_file(
                        self.dest_entity,
                        file_path,
                        caption=cleaned_text or "",
                        force_document=False
                    )
                    # Clean up
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass
                else:
                    if cleaned_text:
                        await self.client.send_message(self.dest_entity, cleaned_text)
            
            else:
                # Just Text
                if cleaned_text:
                    logger.info("Sending replicated message...")
                    await self.client.send_message(self.dest_entity, cleaned_text)
            
            logger.info("Message replicated successfully.")

        except Exception as e:
            logger.error(f"Error replicating message: {e}")
