import os
import logging
import re
import json
import asyncio
from datetime import datetime, timedelta
import pytz
import httpx
import emoji
from deep_translator import GoogleTranslator
from langdetect import detect, DetectorFactory
DetectorFactory.seed = 0
from telethon import TelegramClient, events
from telethon.tl.types import Message
from config import PROMO_TRIGGERS
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

        # Diccionario de reemplazos manuales específicos
        self.manual_replacements = {
            r"GTS VIP": "👑CLUB 10M",
            r"GTS FAMILY": "👑CLUB 10M",
            r"\bGTS\b": "👑CLUB 10M",
            r"@GoldTraderGTS": "@josejaqueoficial",
            r"@Therealkim44": "@josejaqueoficial",
            r"#44fx": "👑CLUB 10M",
            r"Club 44": "👑CLUB 10M",
            r"44 club": "👑CLUB 10M",
            r"\bclub\b(?!\s*10M)": "👑CLUB 10M",
            r"Sunny": "jose",
            r"\bkim44\b": "Jose",
            r"\bkim\b": "Jose",
            r"\bKim\b": "Jose",
             r"\bKIM\b": "Jose",
            r"fly lagi": "vuela de nuevo",
            r"Jom": "Vamos a",
            r"jom": "vamos a",
            r"clear half": "cerrar la mitad",
            r"Clear half": "Cerrar la mitad",
            # --- DICCIONARIO MALAYO INTEGRADO ---
            # Pronombres y Partículas
            r"\baku\b": "yo", r"\bsaya\b": "yo", r"\bkau\b": "tú", r"\bengkau\b": "tú",
            r"\bdia\b": "él", r"\bmereka\b": "ellos", r"\bkita\b": "nosotros", r"\bkami\b": "nosotros",
            r"\bkorang\b": "ustedes", r"\bdiorang\b": "ellos", r"\bnya\b": "su", r"\bpunya\b": "posesión",
            r"\blah\b": "", r"\bje\b": "solo", r"\bjer\b": "solo", r"\bkah\b": "", 
            r"\bpun\b": "también", r"\bkan\b": "¿verdad?", r"\bni\b": "este", r"\btu\b": "ese",
            # Negación y Afirmación
            r"\btak\b": "no", r"\btk\b": "no", r"\btakde\b": "no hay", r"\bxde\b": "no hay", 
            r"\btidak\b": "no", r"\bbukan\b": "no es", r"\bbetul\b": "correcto", r"\bya\b": "sí", 
            r"\bye\b": "sí", r"\byup\b": "sí", r"\bbaik\b": "bien", r"\bboleh\b": "poder", 
            r"\bblh\b": "poder", r"\bok\b": "bien", r"\bokay\b": "bien",
            # Tiempo
            r"\bsekarang\b": "ahora", r"\bskrg\b": "ahora", r"\btadi\b": "hace poco", r"\btd\b": "hace poco",
            r"\bsemalam\b": "ayer", r"\bmlm\b": "noche", r"\besok\b": "mañana", r"\bnanti\b": "luego",
            r"\bkejap\b": "un momento", r"\bsat\b": "un momento", r"\blama\b": "mucho tiempo", 
            r"\bawal\b": "temprano", r"\blambat\b": "tarde", r"\bbaru\b": "recién", 
            r"\bdulu\b": "antes", r"\bdlu\b": "antes", r"\bselalu\b": "siempre", r"\bkadang\b": "a veces",
            r"\bjarang\b": "rara vez", r"\bdah\b": "ya", r"\bkawtim\b": "Hecho",
            # Verbos
            r"\bmasuk\b": "entrar", r"\bkeluar\b": "salir", r"\bambil\b": "tomar", r"\bbagi\b": "dar",
            r"\bbuat\b": "hacer", r"\bpergi\b": "ir", r"\bdatang\b": "venir", r"\bnaik\b": "subir", 
            r"\bturun\b": "bajar", r"\bjatuh\b": "caer", r"\btunggu\b": "esperar", r"\bikut\b": "seguir", 
            r"\bfaham\b": "entender", r"\bkena\b": "recibir", r"\bjadi\b": "convertirse", r"\bguna\b": "usar", 
            r"\btengok\b": "ver", r"\blihat\b": "ver", r"\bbuka\b": "abrir", r"\btutup\b": "cerrar", 
            r"\bcuba\b": "intentar", r"\bharap\b": "esperar", r"\brasa\b": "sentir",
            # Trading
            r"\bkuat\b": "fuerte", r"\blemah\b": "débil", r"\bbesar\b": "grande", r"\bkecil\b": "pequeño",
            r"\bsikit\b": "poco", r"\bbanyak\b": "mucho", r"\bramai\b": "muchos", r"\bcepat\b": "rápido",
            r"\blaju\b": "veloz", r"\bcantik\b": "limpio", r"\bpadu\b": "sólido", r"\bmantap\b": "excelente",
            r"\bsteady\b": "estable", r"\bconfirm\b": "confirmado", r"\bheavy\b": "fuerte", r"\bclear\b": "claro",
            r"\breject\b": "rechazar", r"\bretest\b": "retest", r"\bpecah\b": "romper", r"\btembus\b": "perforar",
            r"\bpantul\b": "rebotar", r"\breverse\b": "girar", r"\bsapu\b": "barrer", r"lock profit": "asegurar",
            r"ambil profit": "tomar ganancias", r"add lot": "añadir posición", r"topup": "margen", 
            r"\bburn\b": "quemar", r"\bhangus\b": "perder todo", r"margin call": "margin call",
            # Emocionales / Coloquiales
            r"\bgila\b": "extremadamente", r"\bteruk\b": "grave", r"\bparah\b": "severo", r"\bbest\b": "bueno",
            r"\bcun\b": "excelente", r"confirm naik": "subida segura", r"confirm drop": "caída segura",
            r"high chance": "alta probabilidad", r"low risk": "bajo riesgo", r"careful": "cuidado",
            r"hati hati": "cuidado", r"\bjangan\b": "no", r"\bjgn\b": "no", r"\bpanic\b": "pánico",
            r"\bgreedy\b": "codicioso", r"\bfomo\b": "fomo", r"\brelax\b": "tranquilo", r"\bchill\b": "tranquilo",
            r"\bregret\b": "arrepentirse",
            # Condicionales
            r"\bkalau\b": "si", r"\bkalu\b": "si", r"\bklau\b": "si", r"\bjika\b": "si", 
            r"\bif\b": "si", r"\basalkan\b": "siempre que", r"\bselagi\b": "mientras", 
            r"\bsementara\b": "mientras", r"\bbila\b": "cuando", r"\blepas\b": "después", 
            r"\bselepas\b": "después", r"\bbefore\b": "antes", r"\bafter\b": "después",
            # Ubicación / Estructura
            r"\batas\b": "arriba", r"\bbawah\b": "abajo", r"\bkat\b": "en", r"\bkt\b": "en", 
            r"\bdekat\b": "cerca", r"\bdkt\b": "cerca", r"\bdlm\b": "dentro", r"\bluar\b": "fuera",
            r"area ni": "esta zona", r"zone ni": "esta zona", r"level ni": "este nivel",
            "support ni": "este soporte", "resistance ni": "esta resistencia", 
            "structure dah break": "estructura rota", "structure fail": "estructura falló",
            "trend masih": "tendencia todavía", "momentum kuat": "impulso fuerte", "volume sikit": "poco volumen",
            # Mezclas / Abreviaturas
            r"kalau tak": "si no", r"kalau tk": "si no", r"tak hold": "no mantiene", r"tak break": "no rompe",
            r"boleh naik": "puede subir", r"boleh drop": "puede caer", r"boleh fly": "dispararse",
            r"secure profit": "asegurar", r"close sikit": "cerrar parcial", r"partial dulu": "parcial primero",
            r"wait dulu": "esperar primero", r"tunggu dulu": "esperar primero", r"burn account sendiri": "quemar cuenta",
            r"\bmmg\b": "realmente", r"\bmcm\b": "como", r"\bsbb\b": "porque", r"\blg\b": "más",
            r"\borg\b": "persona", r"\bpd\b": "en", r"\bdr\b": "de",
            # --- TÉRMINOS RELIGIOSOS Y ESPIRITUALES ---
            r"\balhamdulillah\b": "Gracias a Dios",
            r"\balhamdulillahhirabbilalamin\b": "gracias a Dios, Señor del universo",
            r"\bsyukur\b": "agradecido", r"\bbersyukur\b": "estar agradecido",
            r"\brezeki\b": "provisión / bendición", r"\bmurahrezeki\b": "abundante provisión",
            r"\binsyaallah\b": "si Dios quiere", r"\binshaallah\b": "si Dios quiere", r"\binsyallah\b": "si Dios quiere",
            r"\bamin\b": "amén", r"\baamiin\b": "amén",
            r"\byaallah\b": "oh Dios", r"\ballah\b": "Dios",
            r"\bsemoga\b": "ojalá", r"\bmoga\b": "ojalá",
            r"\bdipermudahkan\b": "que sea facilitado", r"\bpermudahkan\b": "facilitar",
            r"\bdiizinkan\b": "permitido", r"\bizin\b": "permiso", r"\bizinallah\b": "permiso de Dios",
            r"\btawakal\b": "confiar en Dios", r"\bikhtiar\b": "esfuerzo", r"\busaha\b": "esfuerzo",
            r"\bsabar\b": "paciencia", r"\bbersabar\b": "tener paciencia",
            r"\bredha\b": "aceptar con resignación", r"\breda\b": "aceptar con resignación",
            r"\btakdir\b": "destino", r"\bqada\b": "decreto divino", r"\bqadar\b": "destino divino",
            r"\bdugaan\b": "prueba / dificultad", r"\bujian\b": "prueba",
            r"\bbarakah\b": "bendición", r"\bberkat\b": "bendición", r"\brahmat\b": "misericordia",
            r"\bdoa\b": "oración", r"\bdoakan\b": "rezar por",
            r"\bhalal\b": "permitido", r"\bharam\b": "prohibido",
            r"\bastaghfirullah\b": "pido perdón a Dios", r"\bsubhanallah\b": "gloria a Dios",
            r"\bmasyaallah\b": "lo que Dios ha querido", r"\bmashaallah\b": "lo que Dios ha querido",
            r"\bwallahuaklam\b": "Dios sabe mejor", r"\binsaf\b": "arrepentimiento / conciencia",
            r"\bhijrah\b": "cambio espiritual", r"\bistiqamah\b": "constancia en la fe",
            r"\bsyafaat\b": "intercesión", r"\bakhirat\b": "vida después de la muerte",
            r"\bdunia\b": "mundo terrenal", r"\bfakir\b": "pobre",
            r"\bzakat\b": "caridad obligatoria", r"\bsedekah\b": "caridad", r"\bsedekahsubuh\b": "caridad al amanecer",
            r"\brezekiallah\b": "provisión de Dios", r"\brezekihariini\b": "bendición de hoy",
            r"\bbelumrezeki\b": "aún no es provisión", r"\bbukanrezeki\b": "no es provisión",
            r"\brezekisikit\b": "pequeña bendición", r"\brezekibesar\b": "gran bendición",
            r"\bdenganizin\b": "con permiso", r"\batasizin\b": "por permiso",
            r"\bkurnia\b": "regalo / gracia", r"\bnikmat\b": "bendición",
            r"\bberserah\b": "entregarse", r"\bpasrah\b": "resignarse",
            r"\bquran\b": "Corán", r"\bsunnah\b": "tradición profética"
        }


    def is_in_schedule(self, schedule_config):
        """Verifica si el momento actual está dentro del horario configurado."""
        if not schedule_config:
            return True
        try:
            tz = pytz.timezone(schedule_config.get('timezone', 'America/Bogota'))
            now = datetime.now(tz)
            
            from datetime import time
            current_time = now.time()
            
            start_h, start_m = map(int, schedule_config.get('start', '00:00').split(':'))
            end_h, end_m = map(int, schedule_config.get('end', '23:59').split(':'))
            
            start = time(start_h, start_m)
            end = time(end_h, end_m)
            
            if start <= end:
                return start <= current_time <= end
            else: # Caso de horario que cruza la medianoche
                return current_time >= start or current_time <= end
        except Exception as e:
            logger.error(f"Error checking schedule: {e}")
            return True 

    def apply_manual_filters(self, text, source_name=""):
        """Aplica filtros de reemplazo y descarte (Zoom, reuniones, etc.)"""
        if not text: return None
        
        text_upper = text.upper()
        
        # 1. DESCARTE: Zoom (link o palabra)
        if "ZOOM" in text_upper or "US02WEB.ZOOM.US" in text_upper:
            logger.info("Filtro: Mensaje descartado por contener ZOOM.")
            return None
            
        # 2. DESCARTE: Reuniones/Clases (FXKINGS o similar) - Inglés y Español
        reunion_keywords = [
            "CLASE", "PRINCIPIANTES", "NOS VEMOS EN", "INICIAMOS EN", 
            "MINUTES TO GO", "MINUTOS PARA EMPEZAR", "CLASS", "BEGINNERS",
            "SEE YOU IN", "STARTING IN", "JOIN NOW", "ENTRA YA", "WEBINAR",
            "SESIÓN EN VIVO", "LIVE SESSION"
        ]
        if any(kw in text_upper for kw in reunion_keywords):
            logger.info(f"Filtro: Mensaje de reunión/clase descartado ({source_name}).")
            return None

        # 3. DESCARTE: VIP (Si el mensaje contiene VIP, no se envía)
        if "VIP" in text_upper:
            logger.info(f"Filtro: Mensaje descartado por contener VIP.")
            return None

        # 4. REEMPLAZOS ESPECÍFICOS
        final_text = text
        
        # Primero aplicamos los reemplazos de marcas específicas
        for pattern, replacement in self.manual_replacements.items():
            final_text = re.sub(pattern, replacement, final_text, flags=re.IGNORECASE)
            
        # 4. REEMPLAZOS GENERALES (# y @)
        # - si hay un # se cambia por @josejaqueoficial
        final_text = re.sub(r'#\S+', '@josejaqueoficial', final_text)
        
        # - si hay algún arroba debe ser cambiado por @josejaqueoficial
        # (Esto captura cualquier mención que no haya sido procesada arriba)
        final_text = re.sub(r'@\S+', '@josejaqueoficial', final_text)

        return final_text

    def smart_fragment_translation(self, text: str) -> str:
        """
        Divide el texto en fragmentos, detecta el idioma y traduce solo lo necesario.
        Preserva términos técnicos, URLs y emojis.
        """
        if not text: return ""

        # 1. Dividir el texto respetando los delimitadores
        # Usamos regex para dividir por \n, . (seguido de espacio o fin), !, ? manteniendo los delimitadores
        fragments = re.split(r'(\n|\. |\!|\?)', text)
        
        result_fragments = []
        
        for fragment in fragments:
            if not fragment:
                result_fragments.append("")
                continue
                
            # Si el fragmento es un delimitador, lo dejamos igual
            if fragment in ['\n', '!', '?', '. ']:
                result_fragments.append(fragment)
                continue
                
            clean_fragment = fragment.strip()
            
            # 2. Validar si el fragmento debe ser traducido
            # Un fragmento se considera técnico SOLO si es MUY corto y contiene palabras clave aisladas
            # Si el fragmento tiene más de 5 palabras, probablemente es descriptivo y debe traducirse
            words_in_fragment = [w for w in clean_fragment.split() if len(w) > 1]
            is_long_description = len(words_in_fragment) > 5
            
            is_technical_only = any(re.search(rf'^\b{word}\b$', clean_fragment.upper()) for word in ["BUY", "SELL", "TP", "SL", "ENTRY", "XAUUSD", "GOLD"])
            is_url = re.search(r'http[s]?://\S+|t\.me/\S+', clean_fragment)
            is_only_numbers = re.match(r'^[\d\.\-\s/]+$', clean_fragment) if clean_fragment else False
            
            # Si es una descripción larga, forzamos traducción aunque tenga términos técnicos
            should_translate = clean_fragment and (is_long_description or (not is_technical_only and not is_url and not is_only_numbers))
            
            if should_translate:
                try:
                    # 3. Detectar idioma de forma más flexible
                    # Forzar detección si contiene palabras comunes en inglés
                    common_english = ["the", "and", "investors", "strength", "driver", "today", "uncertainty"]
                    is_english_manual = any(re.search(rf'\b{w}\b', clean_fragment.lower()) for w in common_english)
                    
                    lang = 'en' if is_english_manual else ('ms' if any(w in clean_fragment.lower() for w in ["junam", "kutip", "kita", "lagi", "jom", "fly", "padu"]) else detect(clean_fragment))
                    
                    if lang != 'es':
                        # 4. Traducir usando el método existente
                        translated_fragment = self.translate_manually(fragment)
                        
                        # Si después de traducir todavía detectamos fragmentos comunes de malayo,
                        # aplicamos una traducción forzada palabra por palabra para esos fragmentos.
                        if any(w in translated_fragment.lower() for w in ["junam", "kutip", "kita", "fly"]):
                            translated_fragment = self.translate_word_by_word(translated_fragment)
                            
                        result_fragments.append(translated_fragment)
                    else:
                        result_fragments.append(fragment)
                except Exception as e:
                    # Si falla, intentar traducir por si acaso
                    result_fragments.append(self.translate_manually(fragment))
            else:
                result_fragments.append(fragment)
            
        return "".join(result_fragments)

    def translate_manually(self, text):
        """Traduce el texto usando Google Translate preservando términos técnicos."""
        if not text: return text
        
        try:
            # Lista de términos protegidos que NO queremos traducir
            protected_terms = {
                "XAUUSD/GOLD": "___XAUUSD_GOLD___",
                "XAU/USD": "___XAU_USD___",
                "BUY GOLD": "___BG___",
                "SELL GOLD": "___SG___",
                "BUY": "___B___",
                "SELL": "___S___",
                "STOP LOSS": "___SL___",
                "SL": "___SL___",
                "TP1": "___TP1___",
                "TP2": "___TP2___",
                "TP3": "___TP3___",
                "TP4": "___TP4___",
                "TP5": "___TP5___",
                "TP6": "___TP6___",
                "TAKE PROFIT": "___TP___",
                "ENTRY": "___E___",
                "OPEN": "___O___",
                "BE": "___BE___",
                "BREAK EVEN": "___BE___",
                "XAUUSD": "___XAU___",
                "GOLD": "___G___",
                "HIT": "___HIT___",
                "TP": "___TP___",
            }
            
            # 1. Proteger términos técnicos con placeholders
            temp_text = text
            for term, placeholder in protected_terms.items():
                temp_text = re.sub(rf'\b{term}\b', placeholder, temp_text, flags=re.IGNORECASE)
            
            # 2. Traducir el resto con Google Translate (online, sin API key)
            translator = GoogleTranslator(source='auto', target='es')
            translated = translator.translate(temp_text)
            
            # 3. Restaurar términos técnicos originales
            # Usamos replace directo porque los placeholders son únicos
            for term, placeholder in protected_terms.items():
                translated = translated.replace(placeholder, term)
                
            # Asegurar que "HIT" esté en mayúsculas si el usuario lo prefiere así
            translated = re.sub(rf'\bhit\b', 'HIT', translated, flags=re.IGNORECASE)

            # 0. CORRECCIÓN CRÍTICA: "golpe" -> "HIT"
            # Si el traductor convirtió "Hit" en "golpe" o "Golpe", lo revertimos.
            translated = re.sub(r'\bgolpe\b', 'HIT', translated, flags=re.IGNORECASE)

            # --- POST-TRADUCCIÓN: FILTROS DE SEGURIDAD PARA MALAYO Y NOMBRES ---
            # A veces el traductor revive palabras o no traduce ciertas cosas del malayo.
            # Aquí forzamos una última limpieza.
            
            # 1. Reemplazo forzado de nombres que a veces se escapan (Kim, Sunny)
            translated = re.sub(r'\bkim\b', 'Jose', translated, flags=re.IGNORECASE)
            translated = re.sub(r'\bsunny\b', 'jose', translated, flags=re.IGNORECASE)

            # 2. Reemplazo de palabras malayas residuales comunes (Reforzado)
            malay_residuals = {
                r'\blagi\b': 'de nuevo',
                r'\bjom\b': 'vamos',
                r'\bfly\b': 'vuela',
                r'\bnaik\b': 'sube',
                r'\bturun\b': 'baja',
                r'\bjunam\b': 'bajar/caer',
                r'\bkutip\b': 'recaudar',
                r'\bpadu\b': 'fuerte',
                r'\bmantap\b': 'excelente'
            }
            for pattern, replacement in malay_residuals.items():
                translated = re.sub(pattern, replacement, translated, flags=re.IGNORECASE)
                
            return translated.strip()
            
        except Exception as e:
            logger.error(f"Error en traducción online: {e}")
            # Si falla la traducción online, usamos un reemplazo básico de palabras clave
            return self.basic_fallback_translation(text)

    def translate_word_by_word(self, text):
        """Traduce palabras individuales si la traducción de la frase no fue suficiente."""
        if not text: return text
        words = text.split()
        translated_words = []
        
        # Mapeo rápido orientado a trading malayo
        quick_map = {
            "junam": "caída",
            "kutip": "recaudar",
            "kita": "nosotros",
            "lagi": "más/de nuevo",
            "jom": "vamos",
            "fly": "vuela",
            "padu": "excelente",
            "mantap": "genial",
            "alhamdullilah": "gracias a Dios",
            "alhamdulillah": "gracias a Dios",
            "iftar": "cena de ayuno"
        }
        
        for word in words:
            clean_word = re.sub(r'[^\w]', '', word).lower()
            if clean_word in quick_map:
                # Mantener puntuación si existe
                translated = word.lower().replace(clean_word, quick_map[clean_word])
                translated_words.append(translated)
            else:
                translated_words.append(word)
        
        return " ".join(translated_words)

    def basic_fallback_translation(self, text):
        """Reemplazo simple de palabras clave si falla el traductor online."""
        translations = {
            "new signal": "nueva señal",
            "running": "corriendo",
            "join our channel": "únete a nuestro canal",
            "profit": "ganancias"
        }
        translated = text.lower()
        for eng, esp in translations.items():
            translated = re.sub(rf'\b{eng}\b', esp, translated, flags=re.IGNORECASE)
        return translated.strip()

    async def start(self):
        """Starts listeners for all source channels."""
        source_ids = list(self.replication_map.keys())
        logger.info(f"Listening on sources: {source_ids}")
        
        # Listen to ALL source channels
        @self.client.on(events.NewMessage(chats=source_ids))
        async def handler(event):
            chat_id = event.chat_id
            configs = self.replication_map.get(chat_id)
            
            if not configs:
                logger.warning(f"Message from unknown source ID {chat_id}.")
                return

            # Asegurar que configs sea una lista
            if not isinstance(configs, list):
                configs = [configs]
            
            # Filtrar configs por horario
            valid_configs = [c for c in configs if self.is_in_schedule(c.get('schedule'))]
            
            if valid_configs:
                priority = valid_configs[0].get('priority', 99)
                await self.process_message(event.message, priority, valid_configs)

        logger.info("CLUB 10M Multi-Source Replicator Running...")
        await self.client.run_until_disconnected()

    # --- STAGE: HARD FILTERS ---
    def run_hard_filters(self, text):
        if not text: return None
        
        # 1.3 Promo Trimming (SE MANTIENE)
        lines = text.split('\n')
        clean_lines = []
        for line in lines:
            line_lower = line.lower()
            if any(t in line_lower for t in self.promo_triggers):
                if not any(w in line.upper() for w in ["TP", "SL", "ENTRY", "ENTRADA", "BUY", "SELL", "COMPRA", "VENTA"]):
                    continue 
            clean_lines.append(line)
        
        cleaned_text = "\n".join(clean_lines).strip()
        return cleaned_text if cleaned_text else None

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

    def run_logical_filters(self, text, priority):
        data = self.parse_signal(text)
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
                    return f"✅ CLUB 10M: TP{i} ALCANZADO"
            
            # --- CASO STOP LOSS ---
            sl_keywords = ["SL", "STOP LOSS", "STOPLOSS", "🚫SL"]
            if any(w in text_upper for w in sl_keywords) and not any(w in text_upper for w in ["BE", "BREAKEVEN"]):
                if "HIT" in text_upper or "TRIGGERED" in text_upper or "DONE" in text_upper or len(text_upper) < 20:
                    return "✅ CLUB 10M: STOP LOSS ALCANZADO"

            # --- CASO BREAK EVEN ---
            be_keywords = ["BE", "BREAKEVEN", "BREAK EVEN", "SL TO BE", "MOVE SL", "SL MOVED"]
            if any(w in text_upper for w in be_keywords):
                return "✅ CLUB 10M: STOP LOSS MOVIDO A BREAK EVEN"

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
        
        direction = data.get("direction") or "BUY GOLD"
        if direction.upper() == "COMPRA": direction = "BUY GOLD"
        if direction.upper() == "VENTA": direction = "SELL GOLD"
        
        # Determinar Entrada
        entry_min = data.get('entry_min')
        entry_max = data.get('entry_max')
        
        entry_str = self.clean_num(entry_min)
        if entry_max:
            entry_str += f" - {self.clean_num(entry_max)}"
            
        lines = [
            f"💎 **{asset_display}** | CLUB 10M",
            f"Operación: {direction}",
            f"STOP LOSS: {self.clean_num(data.get('sl'))}",
            f"ENTRY: {entry_str}"
        ]
        
        # TPs (TP1 en adelante)
        for i in range(1, 7):
            tp_val = data.get(f"tp{i}")
            if tp_val:
                # Si es un string con múltiples precios, lo limpiamos un poco
                if isinstance(tp_val, str):
                    tp_val = tp_val.replace("ABIERTO", "OPEN")
                    # Quitar paréntesis innecesarios si es solo una lista
                    tp_val = tp_val.strip("()")
                lines.append(f"TP{i}: {self.clean_num(tp_val)}")
                
        return "\n".join(lines)

    async def run_ai_filter(self, text):
        if not self.ai_api_key: return None
        # Si la clave parece de Google Gemini, intentamos usar el endpoint oficial si el proxy falla
        is_gemini_key = self.ai_api_key.startswith("gen-lang-client") or len(self.ai_api_key) > 30
        
        system_prompt = (
            "Actúa como un experto editor financiero y traductor de señales de trading para CLUB 10M.\n\n"
            "TU OBJETIVO: Traducir íntegramente al ESPAÑOL cualquier análisis de mercado o señal, manteniendo la coherencia técnica y profesional. Translate the entire text to Spanish. Do not leave any English words. Return only Spanish.\n\n"
            "REGLAS CRÍTICAS:\n"
            "1. TRADUCCIÓN TOTAL: Si un mensaje contiene párrafos descriptivos en inglés o malayo, TRADÚCELOS COMPLETOS al español con un tono profesional. Ejemplo: 'The tone stays positive' -> 'El tono se mantiene positivo'.\n"
            "2. PROTECCIÓN TÉCNICA: NO traduzcas ni alteres términos específicos de ejecución: BUY, SELL, ENTRY, SL, TP1-4, GOLD, XAUUSD o los valores numéricos de precio.\n"
            "3. MEJORA DE ESTILO: Corrige errores gramaticales, elimina slang y asegúrate de que el análisis de mercado suene como un informe de un banco de inversión.\n"
            "4. BRANDING: Reemplaza cualquier link, usuario (@) o mención de otros canales por 'CLUB 10M'.\n"
            "5. SIN OMISIONES: No resumas. Traduce cada sección del mensaje original (Impulsores, Resistencia, Apoyo, Sentimiento, etc.).\n"
            "6. DICCIONARIO MALAYO (Si aplica): Traduce términos como 'junam' (caída), 'lagi' (más), 'jom' (vamos), 'kita' (nosotros) al contexto de trading español.\n\n"
            "Mensaje a procesar:"
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
                    
                    logger.info(f"AI: Status {response.status_code} para traducción.")
                    
                    if response.status_code == 200:
                        if "googleapis.com" in url:
                            resp_text = response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                        else:
                            resp_text = response.json().get('response', '').strip()
                        
                        if resp_text:
                            logger.info(f"AI: Traducción exitosa: {resp_text[:50]}...")
                            return resp_text
                    else:
                        logger.error(f"AI: Error en API ({response.status_code}): {response.text}")
                    
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
    async def process_message(self, message: Message, priority: int, configs: list):
        source_id = str(message.chat_id)
        source_name = configs[0].get('name', 'Unknown') if configs else "Unknown"
        msg_id = message.id
        original_text = message.text or ""
        
        # Verificar si al menos un destino permite multimedia si no hay texto
        any_media_allowed = any(c.get('allow_media') for c in configs)
        if not original_text and not (message.media and any_media_allowed):
            return

        # 0. Descartar GIFs completamente (Gif + Texto acompañante)
        if message.gif:
            logger.info(f"Pipeline: Mensaje {msg_id} descartado por ser un GIF.")
            return

        logger.info(f"Pipeline: Procesando mensaje de {source_name} ({source_id}). Msg ID: {msg_id}")

        # 1. Aplicar Filtros Manuales (Reemplazos y descartes por Zoom/Clases)
        text_filtered = self.apply_manual_filters(original_text, source_name)
        if not text_filtered:
            logger.info(f"Pipeline: Mensaje {msg_id} descartado por filtros manuales (Zoom/Clase).")
            return

        # 2. Normalización y Traducción con IA (DESACTIVADO TEMPORALMENTE)
        # ai_text = await self.run_ai_filter(text_filtered)
        # 
        # if ai_text and ai_text.upper() != "REJECT":
        #     final_text = ai_text
        #     logger.info(f"Pipeline: Normalización IA aplicada.")
        # else:
        #     # Fallback a traducción manual si la IA falla o no está configurada
        #     final_text = self.smart_fragment_translation(text_filtered)
        #     logger.info(f"Pipeline: Fallback a traducción manual aplicada.")

        # USAR SOLO TRADUCCIÓN DEL BOT
        final_text = self.smart_fragment_translation(text_filtered)
        logger.info(f"Pipeline: Traducción interna del bot aplicada (IA desactivada).")

        # 3. Sanitización Final (Seguridad extra para links/menciones)
        # Nota: La marca CLUB 10M se aplica aquí sobre cualquier link/mención residual
        # que no haya sido capturado por apply_manual_filters
        final_text = re.sub(r'http[s]?://\S+', '👑CLUB 10M', final_text)
        final_text = re.sub(r't\.me/\S+', '👑CLUB 10M', final_text)
        # Las menciones @ ya fueron manejadas en apply_manual_filters, 
        # pero esto asegura que si aparece algo nuevo sea CLUB 10M
        
        final_text = final_text.strip()

        # Publicar en todos los destinos configurados
        for config in configs:
            dest_id = config.get('dest')
            topic_id = config.get('topic')
            allow_media = config.get('allow_media', False)
            
            # Si el destino no permite media y el mensaje es solo media, saltar
            if not final_text and not (message.media and allow_media):
                continue

            try:
                await self.client.send_message(
                    dest_id, 
                    final_text, 
                    reply_to=topic_id,
                    file=message.media if allow_media else None
                )
                logger.info(f"Pipeline: SUCCESS - Msg {msg_id} enviado a {dest_id}.")
            except Exception as e:
                logger.error(f"Pipeline: ERROR enviando Msg {msg_id} a {dest_id}: {e}")
            
        # Guardar en DB para registro
        try:
            parsed_data = self.parse_signal(original_text)
            signal_entry = {
                "source_id": source_id,
                "msg_id": msg_id,
                "asset": parsed_data.get("asset", "UNKNOWN"),
                "direction": parsed_data.get("direction", "UNKNOWN"),
                "entry_min": parsed_data.get("entry_min"),
                "entry_max": parsed_data.get("entry_max"),
                "tp1": parsed_data.get("tp1"),
                "tp2": parsed_data.get("tp2"),
                "tp3": parsed_data.get("tp3"),
                "tp4": parsed_data.get("tp4"),
                "tp5": parsed_data.get("tp5"),
                "sl": parsed_data.get("sl"),
                "raw_text": original_text,
                "formatted_text": final_text
            }
            self.db.save_signal(signal_entry)
        except Exception as e:
            logger.error(f"Error guardando señal en DB: {e}")
