import os
import logging
import re
import json
import asyncio
from datetime import datetime, timedelta
import pytz
import httpx
import emoji
from telethon import TelegramClient, events
from telethon.tl.types import Message
from config import KEYWORDS_OBLIGATORIAS, ANALYSIS_KEYWORDS, PROMO_TRIGGERS
from database import TradingDB

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

class TelegramReplicator:
    def __init__(self, client: TelegramClient, replication_map):
        self.client = client
        self.replication_map = replication_map # Dict {source_id: {dest, topic, priority}}
        
        self.db = TradingDB()
        
        self.promo_triggers = PROMO_TRIGGERS
        
        self.ai_api_url = os.getenv('AI_API_URL', 'https://apifreellm.com/api/v1/chat')
        self.ai_api_key = os.getenv('AI_API_KEY', '')

    async def start(self):
        """Starts listeners for all source channels."""
        source_ids = list(self.replication_map.keys())
        logger.info(f"Listening on sources: {source_ids}")
        
        # Listen to ALL source channels
        @self.client.on(events.NewMessage(chats=source_ids))
        async def handler(event):
            chat_id = event.chat_id
            config = self.replication_map.get(chat_id)
            
            if config:
                priority = config.get('priority', 99)
                await self.process_message(event.message, priority, config)
            else:
                logger.warning(f"Message from unknown source ID {chat_id}.")

        logger.info("Antigraviti Multi-Source Replicator Running...")
        await self.client.run_until_disconnected()

    # --- STAGE: HARD FILTERS ---
    def clean_emojis(self, text):
        """Elimina emojis decorativos manteniendo la legibilidad técnica."""
        if not text: return ""
        # Lista de emojis que permitimos (diamante, flechas, checks, etc.)
        allowed = ["💎", "✅", "🚨", "🎯", "📉", "📈", "💡", "🔑", "📌", "🔥", "🟢", "🔴"]
        
        # Descomponer el texto y filtrar emojis no permitidos
        clean_text = ""
        for char in text:
            if char in allowed or not emoji.is_emoji(char):
                clean_text += char
        return clean_text.strip()

    def run_hard_filters(self, text):
        if not text: return None
        
        # Limpieza de emojis basura al inicio
        text = self.clean_emojis(text)
        if not text: return None

        text_upper = text.upper()
        
        # 1.1 Keywords (Extended for full words and BE updates)
        keywords = KEYWORDS_OBLIGATORIAS
        
        # Check if at least one keyword is present
        if not any(w in text_upper for w in keywords):
            return None
            
        # 1.2 Anti-Analysis Filter: Descartar si el texto es demasiado largo y parece un análisis
        # Los análisis suelen tener palabras como "Resistance", "Support", "Sentiment", "Drivers"
        analysis_keywords = ANALYSIS_KEYWORDS
        analysis_count = sum(1 for w in analysis_keywords if w in text_upper)
        
        # Si tiene más de 2 palabras de análisis y es largo, es un reporte, no una señal
        if analysis_count >= 2 and len(text) > 300:
            logger.info("Hard Filter: Detected as Market Analysis Report. Discarding.")
            return None

        # 1.3 Promo Trimming
        lines = text.split('\n')
        clean_lines = []
        for line in lines:
            line_lower = line.lower()
            if any(t in line_lower for t in self.promo_triggers):
                # Si la línea tiene un trigger de promo pero TAMBIÉN tiene TP, SL o Entrada, no la cortamos
                # Ejemplo: "TP1 5018 (Join our group)" -> no queremos cortar esto si tiene el precio
                if not any(w in line.upper() for w in ["TP", "SL", "ENTRY", "ENTRADA", "BUY", "SELL", "COMPRA", "VENTA"]):
                    break 
            clean_lines.append(line)
        
        cleaned_text = "\n".join(clean_lines).strip()
        cleaned_text_upper = cleaned_text.upper()
        
        if not cleaned_text: return None

        # 1.4 Structure Validation
        has_entry = "ENTRY" in cleaned_text_upper or "ENTRADA" in cleaned_text_upper or re.search(r'\d{4,}\s*-\s*\d{4,}', cleaned_text_upper)
        has_sl = "SL" in cleaned_text_upper or "STOP" in cleaned_text_upper
        has_direction = "BUY" in cleaned_text_upper or "SELL" in cleaned_text_upper or "COMPRA" in cleaned_text_upper or "VENTA" in cleaned_text_upper

        is_signal = has_direction and (has_sl or has_entry)
        
        # Valid events that represent updates (TP reached, SL hit, BE)
        # These are short messages that MUST be allowed
        update_keywords = [
            "TP1", "TP 1", "TP2", "TP3", "TP4", 
            "SL", "STOP LOSS", "STOPLOSS", "🚫SL",
            "BE", "BREAKEVEN", "BREAK EVEN", "SL TO BE", "MOVE SL", "SL MOVED"
        ]
        
        # Endurecer is_update: Ya no basta con que contenga "BE" o "TP1", 
        # debe ser un mensaje corto o tener indicadores claros de acción.
        # El mensaje del usuario contenía "BE" dentro de "successful" (sucessful) y "BEen" (been).
        # Vamos a usar regex para asegurar que sean palabras completas.
        
        has_update_keyword = any(re.search(rf'\b{re.escape(w)}\b', cleaned_text_upper) for w in update_keywords)
        has_action_keyword = any(re.search(rf'\b{re.escape(w)}\b', cleaned_text_upper) for w in ["HIT", "TARGET", "DONE", "REACHED", "TRIGGERED"])
        has_moving_stops = "MOVING STOPS" in cleaned_text_upper or "STOPS TO BE" in cleaned_text_upper
        
        is_update = has_update_keyword or has_action_keyword or has_moving_stops

        # Si el mensaje es muy largo (> 600 caracteres) y no es una señal clara (is_signal),
        # probablemente sea charla o comentario, incluso si tiene palabras clave.
        # Hemos subido el límite de 150 a 600 para permitir señales con mucho texto (como FXKINGS).
        if len(cleaned_text) > 600 and not is_signal:
            # Solo permitir si tiene al menos 2 indicadores de actualización muy claros
            clear_indicators = sum([has_update_keyword, has_action_keyword, has_moving_stops])
            if clear_indicators < 2:
                logger.info(f"Hard Filter: Message too long ({len(cleaned_text)}) and lacks clear signal structure. Discarding as chat.")
                return None

        # Weak entry check (digit) - Mandatory for new signals
        has_digit = any(c.isdigit() for c in cleaned_text)

        if not (is_signal or is_update):
             return None
        
        # Una señal nueva debe tener números (precios)
        # Las actualizaciones (is_update) pueden no tener números (ej: "TP1 HIT")
        if is_signal and not is_update and not has_digit:
             return None

        return cleaned_text

    # --- STAGE: LOGICAL FILTERS ---
    def parse_signal(self, text):
        text_upper = text.upper()
        direction = "BUY" if any(w in text_upper for w in ["BUY", "COMPRA", "COMPRAR"]) else \
                    "SELL" if any(w in text_upper for w in ["SELL", "VENTA", "VENDER"]) else None
        
        # Asset Regex: Avoid pure numbers, allow letters and symbols
        asset = None
        words = re.findall(r'\b[A-ZÁÉÍÓÚ]{3,10}\b', text_upper) # Only letters
        ignore = [
            "BUY", "SELL", "SL", "TP", "TP1", "TP2", "TP3", "TP4", "TP5", "ENTRY", "STOP", "LOSS", 
            "ZONE", "NOW", "HIGH", "RISK", "COMPRA", "VENTA", "VENDER", "COMPRAR", "ENTRADA", "ORO", "OPEN", "ABIERTO"
        ]
        for w in words:
            if w not in ignore and not w.isdigit():
                asset = w
                break
        
        # Special case for "ORO" if no other asset found
        if not asset:
            if any(w in text_upper for w in ["ORO", "GOLD", "XAUUSD", "XAU/USD"]):
                asset = "GOLD"
            elif any(w in text_upper for w in ["PLATA", "SILVER", "XAGUSD", "XAG/USD"]):
                asset = "SILVER"
            elif any(w in text_upper for w in ["PETROLEO", "OIL", "WTI", "USOIL"]):
                asset = "OIL"
        
        # Enhanced extraction for DB
        data = {
            "asset": asset or "GOLD",
            "direction": direction,
            "entry_min": None,
            "entry_max": None,
            "tp1": None,
            "tp2": None,
            "tp3": None,
            "tp4": None,
            "tp4_complex": None, # For "Abierto (5012/5010/...)"
            "tp5": None,
            "sl": None
        }

        # 1. Entry Range (Mover arriba para que esté disponible para limpiar TPs)
        entry_match = re.search(r'(?:ENTRY|ENTRADA|AT|BUY|SELL|COMPRA|VENTA|VENDER|COMPRAR)?\s*(?:NOW|GOLD|XAUUSD|ORO)?\s*[:\-\s]*(\d{4,}(?:\.\d+)?)\s*[-]\s*(\d{4,}(?:\.\d+)?)', text_upper)
        if entry_match:
            data["entry_min"] = float(entry_match.group(1))
            data["entry_max"] = float(entry_match.group(2))
        else:
            # Búsqueda más flexible para entrada única (solo si tiene 4+ dígitos para evitar TPs)
            single_entry = re.search(r'(?:ENTRY|ENTRADA|AT|BUY|SELL|COMPRA|VENTA|VENDER|COMPRAR)\s+(?:NOW|GOLD|XAUUSD|ORO)?\s*[:\-\s]*(\d{4,}(?:\.\d+)?)', text_upper)
            if not single_entry:
                single_entry = re.search(r'(?:ENTRY|ENTRADA)\s*[:\-\s]*(\d{4,}(?:\.\d+)?)', text_upper)
            
            if single_entry:
                data["entry_min"] = float(single_entry.group(1))
            elif not data["entry_min"]:
                # Si no hay nada, pero hay un rango al inicio del mensaje (caso reporte usuario)
                start_range = re.match(r'^\s*(\d{4,}(?:\.\d+)?)\s*[-]\s*(\d{4,}(?:\.\d+)?)', text_upper)
                if start_range:
                    data["entry_min"] = float(start_range.group(1))
                    data["entry_max"] = float(start_range.group(2))

        # 2. Stop Loss
        sl_match = re.search(r'(?:SL|STOP\s*LOSS|STOP)\s*[:\-\s]*(\d+(?:\.\d+)?)', text_upper)
        if sl_match: data["sl"] = float(sl_match.group(1))

        # 3. TP1, TP2, TP3, TP4, TP5
        # Mapeo de emojis a índices
        emojis = [("🥇", 1), ("🥈", 2), ("🥉", 3), ("🎖️", 4)]
        
        # Primero buscamos por emojis (tienen prioridad)
        for emoji, index in emojis:
            # Buscar el emoji en el texto
            if emoji in text_upper:
                # Extraer lo que sigue al emoji hasta el final de la línea
                # Usamos un escape para el emoji por si acaso
                parts = text_upper.split(emoji)
                if len(parts) > 1:
                    # Tomamos la parte justo después del emoji
                    line = parts[1].split("\n")[0].strip()
                    # Limpiar prefijos como "TP1", "TP 1", "TP:", ":", "-", etc.
                    val = re.sub(r'^(?:TP\s*\d?)?\s*[:\-\s]*', '', line, flags=re.IGNORECASE).strip()
                    # Limpiar "OPEN" o "ABIERTO"
                    val = re.sub(r'^(?:OPEN|ABIERTO)\s*', '', val, flags=re.IGNORECASE).strip()
                    
                    if val and self.is_not_entry_range(val, data):
                        data[f"tp{index}"] = val

        # Luego buscamos por texto "TP1", "TP2", etc. para los que falten
        for i in range(1, 6):
            if not data[f"tp{i}"]:
                # Buscar TP{i} que NO esté precedido por un emoji ya procesado
                pattern = rf'(?<!🥇)(?<!🥈)(?<!🥉)(?<!🎖️)TP\s*{i}\s*[:\-\s]*([^\n]+)'
                match = re.search(pattern, text_upper)
                if not match:
                    # Intentar "TAKE PROFIT i"
                    pattern = rf'TAKE\s*PROFIT\s*{i}\s*[:\-\s]*([^\n]+)'
                    match = re.search(pattern, text_upper)
                    
                if match:
                    val = match.group(1).strip()
                    val = re.sub(r'^(?:OPEN|ABIERTO)\s*', '', val, flags=re.IGNORECASE).strip()
                    if self.is_not_entry_range(val, data):
                        # Si es TP4 y tiene formato complejo, lo mantenemos
                        if i == 4 and ("/" in val or "(" in val):
                            data["tp4"] = val
                        else:
                            clean_price_match = re.search(r'(\d{4,}(?:\.\d+)?)', val)
                            if clean_price_match:
                                val = clean_price_match.group(1)
                            data[f"tp{i}"] = val

        # Especial: Si solo hay "Take Profit" sin número y tp1 está vacío
        if not data["tp1"]:
            tp_single = re.search(r'TAKE\s*PROFIT\s*[:\-\s]*([\d\.,\s/\-]+)', text_upper)
            if tp_single: 
                val = tp_single.group(1).strip()
                if self.is_not_entry_range(val, data):
                    data["tp1"] = val

        # Limpieza final: Evitar que el TP5 se "invente" con basura
        # Si TP5 es igual a la entrada o a otro TP, borrarlo
        if data["tp5"]:
            if not self.is_not_entry_range(data["tp5"], data):
                data["tp5"] = None
            else:
                for k in range(1, 5):
                    if data["tp5"] == data[f"tp{k}"]:
                        data["tp5"] = None
                        break

        return data

    def is_not_entry_range(self, val, data):
        """Verifica que un valor de TP no sea en realidad el rango de entrada."""
        if not val: return False
        e_min = data.get('entry_min')
        e_max = data.get('entry_max')
        
        clean_val = str(val).replace(" ", "").replace("–", "-")
        
        range_variations = []
        if e_min is not None and e_max is not None:
            range_variations = [
                f"{int(e_min)}-{int(e_max)}",
                f"{int(e_max)}-{int(e_min)}",
                f"{e_min}-{e_max}",
                f"{e_max}-{e_min}"
            ]
        elif e_min is not None:
            range_variations = [str(int(e_min)), str(e_min)]

        if any(clean_val == c.replace(" ", "") for c in range_variations):
            return False
        
        # También evitar si el valor es EXACTAMENTE el rango de entrada en el texto
        return True

    def validate_signal_coherence(self, data):
        """Validates numerical logic (Buy: SL < Entry < TP, Sell: SL > Entry > TP)."""
        if not data["direction"] or not data["sl"]:
            return True # Not a full signal or update

        entry = data["entry_min"]
        sl = data["sl"]
        tp1 = data["tp1"]

        # Si tp1 es un string (rango o lista), intentamos extraer el primer número
        if isinstance(tp1, str):
            match = re.search(r'(\d+(?:\.\d+)?)', tp1)
            if match:
                tp1 = float(match.group(1))
            else:
                return True # No podemos validar, asumimos coherente

        if not entry or not tp1:
            return True # Missing fields to validate

        if data["direction"] == "BUY":
            if not (sl < entry < tp1):
                logger.warning(f"Coherence Error: BUY signal SL({sl}) must be < Entry({entry}) < TP1({tp1})")
                return False
        elif data["direction"] == "SELL":
            if not (sl > entry > tp1):
                logger.warning(f"Coherence Error: SELL signal SL({sl}) must be > Entry({entry}) > TP1({tp1})")
                return False
        
        return True

    def is_market_hours(self):
        now = datetime.now(pytz.UTC)
        return 6 <= now.hour < 21

    def run_logical_filters(self, text, priority):
        data = self.parse_signal(text)
        asset = data["asset"]
        direction = data["direction"]
        
        if not asset or not direction:
            return True, data

        # Duplicates check removed by user request
        
        # Coherence check
        if not self.validate_signal_coherence(data):
            logger.error(f"Logical: Coherence validation failed for {asset} {direction}.")
            return False, data

        # Schedule
        if not self.is_market_hours():
            logger.warning("Logical: Outside Market Hours. Conservative mode (Logging only).")

        return True, data

    # --- STAGE: AI FILTER ---
    def clean_num(self, val):
        """Limpia caracteres no numéricos y formatea para quitar el .0 innecesario."""
        if val is None or val == "": return "No definido"
        
        # Si ya es un string con formato complejo (ej: 5050/5047 o Open), devolverlo casi tal cual
        if isinstance(val, str):
            if "/" in val or any(x in val.upper() for x in ["OPEN", "ABIERTO", "HIT"]):
                return val.strip("()")

        try:
            # Intentar formatear como número
            f_val = float(str(val).replace(",", ".").strip("()"))
            if f_val == int(f_val):
                return str(int(f_val))
            return str(f_val)
        except:
            # Si falla, limpiar caracteres no deseados pero mantener el string
            if isinstance(val, str):
                return "".join(c for c in val if c.isdigit() or c in '.,/').strip()
            return str(val)

    def format_signal_manually(self, data, raw_text=None):
        """Crea el formato base solicitado de forma manual si la IA falla."""
        text_upper = (raw_text or "").upper()
        
        # 1. Detectar si es una actualización (TP, SL, BE)
        # Una actualización suele ser un mensaje corto que NO contiene una entrada o rango de entrada claro
        # o que explícitamente dice HIT, REACHED, etc.
        is_full_signal = data.get('entry_min') is not None or re.search(r'\d+\s*-\s*\d+', text_upper)
        
        if not is_full_signal:
            # --- CASO TP ALCANZADO ---
            for i in range(1, 5):
                if f"TP{i}" in text_upper or f"TP {i}" in text_upper:
                    return f"✅ TP{i} ALCANZADO"
            
            # --- CASO STOP LOSS ---
            sl_keywords = ["SL", "STOP LOSS", "STOPLOSS", "🚫SL"]
            if any(w in text_upper for w in sl_keywords) and not any(w in text_upper for w in ["BE", "BREAKEVEN"]):
                if "HIT" in text_upper or "TRIGGERED" in text_upper or "DONE" in text_upper or len(text_upper) < 20:
                    return "✅ STOP LOSS ALCANZADO"

            # --- CASO BREAK EVEN ---
            be_keywords = ["BE", "BREAKEVEN", "BREAK EVEN", "SL TO BE", "MOVE SL", "SL MOVED"]
            if any(w in text_upper for w in be_keywords):
                return "✅ STOP LOSS MOVIDO A BREAK EVEN"

        # 2. Si no es actualización (o si tiene entrada), es una señal nueva
        asset = (data.get("asset") or "GOLD").upper()
        # Normalizar activo al estilo solicitado XAUUSD/GOLD
        gold_synonyms = ["GOLD", "ORO", "XAUUSD", "XAU", "XAU/USD"]
        silver_synonyms = ["SILVER", "PLATA", "XAGUSD", "XAG", "XAG/USD"]
        
        if any(s in asset for s in gold_synonyms) or asset == "GOLD":
            asset_display = "XAUUSD/GOLD"
        elif any(s in asset for s in silver_synonyms) or asset == "SILVER":
            asset_display = "XAGUSD/SILVER"
        else:
            asset_display = asset
        
        direction = data.get("direction") or "COMPRA"
        if direction.upper() == "BUY": direction = "COMPRA"
        if direction.upper() == "SELL": direction = "VENTA"
        
        # Determinar Entrada
        entry_min = data.get('entry_min')
        entry_max = data.get('entry_max')
        
        entry_str = self.clean_num(entry_min)
        if entry_max:
            entry_str += f" - {self.clean_num(entry_max)}"
            
        lines = [
            f"💎 **{asset_display}**",
            f"Operación: {direction}",
            f"Stop Loss: {self.clean_num(data.get('sl'))}",
            f"Entrada: {entry_str}"
        ]
        
        # TPs (TP1 en adelante)
        for i in range(1, 7):
            tp_val = data.get(f"tp{i}")
            if tp_val:
                # Si es un string con múltiples precios, lo limpiamos un poco
                if isinstance(tp_val, str):
                    tp_val = tp_val.replace("OPEN", "Abierto").replace("ABIERTO", "Abierto")
                    # Quitar paréntesis innecesarios si es solo una lista
                    tp_val = tp_val.strip("()")
                lines.append(f"TP{i}: {self.clean_num(tp_val)}")
                
        return "\n".join(lines)

    async def run_ai_filter(self, text):
        if not self.ai_api_key: return None

        # Si la clave parece de Google Gemini, intentamos usar el endpoint oficial si el proxy falla
        is_gemini_key = self.ai_api_key.startswith("gen-lang-client") or len(self.ai_api_key) > 30
        
        system_prompt = (
            "Eres un experto en trading. Tu única tarea es traducir y normalizar SEÑALES DE TRADING al ESPAÑOL siguiendo un FORMATO BASE ESTRICTO.\n\n"

    "REGLAS DE ORO:\n"
    "1. USA SIEMPRE EL FORMATO BASE ABAJO. No añadas saludos, ni 'Señal detectada', ni explicaciones.\n"

    "2. El ORDEN de las líneas es CRÍTICO y OBLIGATORIO:\n"
    "Activo\n"
    "Operación\n"
    "Stop Loss\n"
    "Entrada\n"
    "TP1\n"
    "TP2\n"
    "TP3\n"
    "TP4\n\n"

    "3. TRADUCCIONES OBLIGATORIAS:\n"
    "Buy → COMPRA\n"
    "Sell → VENTA\n"
    "Gold → XAUUSD/GOLD\n"
    "XAUUSD → XAUUSD/GOLD\n"
    "Entry → Entrada\n"
    "Take Profit → TP\n"
    "Stop Loss → Stop Loss\n\n"

    "4. MANTÉN Entrada y TP como campos separados. Nunca los unas.\n"

    "5. ELIMINA links, menciones, publicidad o texto irrelevante.\n"

    "6. 'Take Profit', 'TP' y emojis de TP son equivalentes.\n"

    "7. Si un TP tiene varios precios, inclúyelos en la misma línea separados por coma.\n"
    "Ejemplo:\n"
    "TP4: 5050, 5047, 5042, 5036\n\n"

    "8. INTERPRETACIÓN DE EMOJIS:\n"
    "🥇 = TP1\n"
    "🥈 = TP2\n"
    "🥉 = TP3\n"
    "🎖️ = TP4\n"
    "🚫SL = Stop Loss\n\n"

    "9. INTERPRETACIÓN DE ENTRADA:\n"
    "Un número solo → Entrada\n"
    "Un rango como 5067 - 5059 o 4805-4800 → Entrada\n\n"

    "10. TP OPEN:\n"
    "Ejemplo:\n"
    "TP4 Open (5050/5047/5042/5036)\n"
    "Salida:\n"
    "TP4: 5050, 5047, 5042, 5036\n\n"

    "11. DETECTAR OPERACIÓN AUTOMÁTICAMENTE SI NO ESTÁ DEFINIDA:\n"
    "Si los TP están por debajo de la entrada → VENTA\n"
    "Si los TP están por encima de la entrada → COMPRA\n\n"

    "12. ACTIVO POR DEFECTO:\n"
    "Si aparece Gold o XAUUSD → usar XAUUSD/GOLD\n"
    "Si no aparece activo pero los precios son del oro → usar XAUUSD/GOLD\n\n"

    "13. Cuando se envía un TP por separado, es una ACTUALIZACIÓN.\n\n"

    "14. Si el mensaje no contiene una señal válida, NO RESPONDAS.\n\n"

    "--- FORMATO BASE PARA SEÑALES ---\n"
    "💎 **XAUUSD/GOLD**\n"
    "Operación: COMPRA o VENTA\n"
    "Stop Loss: precio\n"
    "Entrada: precio o rango\n"
    "TP1: precio\n"
    "TP2: precio\n"
    "TP3: precio\n"
    "TP4: precio\n\n"

    "--- FORMATO PARA ACTUALIZACIONES ---\n"
    "✅ XAUUSD/GOLD TP ALCANZADO\n\n"

    "Mensaje a procesar:"
    
    "15. INTERPRETACIÓN DE MENSAJES SOLO DE TP (ACTUALIZACIONES):\n"
"Si el mensaje contiene únicamente algo como:\n"
"TP1\n"
"TP 1\n"
"TP1✅\n"
"✅TP1\n"
"TP2\n"
"TP3\n"
"TP4\n"
"TP1 HIT\n"
"TP1 DONE\n"
"TP1 REACHED\n\n"

"Esto significa que el Take Profit fue ALCANZADO.\n"

"Debes responder usando el FORMATO DE ACTUALIZACIÓN:\n"
"✅ XAUUSD/GOLD TP1 ALCANZADO\n\n"

"REGLAS IMPORTANTES:\n"
"- NO incluyas Entrada\n"
"- NO incluyas Stop Loss\n"
"- NO incluyas Operación\n"
"- SOLO envía el formato de actualización\n\n"
"--- FORMATO PARA ACTUALIZACIONES ---\n"
"✅ TP1 ALCANZADO\n"
"✅ TP2 ALCANZADO\n"
"✅ TP3 ALCANZADO\n"
"✅ TP4 ALCANZADO\n"
"✅ STOP LOSS ALCANZADO\n\n"

"16. INTERPRETACIÓN DE ACTUALIZACIONES DE STOP LOSS:\n"
"Si el mensaje contiene:\n"
"SL\n"
"SL HIT\n"
"SL ✅\n"
"STOP LOSS\n"
"STOP LOSS HIT\n"
"STOP LOSS ✅\n"
"🚫SL\n"
"SL TRIGGERED\n\n"

"Significa que el Stop Loss fue alcanzado.\n"
"Responder usando:\n"
"✅ XAUUSD/GOLD STOP LOSS ALCANZADO\n\n"

"17. INTERPRETACIÓN DE BREAK EVEN (SL MOVIDO A ENTRADA):\n"
"Si el mensaje contiene:\n"
"BE\n"
"BREAKEVEN\n"
"SL TO BE\n"
"SL MOVED TO BE\n"
"MOVE SL\n"
"SL MOVED\n\n"

"Significa que el Stop Loss fue movido a Break Even.\n"
"Responder usando:\n"
"✅ STOP LOSS MOVIDO A BREAK EVEN\n\n"

"--- FORMATO PARA ACTUALIZACIONES ---\n"
"✅ TP1 ALCANZADO\n"
"✅ TP2 ALCANZADO\n"
"✅ TP3 ALCANZADO\n"
"✅ TP4 ALCANZADO\n"
"✅ STOP LOSS ALCANZADO\n"
"✅ STOP LOSS MOVIDO A BREAK EVEN\n\n"

    
        )
        
        full_prompt = f"{system_prompt}\n{text}"

        try:
             async with httpx.AsyncClient() as client:
                for attempt in range(2):
                    # Intentar primero con el URL configurado
                    url = self.ai_api_url
                    headers = {"Content-Type": "application/json"}
                    
                    if "googleapis.com" in url:
                        # Formato directo de Google Gemini
                        url = f"{url}?key={self.ai_api_key}"
                        payload = {"contents": [{"parts": [{"text": full_prompt}]}]}
                    else:
                        # Formato Proxy
                        headers["Authorization"] = f"Bearer {self.ai_api_key}"
                        payload = {"message": full_prompt, "model": "apifreellm"}

                    response = await client.post(url, headers=headers, json=payload, timeout=30.0)
                    
                    if response.status_code == 200:
                        if "googleapis.com" in url:
                            resp_text = response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                        else:
                            resp_text = response.json().get('response', '').strip()
                        
                        if resp_text and "REJECT" not in resp_text.upper():
                            return resp_text
                    
                    # Si falla con 401 y es clave de Gemini, intentamos endpoint oficial
                    if response.status_code == 401 and is_gemini_key and "googleapis.com" not in url:
                        logger.warning("Proxy failed with 401. Trying Gemini Direct Endpoint...")
                        self.ai_api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
                        continue
                        
                    await asyncio.sleep(2)
                
                return None
        except Exception as e:
            logger.error(f"AI Filter Exception: {e}")
            return None

    # --- PIPELINE ---
    async def process_message(self, message: Message, priority: int, config: dict):
        source_id = str(message.chat_id)
        msg_id = message.id
        original_text = message.text or ""
        
        logger.info(f"Pipeline: New msg from Source {source_id} (Prio {priority}). Msg ID: {msg_id}")

        # 1. Hard
        clean_1 = self.run_hard_filters(original_text)
        if not clean_1:
            logger.info(f"Pipeline: Msg {msg_id} discarded by Hard Filters.")
            return

        # 2. Logical
        passed, parsed_data = self.run_logical_filters(clean_1, priority)
        if not passed:
            logger.info(f"Pipeline: Msg {msg_id} discarded by Logical Filters.")
            return

        asset = parsed_data["asset"]
        direction = parsed_data["direction"]

        # 3. AI
        final_text = await self.run_ai_filter(clean_1)
            
        if not final_text or "REJECT" in final_text.upper() or len(final_text) > (len(clean_1) * 3 + 100):
            # Check if it's an update (even if direction is missing) or a valid signal
            is_update = any(w in clean_1.upper() for w in ["TP1", "TP2", "TP3", "TP4", "SL", "BE", "BREAKEVEN"])
            
            if (asset and direction) or is_update:
                logger.info(f"Pipeline: AI failed or rejected msg {msg_id}, but it is a valid signal/update. Using manual formatter.")
                # Usa el formateador manual para asegurar el formato base si la IA falla
                final_text = self.format_signal_manually(parsed_data, raw_text=clean_1)
            else:
                logger.warning(f"Pipeline: AI Filter rejected msg {msg_id}. Discarded.")
                return

        # Sanitización Final: Eliminar links y menciones residuales
        final_text = re.sub(r'http[s]?://\S+', '', final_text)
        final_text = re.sub(r't\.me/\S+', '', final_text)
        final_text = re.sub(r'@\S+', '', final_text)
        final_text = final_text.strip()

        # 4. Publish
        dest_id = config.get('dest')
        topic_id = config.get('topic')
        
        try:
            logger.info(f"Pipeline: PUBLISHING Msg {msg_id} to Dest {dest_id} (Topic {topic_id})")
            
            await self.client.send_message(
                dest_id, 
                final_text, 
                reply_to=topic_id
            )
            
            logger.info(f"Pipeline: SUCCESS - Msg {msg_id} replicated to {dest_id}:{topic_id}")
            
            # 5. Save to DB
            signal_entry = {
                "source_id": source_id,
                "msg_id": msg_id,
                "asset": asset,
                "direction": direction,
                "entry_min": parsed_data["entry_min"],
                "entry_max": parsed_data["entry_max"],
                "tp1": parsed_data["tp1"],
                "tp2": parsed_data["tp2"],
                "tp3": parsed_data["tp3"],
                "tp4": parsed_data["tp4"],
                "tp5": parsed_data["tp5"],
                "sl": parsed_data["sl"],
                "raw_text": original_text,
                "formatted_text": final_text
            }
            self.db.save_signal(signal_entry)
                
        except Exception as e:
            logger.error(f"Pipeline: ERROR publishing Msg {msg_id}: {e}")
