import os
import logging
import re
import json
import asyncio
from datetime import datetime, timedelta
import pytz
import httpx
from telethon import TelegramClient, events
from telethon.tl.types import Message

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("debug_replicator.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SignalStateManager:
    """Manages state for logical filters (Conflicts, Duplicates, Priorities)."""
    def __init__(self, state_file="signal_state.json"):
        self.state_file = state_file
        self.active_signals = [] # List of dicts: {asset, direction, entry, priority, timestamp}
        self.load_state()

    def load_state(self):
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    self.active_signals = json.load(f)
        except Exception as e:
            logger.error(f"Error loading state: {e}")
            self.active_signals = []

    def save_state(self):
        try:
            # Prune old signals (> 24 hours)
            cutoff = datetime.now(pytz.UTC) - timedelta(hours=24)
            self.active_signals = [
                s for s in self.active_signals 
                if datetime.fromisoformat(s['timestamp']) > cutoff
            ]
            with open(self.state_file, 'w') as f:
                json.dump(self.active_signals, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving state: {e}")

    def check_duplicate(self, asset, direction, entry):
        """
        Returns True if EXACTLY the same signal (same asset, same dir) 
        was posted recently (last 2 hours), REGARDLESS of priority.
        If it's a re-post, we ignore it.
        """
        if not asset or not direction: return False 

        now = datetime.now(pytz.UTC)
        cutoff = now - timedelta(hours=2)

        for signal in self.active_signals:
            sig_time = datetime.fromisoformat(signal['timestamp'])
            if sig_time > cutoff and signal['asset'] == asset and signal['direction'] == direction:
                # Same signal recently?
                return True
        return False

    def check_priority_conflict(self, asset, new_priority):
        """
        Resolves conflict based on Priority.
        Returns:
            allowed (bool): If True, proceed. If False, block.
            action (str): 'NEW' (no conflict), 'REPLACE' (override old), 'BLOCK' (low priority)
        """
        if not asset: return True, 'NEW'

        now = datetime.now(pytz.UTC)
        cutoff = now - timedelta(hours=4) # Active window
        
        # Sort signals by time (newest first) to find the current active one for this asset
        relevant_signals = [
            s for s in self.active_signals 
            if s['asset'] == asset and datetime.fromisoformat(s['timestamp']) > cutoff
        ]
        
        if not relevant_signals:
            return True, 'NEW'

        # Get latest active signal for this asset
        # (Assuming the list maintenance keeps it reasonably clean, or we just take the last one)
        latest_signal = relevant_signals[-1] 
        old_priority = latest_signal.get('priority', 99) # Default to low priority if unknown

        logger.info(f"Priority Check: Asset={asset}, NewPrio={new_priority}, OldPrio={old_priority}")

        if new_priority < old_priority:
            # New message is HIGHER priority (lower number). OVERRIDE.
            return True, 'REPLACE'
        elif new_priority > old_priority:
            # New message is LOWER priority. BLOCK.
            return False, 'BLOCK'
        else:
            # Equal priority. Allow for now as requested.
            return True, 'NEW'

    def update_signal(self, asset, direction, priority):
        """Adds new signal, removing conflicting ones for the same asset to keep state clean."""
        # Remove active signals for this asset (Logic: One active signal per asset per time window)
        # Or better: Just append the new one, and `check_priority_conflict` logic looks at the latest.
        # Let's prune old ones for this asset to "replace" it.
        self.active_signals = [s for s in self.active_signals if s['asset'] != asset]
        
        self.active_signals.append({
            "asset": asset,
            "direction": direction,
            "priority": priority,
            "timestamp": datetime.now(pytz.UTC).isoformat()
        })
        self.save_state()

class TelegramReplicator:
    def __init__(self, client: TelegramClient, source_map, destination_id):
        self.client = client
        self.source_map = source_map # Dict {id: priority}
        self.destination_id = destination_id
        
        self.state_manager = SignalStateManager()
        
        self.promo_triggers = [
            "promo", "promoción", "promocion", "canal", "únete", "link", 
            "publicidad", "siguenos", "síguenos", "contact", "@", "vip"
        ]
        
        self.ai_api_url = os.getenv('AI_API_URL', 'https://apifreellm.com/api/v1/chat')
        self.ai_api_key = os.getenv('AI_API_KEY', '')

    async def start(self):
        """Starts listeners for all source channels."""
        source_ids = list(self.source_map.keys())
        logger.info(f"Listening on sources: {source_ids} -> Destination: {self.destination_id}")
        
        # Verify Destination
        try:
            self.dest_entity = await self.client.get_entity(self.destination_id)
        except Exception as e:
            logger.error(f"Destination Channel Error: {e}")
            return

        # Listen to ALL source channels
        @self.client.on(events.NewMessage(chats=source_ids))
        async def handler(event):
            # Identify source
            chat_id = event.chat_id
            # Handle discrepancies in ID formats (sometimes brings -100 prefix, sometimes not)
            # We trust self.source_map keys match what Telethon sees or we normalize.
            # Telethon events usually return the packed ID. 
            # Let's try to lookup directly.
            priority = self.source_map.get(chat_id)
            if priority is None: 
                # Try finding by name or other means? Or just ignore unknown (shouldn't happen with filter)
                logger.warning(f"Message from unknown source ID {chat_id}. Defaulting to lowest priority (99).")
                priority = 99
                
            await self.process_message(event.message, priority)

        logger.info("Antigraviti Multi-Source Replicator Running...")
        await self.client.run_until_disconnected()

    # --- STAGE: HARD FILTERS ---
    def run_hard_filters(self, text):
        if not text: return None
        text_upper = text.upper()
        
        # 1.1 Keywords (Extended for full words)
        keywords = ["BUY", "SELL", "TP", "SL", "HIT", "TARGET", "BE", "BREAK EVEN", "ENTRY", "TAKE PROFIT", "STOP LOSS", "SIGNAL"]
        if not any(w in text_upper for w in keywords):
            return None
            
        # 1.3 Promo Trimming
        lines = text.split('\n')
        clean_lines = []
        for line in lines:
            line_lower = line.lower()
            if any(t in line_lower for t in self.promo_triggers):
                break # Cut everything below
            clean_lines.append(line)
        
        cleaned_text = "\n".join(clean_lines).strip()
        cleaned_text_upper = cleaned_text.upper()
        
        if not cleaned_text: return None

        # 1.2 Structure
        is_signal = ("BUY" in cleaned_text_upper or "SELL" in cleaned_text_upper) and \
                    ("SL" in cleaned_text_upper or "STOP" in cleaned_text_upper)
        is_update = any(w in cleaned_text_upper for w in ["HIT", "TARGET", "TP", "SL", "BE", "BREAK EVEN"])

        # Weak entry check (digit) - Only mandatory for signals, not for quick updates like "TP1 HIT"
        has_digit = any(c.isdigit() for c in cleaned_text)

        if not (is_signal or is_update):
             return None
        
        if is_signal and not has_digit:
             return None

        return cleaned_text

    # --- STAGE: LOGICAL FILTERS ---
    def parse_signal(self, text):
        text_upper = text.upper()
        direction = "BUY" if "BUY" in text_upper else "SELL" if "SELL" in text_upper else None
        
        # Asset Regex
        asset = None
        words = re.findall(r'\b[A-Z0-9]{3,6}\b', text_upper)
        ignore = ["BUY", "SELL", "SL", "TP", "TP1", "TP2", "ENTRY", "STOP", "LOSS", "ZONE"]
        for w in words:
            if w not in ignore:
                asset = w
                break
        return asset, direction

    def is_market_hours(self):
        now = datetime.now(pytz.UTC)
        # London (08:00 UTC) to NY Closed (22:00 UTC)? 
        # Prompt says: "Preferably during London/NY".
        # Let's say 7 AM UTC to 9 PM UTC covering both.
        return 6 <= now.hour < 21

    def run_logical_filters(self, text, priority):
        asset, direction = self.parse_signal(text)
        
        if not asset or not direction:
            # If we can't parse, we can't apply asset logic. 
            # If structure passed Hard Filter, valid but unparsed. 
            # Conservative: Allow, but assign 'Unknown' asset? 
            # Or Block? User said "Si falta... descartar".
            return True, asset, direction

        # 2.3 Check Duplicates (Exact same signal) - DISABLED BY USER REQUEST
        # if self.state_manager.check_duplicate(asset, direction, None):
        #     logger.info(f"Logical: Duplicate signal for {asset}. Ignoring.")
        #     return False, asset, direction

        # 2.1 & 2.2 Check Priority / Conflict
        # We need to know if there's an existing signal for this asset.
        allowed, action = self.state_manager.check_priority_conflict(asset, priority)
        
        if not allowed:
            logger.info(f"Logical: Priority Block. New Priority {priority} too low or Conflict.")
            return False, asset, direction
            
        if action == 'REPLACE':
            logger.info(f"Logical: High Priority Signal! Replacing previous state for {asset}.")

        # 2.4 Schedule
        if not self.is_market_hours():
            logger.warning("Logical: Outside Market Hours. Conservative mode (Logging only).")
            # return False, asset, direction # Uncomment to block

        return True, asset, direction

    # --- STAGE: AI FILTER ---
    async def run_ai_filter(self, text):
        if not self.ai_api_key: return text

        system_prompt = (
            "Eres un transcriptor experto y editor profesional de un club de trading. "
            "Tu misión es reescribir el mensaje siguiendo estas REGLAS DE ORO:\n"
            "1. TRADUCE al español latino neutro si el mensaje está en inglés.\n"
            "2. REEMPLAZA OBLIGATORIAMENTE cualquier nombre de usuario (ej. @GoldMaster) por: @josejaqueoficial.\n"
            "3. REEMPLAZA OBLIGATORIAMENTE palabras como 'club', 'hermandad', 'brotherhood', 'familia', 'family' por: Club 10M.\n"
            "4. TRADUCE 'Managing risk by moving stops/most stops to BE' como: Aseguren ganancias moviendo SL a break even.\n"
            "5. NORMALIZA el formato. Acepta 'Take Profit' como TP, 'Stop Loss' como SL, 'Signal' como Dirección y 'Entry' como Entrada.\n"
            "   A. Si es una NUEVA SEÑAL (aunque use palabras completas como Take Profit/Stop Loss):\n"
            "      💎 Activo: [Activo]\n"
            "      🚀 Dirección: BUY / SELL\n"
            "      📥 Entrada: [Precio]\n"
            "      🎯 TP1: [Precio]\n"
            "      🎯 TP2: [Precio]\n"
            "      ⛔ SL: [Precio]\n"
            "      ⚖️ Riesgo recomendado: 1–2%\n"
            "      ✅ Estado: Activa\n\n"
            "   B. Si es una ACTUALIZACIÓN (TP HIT, SL HIT, TARGET REACHED):\n"
            "      💎 Activo: [Activo]\n"
            "      ✅ Resultado: [Ej: TP1 HIT / SL HIT]\n"
            "      💰 Ganancia/Pérdida: [Si se menciona, ej: +40 pips]\n"
            "      📢 Aviso: Club 10M\n\n"
            "5. Estilo profesional, sin emojis adicionales (mantén los originales si son útiles), sin promos, sin enlaces.\n"
            "6. NO inventes datos técnicos (precios, TPs, SLs).\n\n"
            "Si el mensaje es charla irrelevante o falta información vital: responde solo REJECT.\n"
            "Mensaje a procesar:"
        )
        
        full_prompt = f"{system_prompt}\n{text}"

        try:
             async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.ai_api_url,
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.ai_api_key}"},
                    json={"message": full_prompt, "model": "apifreellm"},
                    timeout=30.0
                )
                if response.status_code == 200:
                    resp_text = response.json().get('response', '').strip()
                    if "REJECT" in resp_text.upper() and len(resp_text) < 50:
                        return None
                    return resp_text
                else:
                    logger.error(f"AI API Error: {response.status_code} - {response.text}")
                    return None
        except Exception as e:
            logger.error(f"AI Filter Exception: {e}")
            return None

    # --- PIPELINE ---
    async def process_message(self, message: Message, priority: int):
        original_text = message.text or ""
        logger.info(f"Pipeline: New msg from Prio {priority}. Len: {len(original_text)}")

        # 1. Hard
        clean_1 = self.run_hard_filters(original_text)
        if not clean_1: return

        # 2. Logical
        passed, asset, direction = self.run_logical_filters(clean_1, priority)
        if not passed: return

        # 3. AI
        # Bypass AI for very short messages like "TP1 HIT" to avoid AI hallucination/rejection
        if len(clean_1) < 20:
            logger.info("Pipeline: Short message detected. Bypassing AI filter.")
            final_text = clean_1
        else:
            final_text = await self.run_ai_filter(clean_1)
            
        if not final_text:
            logger.warning("Pipeline: AI Filter rejected or failed. Message discarded.")
            return

        # STRIKE RULE: Never publish AI reasoning or "REJECT" explanations
        if "REJECT" in final_text.upper() or len(final_text) > (len(clean_1) * 3 + 100):
            logger.warning(f"Pipeline: AI returned a rejection or weird explanation. Discarding to avoid garbage in channel.")
            return

        # 4. Publish
        try:
            logger.info(f"Pipeline: PUBLISHING for {asset} (Prio {priority})")
            await self.client.send_message(self.dest_entity, final_text)
            
            # 5. Update State
            if asset and direction:
                self.state_manager.update_signal(asset, direction, priority)
        except Exception as e:
            logger.error(f"Publish Error: {e}")
