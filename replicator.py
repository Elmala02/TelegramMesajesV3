import os
import time
import unicodedata
import logging
import re
import json
import asyncio
from datetime import datetime, timedelta
import pytz
import httpx
import emoji
from deep_translator import GoogleTranslator, MyMemoryTranslator
from langdetect import detect, DetectorFactory
DetectorFactory.seed = 0
from telethon import TelegramClient, events
from telethon.tl.types import Message
from config import PROMO_TRIGGERS
from database import TradingDB
import message_cache
import qr_detector
import face_detector

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TelegramReplicator:
    def __init__(self, client: TelegramClient, replication_map):
        self.client = client
        self.replication_map = replication_map # Dict {source_id: {dest, topic, priority}}
        
        # self.db = TradingDB() # Deshabilitado para ahorrar recursos
        
        self.promo_triggers = PROMO_TRIGGERS
        
        self.ai_api_url = os.getenv('AI_API_URL', 'https://apifreellm.com/api/v1/chat')
        self.ai_api_key = os.getenv('AI_API_KEY', '')
        self.gemini_api_key = os.getenv('GEMINI_API_KEY', os.getenv('AI_API_KEY', '')).strip()
        self.gemini_model = os.getenv('GEMINI_MODEL', 'gemini-3.6-flash')
        self._translation_lock = None
        self._last_translation_time = 0.0
        self._last_bot_event_ts = {}
        self._last_edit_as_new_dedupe = {}

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
            r"44['’]?s\s*Club": "👑CLUB 10M",
            r"44['’]?s\s*Clup": "👑CLUB 10M",
            r"#77fx": "👑CLUB 10M",
            r"Club 77": "👑CLUB 10M",
            r"77 club": "👑CLUB 10M",
            r"77['’]?s\s*Club": "👑CLUB 10M",
            r"77['’]?s\s*Clup": "👑CLUB 10M",
            r"77['’]s": "",
            r"\bclub\b(?!\s*10M)": "👑CLUB 10M",
            r"s+u+n{2,}[yi]+(?![a-z])": "jose",
            r"(?<![A-Za-z0-9])s+u+n+y+(?![A-Za-z0-9])": "jose",
            r"(?<![A-Za-z0-9])s+\s*u+\s*n{2,}\s*[yi]+(?![A-Za-z0-9])": "jose",
            r"\bkim44\b": "Jose",
            r"\bkim\b": "Jose",
            r"\bKim\b": "Jose",
            r"\bKIM\b": "Jose",
            r"\bSezir\b": "@josejaqueoficial",
            r"\bsezir\b": "@josejaqueoficial",
            r":Addushi": ":jose",
            r"\bAddushi\b": "jose",
            r"\baddushi\b": "jose",
            r"\bAllah\b": "dios",
            r"\ballah\b": "dios",
            r"\bAKTIV\b": "act",
            r"\baktiv\b": "act",
            r"\bKOTTA\b": "grande",
            r"\bkotta\b": "grande",
            r"fly lagi": "vuela de nuevo",
            r"Jom": "Vamos a",
            r"jom": "vamos a",
            r"clear half": "cerrar la mitad",
            r"Clear half": "Cerrar la mitad",
            r"44['’]s": "",
            r"Nak": "",
            r"Alhamdullilah": "gracias a Dios",
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
            r"\bdulu\b": "primero", r"\bdlu\b": "primero", r"\bselalu\b": "siempre", r"\bkadang\b": "a veces",
            r"\bjarang\b": "rara vez", r"\bdah\b": "ya", r"\bkawtim\b": "Hecho",
            r"\bhold\b": "espera",
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
            r"\bquran\b": "Corán", r"\bsunnah\b": "tradición profética",
            # --- TÉRMINOS UZBEKOS / ASIA CENTRAL Y CIRÍLICO ---
            # Saludos y términos de trading en uzbeko/ruso
            r"\bassalomu?\s+al[ae]y?kum\b": "Saludos",
            r"\bassalom\b": "Saludos",
            r"\bxurmatli\b": "estimados",
            r"\bhurmatli\b": "estimados",
            r"\btraderlar\b": "traders",
            r"\btreyding\b": "trading",
            r"\bsavdo\b": "operación",
            r"\bsavdolar\b": "operaciones",
            r"\bfoyda\s+qildilarmi\??\b": "¿obtuvieron ganancias?",
            r"\bfoyda\b": "ganancia",
            r"\bzarar\b": "pérdida",
            r"\bkirish\b": "entrada",
            r"\bchiqish\b": "salida",
            r"\bkutamiz\b": "esperamos",
            r"\bomad\b": "éxito",
            r"\bbarchaga\s+omad\b": "éxito a todos",
            r"\bdiqqat\b": "atención",
            # Frases religiosas en alfabeto cirílico y variantes
            r"ЛАА\s+ХАВЛА\s+ВА\s+ЛАА\s+КУВВАТА\s+ИЛАА\s+БИЛЛАХИ": "No hay fuerza ni poder excepto en Dios",
            r"лаа\s+хавла\s+ва\s+лаа\s+куввата\s+илаа\s+биллахи": "No hay fuerza ni poder excepto en Dios",
            r"\bla\s+hawla\s+wa\s+la\s+quwwata\s+illa\s+billah\b": "No hay fuerza ni poder excepto en Dios",
            r"\bбисмиллах\b": "En el nombre de Dios",
            r"\bалхамдулиллах\b": "Gracias a Dios",
            r"\биншааллах\b": "Si Dios quiere",
            r"\bмашааллах\b": "Lo que Dios ha querido",
            r"\bсубханаллах\b": "Gloria a Dios"
        }

    def normalize_text(self, text: str) -> str:
        """Normaliza fuentes estilizadas de Telegram (negritas matemáticas, cursivas, etc.) a texto estándar y limpia tags residuales."""
        if not text:
            return ""
        text = unicodedata.normalize('NFKC', text)
        # Limpiar etiquetas HTML de custom emojis o tags corruptos de Telegram
        text = re.sub(r'</?g(?:\s+[^>]*)?>', '', text)
        text = re.sub(r'</?(?:tg-emoji|emoji)(?:\s+[^>]*)?>', '', text)
        return text


    def is_in_schedule(self, schedule_config):
        """Verifica si el momento actual está dentro del horario configurado."""
        if not schedule_config:
            return True
        try:
            tz = pytz.timezone(schedule_config.get('timezone', 'America/Bogota'))
            now = datetime.now(tz)
            
            # Verificar días de la semana (0 = Lunes, 6 = Domingo)
            if 'days' in schedule_config:
                if now.weekday() not in schedule_config['days']:
                    return False
            
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
        text = self.normalize_text(text)
        text_upper = text.upper()

        # Detectar si el mensaje es una SEÑAL TÉCNICA DE TRADING explícita
        # Si es una señal (contiene parámetros de entrada/TP/SL/BUY/SELL/XAUUSD), se protege contra descartes por palabras clave generales.
        signal_keywords = ["SIGNAL:", "ENTRY:", "TAKE PROFIT", "STOP LOSS", "BUY LIMIT", "SELL LIMIT", "BUY STOP", "SELL STOP"]
        signal_terms = ["BUY", "SELL", "ENTRY", "TP", "SL", "SIGNAL"]
        has_signal_format = ("XAUUSD" in text_upper or "GOLD" in text_upper) and any(re.search(rf'\b{re.escape(st)}\b', text_upper) for st in signal_terms)
        is_explicit_signal = has_signal_format or any(sk in text_upper for sk in signal_keywords)
        
        # 0. DESCARTE: Concurso / Sitio Web / Website
        if "CONCURSO" in text_upper or "CONTEST" in text_upper or "GIVEAWAY" in text_upper or "RAFFLE" in text_upper or "SWEEPSTAKE" in text_upper or "SWEEPSTAKES" in text_upper or "COMPETITION" in text_upper or "SITIO WEB" in text_upper or "WEBSITE" in text_upper or "WEB SITE" in text_upper or "WEB-SITE" in text_upper or "SITE-WEB" in text_upper:
            logger.info("Filtro: Mensaje descartado por contener CONCURSO o SITIO WEB/WEBSITE.")
            return None

        # 0.1 DESCARTE: Links de páginas web (HTTP/HTTPS)
        if re.search(r'http[s]?://', text, flags=re.IGNORECASE):
            logger.info("Filtro: Mensaje descartado por contener un link de página web.")
            return None
            
        # 1. DESCARTE: Zoom (link o palabra)
        if "ZOOM" in text_upper or "US02WEB.ZOOM.US" in text_upper:
            logger.info("Filtro: Mensaje descartado por contener ZOOM.")
            return None

        # 1.1 DESCARTE: Palabras no permitidas (billetera, pagos, participantes, wallet, pool, poll)
        if re.search(r'\b(BILLETERA|BILLETERAS|PAGO|PAGOS|PARTICIPANTE|PARTICIPANTES|WALLET|WALLETS|POOL|POOLS|POLL|POLLS)\b', text_upper):
            logger.info("Filtro: Mensaje descartado por contener palabras no permitidas (billetera, pagos, participantes, wallet, pool, poll).")
            return None

        # 1.2 DESCARTE: VIP OPEN, Cupos, Slots (o tragamonedas)
        if re.search(r'\bVIP\s+OPEN\b', text_upper) or re.search(r'\b(CUPO|CUPOS|SLOT|SLOTS|TRAGAMONEDAS)\b', text_upper):
            logger.info("Filtro: Mensaje descartado por contener VIP OPEN, cupos, slots o tragamonedas.")
            return None

        # Si es una señal de trading explícita, OMITIR los descartes de reuniones/VIP/redes sociales
        if not is_explicit_signal:
            # 2. DESCARTE: Reuniones/Clases/Transmisiones/En Vivo (FXKINGS o similar) - Inglés y Español
            reunion_keywords = [
                "CLASE", "PRINCIPIANTES", "NOS VEMOS EN", "INICIAMOS EN", 
                "MINUTES TO GO", "MINUTOS PARA EMPEZAR", "CLASS", "BEGINNERS",
                "SEE YOU IN", "STARTING IN", "JOIN NOW", "ENTRA YA", "WEBINAR",
                "SESIÓN EN VIVO", "LIVE SESSION", "EN VIVO", "AL AIRE", "CRONOGRAMA",
                "BOSINMI", "ONLINE", "ÉTER", "ETER"
            ]
            if any(kw in text_upper for kw in reunion_keywords):
                logger.info(f"Filtro: Mensaje de reunión/clase/en vivo/online descartado ({source_name}).")
                return None

            # 2.1 DESCARTE: Entrevistas con estudiantes en línea
            if any(term in text_upper for term in ["ENTREVISTA", "ESTUDIANTES EN LÍNEA", "ESTUDIANTES EN LINEA", "ENTREVISTA EN LÍNEA", "ENTREVISTA EN LINEA"]):
                logger.info(f"Filtro: Mensaje descartado por tema de entrevista / estudiantes en línea.")
                return None

            # 3. DESCARTE: VIP (Si el mensaje contiene VIP, no se envía)
            if "VIP" in text_upper:
                logger.info(f"Filtro: Mensaje descartado por contener VIP.")
                return None

            # 3.1 DESCARTE: Redes Sociales (Instagram, TikTok, Facebook, Twitter, YouTube, Discord, WhatsApp, Telegram, etc.)
            social_keywords = [
                "INSTAGRAM", "INSTA", "TIKTOK", "TIK TOK", "FACEBOOK", "TWITTER", "X.COM",
                "YOUTUBE", "DISCORD", "SNAPCHAT", "THREADS", "PINTEREST", "LINKEDIN", "WHATSAPP",
                "REDES SOCIALES", "RED SOCIAL", "SOCIAL MEDIA", "MEDIA SOSIAL",
                "SIGUENOS", "SÍGUENOS", "SIGANOS", "SÍGANOS", "SIGANME", "SÍGANME",
                "FOLLOW US", "FOLLOW ME", "FOLLOW OUR", "IKUTI KAMI", "SUBSCRIBE",
                "SUSCRÍBETE", "SUSCRIBETE"
            ]
            for kw in social_keywords:
                if re.search(rf'\b{re.escape(kw)}\b', text_upper):
                    logger.info(f"Filtro: Mensaje descartado por mención de redes sociales ({kw}).")
                    return None

        # 4. REEMPLAZOS ESPECÍFICOS
        final_text = text
        
        # Reemplazar 44fx por club 10 m
        final_text = re.sub(r'44fx\.?', 'club 10 m', final_text, flags=re.IGNORECASE)
        final_text = re.sub(r'77fx\.?', 'club 10 m', final_text, flags=re.IGNORECASE)
        
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

    async def _translate_google_direct(self, text: str) -> str:
        """Traduce texto completo usando el endpoint directo de Google Translate API (rápido, sin scraping)."""
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": "es",
            "dt": "t"
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, params=params, data={"q": text})
            if response.status_code == 200:
                data = response.json()
                if data and isinstance(data, list) and data[0]:
                    translated = "".join(part[0] for part in data[0] if part and part[0])
                    return translated
            elif response.status_code == 429:
                logger.warning("Google Translate API directo devolvió status 429 (Too Many Requests).")
            else:
                logger.warning(f"Google Translate API directo devolvió status {response.status_code}.")
        return None

    def _translate_google_direct_sync(self, text: str) -> str:
        """Versión síncrona de _translate_google_direct."""
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": "es",
            "dt": "t"
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, params=params, data={"q": text})
                if response.status_code == 200:
                    data = response.json()
                    if data and isinstance(data, list) and data[0]:
                        return "".join(part[0] for part in data[0] if part and part[0])
        except Exception as e:
            logger.warning(f"Error en Google Translate directo síncrono: {e}")
        return None

    def get_mymemory_lang(self, lang_code: str) -> str:
        """Convierte código de idioma corto a nombre compatible con MyMemoryTranslator."""
        mapping = {
            'en': 'english',
            'ms': 'malay',
            'ru': 'russian',
            'uz': 'uzbek',
            'id': 'indonesian',
            'fr': 'french',
            'de': 'german',
            'ar': 'arabic',
            'zh': 'chinese simplified',
            'ja': 'japanese',
            'es': 'spanish'
        }
        return mapping.get(str(lang_code).lower() if lang_code else 'en', 'english')

    async def _attempt_translation(self, temp_text, detected_lang):
        """Intenta traducir usando:
        1. Google Translate API directo (ultra rápido y sin bloqueos de scraping).
        2. GoogleTranslator de deep_translator (secundario).
        3. MyMemoryTranslator (terciario).
        """
        if self._translation_lock is None:
            self._translation_lock = asyncio.Lock()
            
        async with self._translation_lock:
            # Control de ráfagas: mínimo 0.5s entre llamadas
            elapsed = time.time() - self._last_translation_time
            if elapsed < 0.5:
                await asyncio.sleep(0.5 - elapsed)
                
            translated = None
            
            # 1. Intentar Google Translate API directo (primario)
            try:
                translated = await self._translate_google_direct(temp_text)
                if translated and isinstance(translated, str) and ("Error 500" in translated or "Server Error" in translated):
                    translated = None
            except Exception as e_gtx:
                logger.warning(f"GoogleTranslate API directo fallo inicial: {e_gtx}. Pasando a traductor secundario.")
                translated = None

            # 2. Intentar deep_translator GoogleTranslator (secundario)
            if not translated or not isinstance(translated, str):
                try:
                    translated = await asyncio.to_thread(
                        lambda: GoogleTranslator(source='auto', target='es').translate(temp_text)
                    )
                    if translated and isinstance(translated, str) and ("Error 500" in translated or "Server Error" in translated):
                        logger.warning("GoogleTranslator devolvió error 500. Pasando a MyMemory.")
                        translated = None
                except Exception as e_gt:
                    logger.warning(f"GoogleTranslator fallo secundario: {e_gt}. Pasando a MyMemory.")
                    translated = None
            
            # 3. Intentar MyMemoryTranslator (terciario)
            if not translated or not isinstance(translated, str):
                try:
                    src_name = self.get_mymemory_lang(detected_lang)
                    translated = await asyncio.to_thread(
                        lambda: MyMemoryTranslator(source=src_name, target='spanish').translate(temp_text)
                    )
                    if translated and isinstance(translated, str) and ("MYMEMORY WARNING" in translated.upper() or "QUOTA EXCEEDED" in translated.upper() or "Error 500" in translated or "INVALID SOURCE" in translated.upper()):
                        logger.warning("MyMemoryTranslator devolvió aviso de límite o error.")
                        translated = None
                except Exception as e_mm:
                    logger.error(f"MyMemoryTranslator fallo también: {e_mm}")
                    translated = None

            self._last_translation_time = time.time()
            return translated

    _PROTECTED_TERMS = [
        (r'(?<![A-Za-z0-9])XAUUSD/GOLD(?![A-Za-z0-9])', 'XTRD01X', 'XAUUSD/GOLD', True),
        (r'(?<![A-Za-z0-9])XAU/USD(?![A-Za-z0-9])', 'XTRD02X', 'XAU/USD', True),
        (r'(?<![A-Za-z0-9])GBP/USD(?![A-Za-z0-9])', 'XTRD34X', 'GBP/USD', True),
        (r'(?<![A-Za-z0-9])GBPUSD(?![A-Za-z0-9])', 'XTRD35X', 'GBPUSD', True),
        (r'(?<![A-Za-z0-9])EUR/USD(?![A-Za-z0-9])', 'XTRD36X', 'EUR/USD', True),
        (r'(?<![A-Za-z0-9])EURUSD(?![A-Za-z0-9])', 'XTRD37X', 'EURUSD', True),
        (r'(?<![A-Za-z0-9])AUD/CAD(?![A-Za-z0-9])', 'XTRD38X', 'AUD/CAD', True),
        (r'(?<![A-Za-z0-9])AUDCAD(?![A-Za-z0-9])', 'XTRD39X', 'AUDCAD', True),
        (r'(?<![A-Za-z0-9])USD/JPY(?![A-Za-z0-9])', 'XTRD40X', 'USD/JPY', True),
        (r'(?<![A-Za-z0-9])USDJPY(?![A-Za-z0-9])', 'XTRD41X', 'USDJPY', True),
        (r'(?<![A-Za-z0-9])TRADE\s+SL(?![A-Za-z0-9])', 'XTRD42X', 'TRADE SL', True),
        (r'(?<![A-Za-z0-9])HARD\s+SL(?![A-Za-z0-9])', 'XTRD43X', 'HARD SL', True),
        (r'(?<![A-Za-z0-9])HIGH\s+RR(?![A-Za-z0-9])', 'XTRD44X', 'HIGH RR', True),
        (r'(?<![A-Za-z0-9])SCALP(?![A-Za-z0-9])', 'XTRD45X', 'SCALP', True),
        (r'(?<![A-Za-z0-9])M5(?![A-Za-z0-9])', 'XTRD46X', 'M5', False),
        (r'(?<![A-Za-z0-9])M15(?![A-Za-z0-9])', 'XTRD47X', 'M15', False),
        (r'(?<![A-Za-z0-9])M30(?![A-Za-z0-9])', 'XTRD48X', 'M30', False),
        (r'(?<![A-Za-z0-9])H1(?![A-Za-z0-9])', 'XTRD49X', 'H1', False),
        (r'(?<![A-Za-z0-9])H4(?![A-Za-z0-9])', 'XTRD50X', 'H4', False),
        (r'(?<![A-Za-z0-9])BUY\s+GOLD(?![A-Za-z0-9])', 'XTRD03X', 'BUY GOLD', True),
        (r'(?<![A-Za-z0-9])SELL\s+GOLD(?![A-Za-z0-9])', 'XTRD04X', 'SELL GOLD', True),
        (r'(?<![A-Za-z0-9])BUY\s+LIMIT(?![A-Za-z0-9])', 'XTRD05X', 'BUY LIMIT', True),
        (r'(?<![A-Za-z0-9])SELL\s+LIMIT(?![A-Za-z0-9])', 'XTRD06X', 'SELL LIMIT', True),
        (r'(?<![A-Za-z0-9])BUY\s+STOP(?![A-Za-z0-9])', 'XTRD07X', 'BUY STOP', True),
        (r'(?<![A-Za-z0-9])SELL\s+STOP(?![A-Za-z0-9])', 'XTRD08X', 'SELL STOP', True),
        (r'(?<![A-Za-z0-9])TAKE[\s_-]*PROFIT(?![A-Za-z0-9])', 'XTRD09X', 'TAKE PROFIT', True),
        (r'(?<![A-Za-z0-9])STOP[\s_-]*LOSS(?![A-Za-z0-9])', 'XTRD10X', 'STOP LOSS', True),
        (r'(?<![A-Za-z0-9])SL\s+TO\s+BE(?![A-Za-z0-9])', 'XTRD11X', 'SL a BE', True),
        (r'(?<![A-Za-z0-9])POSITIONS?\s+(?:IN|TO|AT)\s+BE(?![A-Za-z0-9])', 'XTRD33X', 'posiciones en BE', True),
        (r'(?<![A-Za-z0-9])BREAK[\s_-]*EVEN(?![A-Za-z0-9])', 'XTRD12X', 'BE', True),
        (r'(?<![A-Za-z0-9])BE(?![A-Za-z0-9])', 'XTRD13X', 'BE', False),
        (r'(?<![A-Za-z0-9])BUY(?![A-Za-z0-9])', 'XTRD14X', 'BUY', True),
        (r'(?<![A-Za-z0-9])SELL(?![A-Za-z0-9])', 'XTRD15X', 'SELL', True),
        (r'(?<![A-Za-z0-9])SL(?![A-Za-z0-9])', 'XTRD16X', 'SL', True),
        (r'(?<![A-Za-z0-9])TP10(?![A-Za-z0-9])', 'XTRD17X', 'TP10', True),
        (r'(?<![A-Za-z0-9])TP1(?![A-Za-z0-9])', 'XTRD18X', 'TP1', True),
        (r'(?<![A-Za-z0-9])TP2(?![A-Za-z0-9])', 'XTRD19X', 'TP2', True),
        (r'(?<![A-Za-z0-9])TP3(?![A-Za-z0-9])', 'XTRD20X', 'TP3', True),
        (r'(?<![A-Za-z0-9])TP4(?![A-Za-z0-9])', 'XTRD21X', 'TP4', True),
        (r'(?<![A-Za-z0-9])TP5(?![A-Za-z0-9])', 'XTRD22X', 'TP5', True),
        (r'(?<![A-Za-z0-9])TP6(?![A-Za-z0-9])', 'XTRD23X', 'TP6', True),
        (r'(?<![A-Za-z0-9])TP7(?![A-Za-z0-9])', 'XTRD24X', 'TP7', True),
        (r'(?<![A-Za-z0-9])TP8(?![A-Za-z0-9])', 'XTRD25X', 'TP8', True),
        (r'(?<![A-Za-z0-9])TP9(?![A-Za-z0-9])', 'XTRD26X', 'TP9', True),
        (r'(?<![A-Za-z0-9])ENTRY(?![A-Za-z0-9])', 'XTRD27X', 'ENTRY', True),
        (r'(?<![A-Za-z0-9])OPEN(?![A-Za-z0-9])', 'XTRD28X', 'OPEN', True),
        (r'(?<![A-Za-z0-9])XAUUSD(?![A-Za-z0-9])', 'XTRD29X', 'XAUUSD', True),
        (r'(?<![A-Za-z0-9])GOLD(?![A-Za-z0-9])', 'XTRD30X', 'GOLD', True),
        (r'(?<![A-Za-z0-9])HIT(?![A-Za-z0-9])', 'XTRD31X', 'HIT', True),
        (r'(?<![A-Za-z0-9])TP(?![A-Za-z0-9])', 'XTRD32X', 'TP', True),
    ]

    def _protect_trading_terms(self, text: str) -> str:
        """Reemplaza términos técnicos por códigos opacos antes de traducir (resiste cursivas _ y negritas *)."""
        temp_text = text
        for pattern, placeholder, _, ignore_case in self._PROTECTED_TERMS:
            flags = re.IGNORECASE if ignore_case else 0
            temp_text = re.sub(pattern, placeholder, temp_text, flags=flags)
        return temp_text

    def _postprocess_translation(self, translated: str) -> str:
        """Restaura términos protegidos y corrige traducciones indeseadas."""
        for _, placeholder, restore_value, _ in self._PROTECTED_TERMS:
            translated = re.sub(re.escape(placeholder), restore_value, translated, flags=re.IGNORECASE)

        translated = re.sub(r'(?<![A-Za-z0-9])OBTENCI[OÓ]N DE BENEFICIOS(?![A-Za-z0-9])', 'TAKE PROFIT', translated, flags=re.IGNORECASE)
        translated = re.sub(r'(?<![A-Za-z0-9])TOMA DE GANANCIAS(?![A-Za-z0-9])', 'TAKE PROFIT', translated, flags=re.IGNORECASE)
        translated = re.sub(r'\bPG(\d+)\b', r'TP\1', translated, flags=re.IGNORECASE)
        translated = re.sub(r'\bPG\b', 'TP', translated, flags=re.IGNORECASE)

        # Corrección anti-SER/ESTAR para BE (Break Even)
        translated = re.sub(r'\b(a|en|hacia)\s+ser\b', r'\1 BE', translated, flags=re.IGNORECASE)
        translated = re.sub(r'\b(a|en|hacia)\s+estar\b', r'\1 BE', translated, flags=re.IGNORECASE)
        translated = re.sub(r'\b(poner|set|mover|ajustar|cambiar|posicion(?:es)?|posici(?:o|ó)n(?:es)?|sl|stop\s*loss)\s+ser\b', r'\1 BE', translated, flags=re.IGNORECASE)
        translated = re.sub(r'\b(poner|set|mover|ajustar|cambiar|posicion(?:es)?|posici(?:o|ó)n(?:es)?|sl|stop\s*loss)\s+estar\b', r'\1 BE', translated, flags=re.IGNORECASE)

        translated = re.sub(r'\bhit\b', 'HIT', translated, flags=re.IGNORECASE)
        translated = re.sub(r'_*golpe_*', 'HIT', translated, flags=re.IGNORECASE)
        translated = re.sub(r'\bkim\b', 'Jose', translated, flags=re.IGNORECASE)
        translated = re.sub(r's+u+n{2,}[yi]+(?![a-z])', 'jose', translated, flags=re.IGNORECASE)
        translated = re.sub(r'(?<![A-Za-z0-9])s+u+n+y+(?![A-Za-z0-9])', 'jose', translated, flags=re.IGNORECASE)

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

        return self.apply_spanish_terms(translated.strip())

    async def translate_manually_async(self, text, detected_lang='en'):
        """Traduce el texto completo de forma asíncrona en UNA SOLA llamada preservando términos técnicos.
        Incluye reintentos con backoff si la red falla."""
        if not text: return text
        
        try:
            temp_text = self._protect_trading_terms(text)
            
            # Reintentos con backoff exponencial (3s, 6s, 12s)
            max_retries = 3
            retry_delays = [3, 6, 12]
            translated = None

            for attempt in range(max_retries + 1):
                translated = await self._attempt_translation(temp_text, detected_lang)
                
                if translated and isinstance(translated, str):
                    if attempt > 0:
                        logger.info(f"Traducción exitosa en intento {attempt + 1} después de reintentos.")
                    break
                
                if attempt < max_retries:
                    delay = retry_delays[attempt]
                    logger.warning(f"Traducción fallida (intento {attempt + 1}/{max_retries + 1}). Reintentando en {delay}s...")
                    await asyncio.sleep(delay)

            # Si todos los reintentos fallaron, retornar None para no enviar mensajes sin traducir
            if not translated or not isinstance(translated, str):
                logger.error(f"Fallo definitivo asíncrono tras {max_retries + 1} intentos: Todos los traductores fallaron.")
                return None

            return self._postprocess_translation(translated)
            
        except Exception as e:
            logger.error(f"Excepción en traducción asíncrona: {e}")
            return None

    async def smart_fragment_translation_async(self, text: str) -> str:
        """
        Traduce el mensaje completo de forma asíncrona en UNA SOLA llamada,
        protegiendo términos técnicos, marcas, números y emojis.
        Retorna None si la traducción falla por completo (para evitar enviar textos en inglés).
        """
        if not text: return ""
        text = self.normalize_text(text)
        
        # Validar si contiene palabras comunes en inglés o malayo
        common_english = ["the", "and", "investors", "strength", "driver", "today", "uncertainty", "running", "spike", "secured", "news", "ready", "now", "manage", "risk", "wait", "break", "even", "take", "profit", "positions", "position"]
        is_english_manual = any(re.search(r'\b' + re.escape(w) + r'\b', text.lower()) for w in common_english)
        is_malay = any(w in text.lower() for w in ["junam", "kutip", "kita", "lagi", "jom", "fly", "padu"])
        
        try:
            lang = 'en' if is_english_manual else ('ms' if is_malay else detect(text))
        except Exception:
            lang = 'en'
            
        # Si ya está en español y no contiene palabras residuales en inglés o malayo, no requiere traducción
        if lang == 'es' and not is_english_manual and not is_malay:
            return text
            
        # Traducir todo el mensaje en UNA SOLA llamada a Google
        translated = await self.translate_manually_async(text, detected_lang=lang)
        if translated is None:
            logger.error("Fallo crítico en traducción asíncrona del mensaje. Cancelando mensaje.")
            return None
            
        if any(w in translated.lower() for w in ["junam", "kutip", "kita", "fly"]):
            translated = self.translate_word_by_word(translated)
            
        return translated

    def translate_manually(self, text, detected_lang='en'):
        """Versión síncrona de translate_manually para compatibilidad."""
        if not text: return text
        try:
            temp_text = self._protect_trading_terms(text)
            
            translated = self._translate_google_direct_sync(temp_text)
            if not translated:
                try:
                    translated = GoogleTranslator(source='auto', target='es').translate(temp_text)
                except Exception:
                    translated = None
            if not translated:
                try:
                    src_name = self.get_mymemory_lang(detected_lang)
                    translated = MyMemoryTranslator(source=src_name, target='spanish').translate(temp_text)
                except Exception:
                    translated = None
                    
            if not translated or not isinstance(translated, str):
                return None

            return self._postprocess_translation(translated)
        except Exception as e:
            logger.error(f"Excepción en traducción manual: {e}")
            return None

    def smart_fragment_translation(self, text: str) -> str:
        """Versión síncrona de smart_fragment_translation para compatibilidad."""
        if not text: return ""
        text = self.normalize_text(text)
        return self.translate_manually(text)


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
            "iftar": "cena de ayuno",
            "assalom": "saludos",
            "xurmatli": "estimados",
            "hurmatli": "estimados",
            "traderlar": "traders",
            "savdo": "operación",
            "foyda": "ganancia",
            "zarar": "pérdida",
            "omad": "éxito"
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

    def apply_spanish_terms(self, text):
        if not text: return text
        try:
            force = str(os.getenv('FORCE_SPANISH_TERMS', 'false')).lower() in ['true', '1', 'yes', 'on']
            if not force: return text
            patterns = [
                (r'\bBREAK\s*EVEN\b', 'BE')
            ]
            out = text
            for p, r in patterns:
                out = re.sub(p, r, out, flags=re.IGNORECASE)
            return out
        except:
            return text

    def _is_loading_placeholder(self, text: str) -> bool:
        """Detecta mensajes temporales de carga al hacer clic en REFRESH (ej. '⏳ Refreshing...')."""
        if not text:
            return True
        clean = text.strip().lower()
        loading_markers = [
            "refreshing", "loading", "cargando", "actualizando", 
            "calculating", "calculando", "please wait", "espere", "⏳", "🔄"
        ]
        is_loading = any(m in clean for m in loading_markers)
        # Una señal completa real SIEMPRE tiene niveles de TP y Stop Loss
        has_complete_signal = any(f"tp{i}" in clean for i in range(1, 4)) and any(s in clean for s in ["sl", "stop loss", "trade sl"])
        if is_loading and not has_complete_signal:
            return True
        return False

    async def _get_configs_for_event(self, event):
        chat_id = event.chat_id
        configs = self.replication_map.get(chat_id)
        if not configs:
            try:
                chat = await event.get_chat()
                username = getattr(chat, 'username', None)
                if username:
                    configs = self.replication_map.get(f"@{username}") or self.replication_map.get(username)
            except Exception as e_chat:
                logger.debug(f"Error obteniendo chat para fallback de username: {e_chat}")
        if not configs:
            return []
        return configs if isinstance(configs, list) else [configs]

    def _find_button_coords(self, msg, pattern: str):
        """Busca un botón inline por regex en el mensaje y devuelve (row, col, text)."""
        if not msg or not getattr(msg, 'buttons', None):
            return None
        for r_idx, row in enumerate(msg.buttons):
            for c_idx, btn in enumerate(row):
                btn_text = (getattr(btn, 'text', '') or '').strip()
                if re.search(pattern, btn_text, re.IGNORECASE):
                    return (r_idx, c_idx, btn_text)
        return None

    def _validate_mind_quality(self, text: str, config: dict) -> tuple:
        """Verifica si la señal de NeuralTrade/Mind cumple con el indicador verde y la confianza mínima."""
        if not text:
            return False, "Texto vacío"

        first_lines = "\n".join(text.strip().splitlines()[:3]).upper()
        if config.get('require_green_indicator'):
            has_green = '🟢' in first_lines or 'CONDICIONES CUMPLIDAS' in first_lines
            is_yellow = '🟡' in first_lines or 'WITHIN LIMITS' in first_lines or 'DENTRO DE LÍMITES' in first_lines or 'DENTRO DE LIMITES' in first_lines
            if is_yellow or not has_green:
                det = "🟡 (Amarillo)" if is_yellow else "sin botón 🟢"
                return False, f"Indicador no es verde (detectado: {det})"

        min_conf = config.get('min_direction_confidence')
        if min_conf is not None:
            conf_m = re.search(r'(?:Direction\s*Confidence|Confianza\s*en\s*la\s*direcci[óo]n)[:\s]*(\d+)', text, re.I)
            if not conf_m:
                return False, "No se detectó porcentaje de 'Direction Confidence'"
            conf_val = int(conf_m.group(1))
            if conf_val < min_conf:
                return False, f"Confianza de dirección {conf_val}% es menor al mínimo requerido ({min_conf}%)"

        return True, "Cumple indicador verde y confianza requerida"

    def _get_timeframe_for_minute(self, minute: int) -> str:
        """Determina la temporalidad según el minuto de la hora (:00 -> H1, :15 -> M15, :30 -> M30, :45 -> M15)."""
        if 53 <= minute or minute < 8:
            return "H1"
        elif 8 <= minute < 23:
            return "M15"
        elif 23 <= minute < 38:
            return "M30"
        else: # 38 <= minute < 53
            return "M15"

    async def _trigger_refresh_once(self, source_key, refresh_cfgs, reason="Auto-Refresh", override_tf=None):
        """Hace clic en el botón REFRESH del último mensaje del bot (asegurando activo y temporalidad) y garantiza envío."""
        source_name = refresh_cfgs[0].get('name', str(source_key))
        btn_keyword = str(refresh_cfgs[0].get('refresh_button_text', 'REFRESH')).upper()

        valid_configs = [c for c in refresh_cfgs if self.is_in_schedule(c.get('schedule'))]
        if not valid_configs:
            logger.info(f"{reason} ({source_name}): Fuera de horario configurado, omitiendo ciclo.")
            return

        target_msg = None
        async for msg in self.client.iter_messages(source_key, limit=15):
            if msg.out or not msg.buttons:
                continue
            target_msg = msg
            break

        if not target_msg:
            logger.warning(
                f"{reason} ({source_name}): No se encontró mensaje reciente con botones interactivos."
            )
            return

        # 1. Asegurar Activo (ej: XAUUSD / GOLD) si está configurado
        target_asset = refresh_cfgs[0].get('target_asset_button')
        if target_asset:
            txt_now = (target_msg.text or "").upper()
            if not any(k in txt_now for k in ["XAU", "GOLD", "ORO"]):
                coords_asset = self._find_button_coords(target_msg, rf'\b{re.escape(target_asset)}\b|XAU\s*/?\s*USD|\bGOLD\b')
                if coords_asset:
                    logger.info(f"{reason} ({source_name}): Seleccionando activo {target_asset} (botón '{coords_asset[2]}')...")
                    try:
                        await target_msg.click(coords_asset[0], coords_asset[1])
                        await asyncio.sleep(2.5)
                        fresh_asset = await self.client.get_messages(source_key, ids=target_msg.id)
                        if fresh_asset and fresh_asset.buttons:
                            target_msg = fresh_asset
                    except Exception as e_asset:
                        logger.warning(f"{reason} ({source_name}): Aviso al seleccionar {target_asset}: {e_asset}")

        # 2. Asegurar Temporalidad (ej: H1, M15, M30) si está configurada o solicitada por ciclo
        target_tf = override_tf or refresh_cfgs[0].get('target_timeframe_button')
        if target_tf:
            txt_now = (target_msg.text or "").upper()
            if not re.search(rf'\({re.escape(target_tf)}\)', txt_now):
                coords_tf = self._find_button_coords(target_msg, rf'^(?:⏰\s*)?{re.escape(target_tf)}$|\b{re.escape(target_tf)}\b')
                if coords_tf:
                    logger.info(f"{reason} ({source_name}): Cambiando temporalidad a {target_tf} (botón '{coords_tf[2]}')...")
                    try:
                        await target_msg.click(coords_tf[0], coords_tf[1])
                        await asyncio.sleep(2.5)
                        fresh_tf = await self.client.get_messages(source_key, ids=target_msg.id)
                        if fresh_tf and fresh_tf.buttons:
                            target_msg = fresh_tf
                    except Exception as e_tf:
                        logger.warning(f"{reason} ({source_name}): Aviso al cambiar a temporalidad {target_tf}: {e_tf}")

        # 3. Presionar botón REFRESH
        coords_refresh = self._find_button_coords(target_msg, rf'{re.escape(btn_keyword)}')
        if not coords_refresh:
            for r_idx, row in enumerate(target_msg.buttons or []):
                for c_idx, btn in enumerate(row):
                    b_txt = (getattr(btn, 'text', '') or '').upper()
                    if btn_keyword in b_txt:
                        coords_refresh = (r_idx, c_idx, b_txt)
                        break
                if coords_refresh:
                    break

        if not coords_refresh:
            logger.warning(f"{reason} ({source_name}): No se encontró botón '{btn_keyword}' tras verificar opciones.")
            return

        ts_before = time.time()
        logger.info(
            f"{reason} ({source_name}): Haciendo clic en botón '{coords_refresh[2]}' del Msg {target_msg.id}..."
        )
        try:
            await target_msg.click(coords_refresh[0], coords_refresh[1])
        except Exception as e_click:
            logger.warning(f"{reason} ({source_name}): Aviso al hacer clic en '{btn_keyword}': {e_click}")

        # Esperar a que el bot termine de calcular y edite o envíe el mensaje (7s)
        await asyncio.sleep(7)

        # Buscar si envió un mensaje nuevo o si editó el mensaje actual
        latest_msgs = await self.client.get_messages(source_key, limit=3)
        msg_to_send = None
        for m in (latest_msgs or []):
            if not getattr(m, 'out', False) and not self._is_loading_placeholder(m.text or ""):
                msg_to_send = m
                break
        if not msg_to_send:
            fresh_msg = await self.client.get_messages(source_key, ids=target_msg.id)
            msg_to_send = fresh_msg if fresh_msg else target_msg

        if msg_to_send and not self._is_loading_placeholder(msg_to_send.text or ""):
            priority = valid_configs[0].get('priority', 99)
            await self.process_message(msg_to_send, priority, valid_configs)

    async def _timeframe_cycle_loop(self, source_key, cycle_cfgs):
        """Ejecuta el ciclo de temporalidades (:00 -> H1, :15 -> M15, :30 -> M30, :45 -> M15) sincronizado al reloj."""
        source_name = cycle_cfgs[0].get('name', str(source_key))
        logger.info(
            f"Timeframe-Cycle: Iniciado para {source_name} "
            f"(:00 -> H1, :15 -> M15, :30 -> M30, :45 -> M15)."
        )

        # Disparo inicial tras 4s para calibrar temporalidad del minuto actual
        try:
            await asyncio.sleep(4)
            now_dt = datetime.now()
            init_tf = self._get_timeframe_for_minute(now_dt.minute)
            logger.info(f"Timeframe-Cycle ({source_name}): Disparo inicial calibrando temporalidad {init_tf}...")
            await self._trigger_refresh_once(source_key, cycle_cfgs, reason=f"Cycle-Init ({init_tf})", override_tf=init_tf)
        except asyncio.CancelledError:
            return
        except Exception as e_init:
            logger.warning(f"Timeframe-Cycle ({source_name}): Aviso en ciclo inicial: {e_init}")

        while True:
            try:
                # Calcular tiempo exacto hasta el siguiente cuarto de hora (:00, :15, :30, :45)
                now_dt = datetime.now()
                sec_in_hour = now_dt.minute * 60 + now_dt.second + (now_dt.microsecond / 1_000_000.0)
                checkpoints = [0, 900, 1800, 2700, 3600]
                next_cp = None
                for cp in checkpoints:
                    if cp > sec_in_hour + 2.0:
                        next_cp = cp
                        break
                if next_cp is None:
                    next_cp = 3600

                sleep_seconds = max(5.0, next_cp - sec_in_hour)
                target_min = int((next_cp % 3600) / 60)
                next_tf = self._get_timeframe_for_minute(target_min)
                logger.info(
                    f"Timeframe-Cycle ({source_name}): Próxima consulta a las :{target_min:02d} ({next_tf}) "
                    f"en {sleep_seconds:.1f} segundos."
                )

                await asyncio.sleep(sleep_seconds)

                # Llegamos al checkpoint: determinar temporalidad y disparar refresh
                cur_dt = datetime.now()
                target_tf = self._get_timeframe_for_minute(cur_dt.minute)
                logger.info(f"Timeframe-Cycle ({source_name}): Ejecutando consulta de :{cur_dt.minute:02d} para {target_tf}...")
                await self._trigger_refresh_once(
                    source_key, 
                    cycle_cfgs, 
                    reason=f"Timeframe-Cycle ({target_tf})", 
                    override_tf=target_tf
                )
            except asyncio.CancelledError:
                logger.info(f"Timeframe-Cycle ({source_name}): Tarea cancelada.")
                break
            except Exception as e:
                logger.error(f"Timeframe-Cycle ({source_name}): Error en ciclo: {e}")
                await asyncio.sleep(30)

    async def _auto_refresh_loop(self, source_key, refresh_cfgs, interval_minutes: float):
        """Presiona automáticamente el botón REFRESH en bots interactivos cada N minutos."""
        interval_seconds = max(60, int(interval_minutes * 60))
        source_name = refresh_cfgs[0].get('name', str(source_key))
        btn_keyword = str(refresh_cfgs[0].get('refresh_button_text', 'REFRESH')).upper()
        logger.info(
            f"Auto-Refresh: Iniciado para {source_name} ({source_key}) cada {interval_minutes} min "
            f"(botón '{btn_keyword}')."
        )

        # Disparo inicial tras 5 segundos de arranque para asegurar que el bot esté en el activo y temporalidad deseados
        try:
            await asyncio.sleep(5)
            await self._trigger_refresh_once(source_key, refresh_cfgs, reason="Auto-Refresh-Initial")
        except asyncio.CancelledError:
            return
        except Exception as e_init:
            logger.warning(f"Auto-Refresh ({source_name}): Aviso en ciclo inicial: {e_init}")

        while True:
            try:
                await asyncio.sleep(interval_seconds)
                await self._trigger_refresh_once(source_key, refresh_cfgs, reason="Auto-Refresh")
            except asyncio.CancelledError:
                logger.info(f"Auto-Refresh ({source_name}): Tarea cancelada.")
                break
            except Exception as e:
                logger.error(f"Auto-Refresh ({source_name}): Error en ciclo automático: {e}")

    async def start(self):
        """Starts listeners for all source channels."""
        # Identificar IDs enteros resueltos y posibles usernames pendientes (evita que un @username roto bloquee Telethon)
        resolved_int_sources = {k for k in self.replication_map.keys() if isinstance(k, int)}
        unresolved_str_sources = {
            k for k, v in self.replication_map.items()
            if isinstance(k, str) and not any(isinstance(ik, int) and iv is v for ik, iv in self.replication_map.items())
        }
        logger.info(f"Listening on resolved int sources: {sorted(resolved_int_sources)}")
        if unresolved_str_sources:
            logger.warning(f"Unresolved string sources (fallback por username): {sorted(unresolved_str_sources)}")

        # Recolectar fuentes con auto-refresh y con timeframe-cycle (deduplicadas por objeto de configuración)
        cycle_targets = []
        started_cycle_keys = set()
        refresh_targets = []
        started_refresh_keys = set()
        for src_key, cfgs in self.replication_map.items():
            if isinstance(src_key, str) and any(
                isinstance(k, int) and v is cfgs for k, v in self.replication_map.items()
            ):
                continue
            cfg_list = cfgs if isinstance(cfgs, list) else [cfgs]

            # 1. Ciclo de temporalidades por hora (:00 H1, :15 M15, :30 M30, :45 M15)
            cycle_cfgs = [c for c in cfg_list if c.get('timeframe_cycle')]
            if cycle_cfgs and src_key not in started_cycle_keys:
                started_cycle_keys.add(src_key)
                cycle_targets.append((src_key, cycle_cfgs))

            # 2. Auto-refresh regular si no usa timeframe_cycle
            refresh_cfgs = [c for c in cfg_list if c.get('auto_refresh_minutes') and not c.get('timeframe_cycle')]
            if refresh_cfgs and src_key not in started_refresh_keys:
                started_refresh_keys.add(src_key)
                interval_min = min(float(c['auto_refresh_minutes']) for c in refresh_cfgs)
                refresh_targets.append((src_key, refresh_cfgs, interval_min))

        # Listen to ALL new messages (filtrando en Python para máxima confiabilidad con bots y canales)
        @self.client.on(events.NewMessage())
        async def handler(event):
            # Comando manual instantáneo: escribir /refresh o !refresh desde tu cuenta fuerza el refresh + envío
            raw_txt = (event.message.text or "").strip().lower()
            if getattr(event.message, 'out', False) and raw_txt in ("/refresh", "!refresh") and (refresh_targets or cycle_targets):
                logger.info(f"Manual-Refresh: Comando '{raw_txt}' detectado. Ejecutando refresh inmediato...")
                for src_key, refresh_cfgs, _ in refresh_targets:
                    asyncio.create_task(self._trigger_refresh_once(src_key, refresh_cfgs, reason="Manual-Refresh"))
                for src_key, cycle_cfgs in cycle_targets:
                    now = datetime.now()
                    tf = self._get_timeframe_for_minute(now.minute)
                    asyncio.create_task(self._trigger_refresh_once(src_key, cycle_cfgs, reason=f"Manual-Refresh ({tf})", override_tf=tf))
                return

            if event.chat_id not in resolved_int_sources and not unresolved_str_sources:
                return

            configs = await self._get_configs_for_event(event)
            if not configs:
                return
            
            # Filtrar configs por horario y por incoming_only (ignorar mensajes salientes como /start en bots)
            valid_configs = [
                c for c in configs
                if self.is_in_schedule(c.get('schedule'))
                and not (c.get('incoming_only') and getattr(event.message, 'out', False))
            ]
            
            if valid_configs:
                if any(c.get('edit_as_new') for c in valid_configs) and self._is_loading_placeholder(event.message.text or ""):
                    logger.info(f"NewMessage: Ignorando mensaje temporal de carga en {event.chat_id}.")
                    return
                self._last_bot_event_ts[str(event.chat_id)] = time.time()
                priority = valid_configs[0].get('priority', 99)
                await self.process_message(event.message, priority, valid_configs)


        # Handler para MENSAJES EDITADOS (sin chats= para evitar fallos de resolución de Telethon)
        @self.client.on(events.MessageEdited())
        async def edit_handler(event):
            if event.chat_id not in resolved_int_sources and not unresolved_str_sources:
                return

            configs = await self._get_configs_for_event(event)
            if not configs:
                return

            edit_as_new_configs = [
                c for c in configs
                if c.get('edit_as_new')
                and self.is_in_schedule(c.get('schedule'))
                and not (c.get('incoming_only') and getattr(event.message, 'out', False))
            ]
            if edit_as_new_configs:
                msg_text = (event.message.text or "").strip()
                if self._is_loading_placeholder(msg_text):
                    logger.info(f"EditAsNew: Ignorando mensaje temporal de carga en {event.chat_id}.")
                    return

                # Debounce corto (2s) contra eventos duplicados inmediatos con texto idéntico
                dedupe_key = (event.chat_id, event.message.id)
                now_ts = time.time()
                last_text, last_ts = self._last_edit_as_new_dedupe.get(dedupe_key, ("", 0.0))
                if msg_text == last_text and (now_ts - last_ts) < 2.0:
                    return
                self._last_edit_as_new_dedupe[dedupe_key] = (msg_text, now_ts)
                self._last_bot_event_ts[str(event.chat_id)] = now_ts

                logger.info(f"EditAsNew: Edición detectada en {event.chat_id} (Msg {event.message.id}). Enviando como NUEVO mensaje...")
                priority = edit_as_new_configs[0].get('priority', 99)
                await self.process_message(event.message, priority, edit_as_new_configs)
                return

            # Procesar el mensaje editado estándar a través del sistema de cache
            await self.handle_message_edit(event.message)

        # Lanzar tareas de Auto-Refresh para bots interactivos configurados
        for src_key, refresh_cfgs, interval_min in refresh_targets:
            asyncio.create_task(self._auto_refresh_loop(src_key, refresh_cfgs, interval_min))

        # Lanzar tareas de Ciclo de Temporalidades (:00 H1, :15 M15, :30 M30, :45 M15)
        for src_key, cycle_cfgs in cycle_targets:
            asyncio.create_task(self._timeframe_cycle_loop(src_key, cycle_cfgs))

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

    def format_neuraltrade_club10(self, text: str) -> str:
        """Formatea señales de NeuralTradeML / Mind con el estilo completo, decorado y elegante de CLUB 10M."""
        if not text:
            return None
        text_upper = text.upper()
        
        # 1. Dirección (BUY o SELL)
        direction = None
        if 'BUY' in text_upper or 'COMPRA' in text_upper:
            direction = 'BUY'
            dir_emoji = '🟢'
        elif 'SELL' in text_upper or 'VENTA' in text_upper:
            direction = 'SELL'
            dir_emoji = '🔴'
            
        if not direction:
            return None
            
        # 2. Activo y Temporalidad
        asset_match = re.search(r'([A-Z]{3,6}/[A-Z]{3,6}|XAUUSD|XAGUSD|EURUSD|GBPUSD|USDJPY|AUDCAD|GOLD|ORO)\s*(?:\(([A-Za-z0-9]+)\))?', text, re.I)
        asset_name = 'XAU/USD'
        timeframe = 'H1'
        if asset_match:
            cand_asset = asset_match.group(1).strip().upper()
            if any(g in cand_asset for g in ['XAU', 'GOLD', 'ORO']):
                asset_name = 'XAU/USD'
            else:
                asset_name = cand_asset
            if asset_match.group(2):
                timeframe = asset_match.group(2).strip().upper()

        def clean_val(v):
            if not v:
                return ''
            v = v.strip().replace(',', '.')
            v = re.sub(r'\s*[–—−]\s*', ' - ', v)
            v = re.sub(r'\s+', ' ', v)
            return v

        def format_range(s):
            if not s:
                return None
            if '-' in s:
                parts = [p.strip().strip('.') for p in s.split('-')]
                if len(parts) >= 2 and parts[0] and parts[1]:
                    return f"{parts[0]} - {parts[1]}"
            return s.strip()

        # 3. Precio Actual
        curr_match = re.search(r'(?:Current|Actual)[^\n\d]*([0-9]+(?:[.,][0-9]+)?)', text, re.I)
        curr_val = clean_val(curr_match.group(1)) if curr_match else None

        # 4. Entradas (Óptima / Extendida / General)
        best_entry_m = re.search(r'(?:ENTRY|ENTRADA)\s*\((?:best|óptimo|optim)[^)]*\)[^\n\d]*([0-9\.,\s–—−-]+)', text, re.I)
        ok_entry_m = re.search(r'(?:ENTRY|ENTRADA)\s*\((?:ok|correcto|correct)[^)]*\)[^\n\d]*([0-9\.,\s–—−-]+)', text, re.I)
        gen_entry_m = re.search(r'(?:ENTRY|ENTRADA)[^\n\d]*(\d+(?:[.,]\d+)?\s*[-–—−]\s*\d+(?:[.,]\d+)?)', text, re.I)
        if not gen_entry_m:
            gen_entry_m = re.search(r'(?:ENTRY|ENTRADA)\s*(?:\([^)]*\))?\s*[:\-]\s*([0-9\.,\s–—−-]+)', text, re.I)

        entry_best_str = format_range(clean_val(best_entry_m.group(1))) if best_entry_m else None
        entry_ok_str = format_range(clean_val(ok_entry_m.group(1))) if ok_entry_m else None
        entry_gen_str = format_range(clean_val(gen_entry_m.group(1))) if gen_entry_m else None

        if not entry_best_str and not entry_ok_str and not entry_gen_str:
            logger.info(f"format_neuraltrade_club10: No se detectó Entrada en: {repr(text[:120])}")
            return None

        # 5. No Chase (No perseguir por encima/debajo)
        no_chase_m = re.search(r'(?:No\s*chase|No\s*hay\s*persecuci[óo]n)\s*(below|above|arriba|abajo)?[^\n\d]*([0-9]+(?:[.,][0-9]+)?)', text, re.I)
        no_chase_str = None
        if no_chase_m:
            side_raw = (no_chase_m.group(1) or '').lower()
            nc_val = clean_val(no_chase_m.group(2))
            if any(w in side_raw for w in ['below', 'abajo']):
                no_chase_str = f"Por debajo de {nc_val}"
            elif any(w in side_raw for w in ['above', 'arriba']):
                no_chase_str = f"Por encima de {nc_val}"
            else:
                no_chase_str = nc_val

        # 6. Stop Loss (Trade SL y Hard SL)
        trade_sl_m = re.search(r'TRADE\s*SL[^\n\d]*([0-9]+(?:[.,][0-9]+)?)', text, re.I)
        hard_sl_m = re.search(r'HARD\s*SL[^\n\d]*([0-9]+(?:[.,][0-9]+)?)', text, re.I)
        gen_sl_m = re.search(r'(?:STOP\s*LOSS|\bSL\b|PARADAS?)[^\n\d]*([0-9]+(?:[.,][0-9]+)?)', text, re.I)

        trade_sl_str = clean_val(trade_sl_m.group(1)) if trade_sl_m else None
        hard_sl_str = clean_val(hard_sl_m.group(1)) if hard_sl_m else None
        gen_sl_str = clean_val(gen_sl_m.group(1)) if gen_sl_m else None

        main_sl = trade_sl_str or gen_sl_str
        if not main_sl:
            logger.info(f"format_neuraltrade_club10: No se detectó Stop Loss en: {repr(text[:120])}")
            return None

        # 7. Take Profits (TP1 .. TP5)
        tps = []
        tp_emojis = ['🥇', '🥈', '🥉', '🎖️', '🚀']
        for i in range(1, 6):
            tp_m = re.search(rf'(?:TP|TARGET|OBJETIVO|TAKE\s*PROFIT)\s*{i}[^\n\d]*([0-9]+(?:[.,][0-9]+)?)', text, re.I)
            if tp_m:
                val = clean_val(tp_m.group(1))
                emoji = tp_emojis[i-1] if i-1 < len(tp_emojis) else '🎯'
                tps.append(f"{emoji} **TP{i}:** {val}")

        if not tps:
            logger.info(f"format_neuraltrade_club10: No se detectaron Take Profits en: {repr(text[:120])}")
            return None

        # 8. Ventana de Entrada y Validez
        win_m = re.search(r'(?:Best\s*entry\s*window|Mejor\s*ventana\s*ENTRY)[:\s]*([^\n\r]+)', text, re.I)
        enter_by_m = re.search(r'(?:Enter\s*by|Ingrese\s*antes\s*de)[:\s]*([^\n\r]+)', text, re.I)
        valid_m = re.search(r'(?:Valid\s*until|V[áa]lido\s*hasta)[:\s]*([^\n\r]+)', text, re.I)

        window_str = clean_val(win_m.group(1)) if win_m else None
        enter_by_str = clean_val(enter_by_m.group(1)) if enter_by_m else None
        valid_str = clean_val(valid_m.group(1)) if valid_m else None

        # 9. Confianza IA / Machine Learning
        ml_m = re.search(r'(?:Machine\s*Learning\s*Score|Puntuaci[óo]n\s*de\s*aprendizaje\s*autom[áa]tico)[:\s]*(\d+)', text, re.I)
        conf_m = re.search(r'(?:Direction\s*Confidence|Confianza\s*en\s*la\s*direcci[óo]n)[:\s]*(\d+)', text, re.I)
        ml_val = ml_m.group(1) if ml_m else None
        conf_val = conf_m.group(1) if conf_m else None

        ai_conf_str = None
        if ml_val and conf_val:
            ai_conf_str = f"{ml_val}% (Dirección: {conf_val}%)"
        elif ml_val:
            ai_conf_str = f"{ml_val}%"
        elif conf_val:
            ai_conf_str = f"{conf_val}%"

        # 10. Gestión de Riesgo
        gest_m = re.search(r'(?:still\s*open\s*at|OPEN\s*a\s*las|abierta\s*a\s*las)\s*([0-9]{1,2}:[0-9]{2}(?:\s*(?:UK|Reino\s*Unido|[A-Za-z]{2,4}))?)', text, re.I)
        gestion_str = None
        if gest_m:
            hora_gest = gest_m.group(1).strip()
            gestion_str = f"Si sigue abierta a las {hora_gest} y TP1 no alcanzado: reducir riesgo / salir en retroceso."

        # 11. ID de Señal (evita falsos positivos como la terminación de Confidence)
        id_m = re.search(r'\b(?:ID|Identificaci[óo]n)[:\s]+([A-Za-z0-9]{6,15})\b', text, re.I)
        sig_id = id_m.group(1).strip() if id_m else None

        # Ensamblar mensaje completo estilo CLUB 10M VIP
        op_suffix = "GOLD" if "XAU" in asset_name or "GOLD" in asset_name else asset_name
        lines = [
            "👑 **CLUB 10M | SEÑAL VIP** 👑",
            "",
            f"💎 **ACTIVO:** {asset_name} ({timeframe})",
            f"{dir_emoji} **OPERACIÓN:** {direction} {op_suffix}"
        ]

        if curr_val:
            lines.append(f"💵 **PRECIO ACTUAL:** {curr_val}")

        if entry_best_str and entry_ok_str:
            lines.append(f"🎯 **ENTRADA ÓPTIMA:** {entry_best_str}")
            lines.append(f"📍 **ENTRADA EXTENDIDA:** {entry_ok_str}")
        elif entry_best_str:
            lines.append(f"🎯 **ENTRADA:** {entry_best_str}")
        elif entry_gen_str:
            lines.append(f"🎯 **ENTRADA:** {entry_gen_str}")

        if no_chase_str:
            lines.append(f"⚠️ **NO PERSEGUIR:** {no_chase_str}")

        lines.append(f"🛑 **STOP LOSS:** {main_sl}")
        if hard_sl_str:
            lines.append(f"🛡️ **HARD SL:** {hard_sl_str}")

        lines.append("")
        lines.append("🎯 **OBJETIVOS:**")
        lines.extend(tps)

        # Bloque de Tiempos
        time_lines = []
        if window_str:
            if enter_by_str:
                time_lines.append(f"⏰ **VENTANA DE ENTRADA:** {window_str} (Entrar antes de {enter_by_str})")
            else:
                time_lines.append(f"⏰ **VENTANA DE ENTRADA:** {window_str}")
        elif enter_by_str:
            time_lines.append(f"⏰ **ENTRAR ANTES DE:** {enter_by_str}")

        if valid_str:
            time_lines.append(f"⏳ **VÁLIDO HASTA:** {valid_str}")

        if time_lines:
            lines.append("")
            lines.extend(time_lines)

        if ai_conf_str:
            lines.append("")
            lines.append(f"🤖 **CONFIANZA IA:** {ai_conf_str}")

        if gestion_str:
            lines.append("")
            lines.append(f"💡 **GESTIÓN:** {gestion_str}")

        if sig_id:
            lines.append(f"🔖 **ID:** `{sig_id}`")

        return "\n".join(lines)

    def is_gemini_enabled(self, config: dict) -> bool:
        """Verifica si un destino tiene habilitada la traducción con Gemini."""
        if not isinstance(config, dict):
            return False
        if config.get('use_gemini') is True:
            return True
        dest = config.get('dest')
        # Soporte directo para grupo de prueba y NASR (-1004438757585, -1004351918395)
        if dest in [-1004438757585, 4438757585, -4438757585, -1004351918395, 4351918395, -4351918395]:
            return True
        return False

    def is_gemini_dest_id(self, dest_id: int) -> bool:
        """Verifica si un dest_id tiene habilitado Gemini en REPLICATION_MAP o por ID."""
        if dest_id in [-1004438757585, 4438757585, -4438757585, -1004351918395, 4351918395, -4351918395]:
            return True
        for configs in self.replication_map.values():
            cfg_list = configs if isinstance(configs, list) else [configs]
            for cfg in cfg_list:
                if cfg.get('dest') == dest_id and cfg.get('use_gemini') is True:
                    return True
        return False

    def is_face_detection_enabled(self, source_id, configs: list) -> bool:
        """Verifica si la detección de rostros está habilitada exclusivamente para los grupos autorizados (-1004438757585 y -1004308389038)."""
        allowed_ids = {
            -1004438757585, 4438757585, -4438757585,
            -1004308389038, 4308389038, -4308389038
        }
        try:
            if int(source_id) in allowed_ids:
                return True
        except (ValueError, TypeError):
            pass

        if isinstance(configs, list):
            for cfg in configs:
                dest = cfg.get('dest') if isinstance(cfg, dict) else None
                try:
                    if dest and int(dest) in allowed_ids:
                        return True
                except (ValueError, TypeError):
                    pass
                if cfg.get('enable_face_detection') is True:
                    return True

        return False

    def sanitize_text(self, text: str) -> str:
        """Sanitiza menciones, enlaces externos, etiquetas HTML y fugas de razonamiento IA."""
        if not text:
            return ""
        text = re.sub(r'http[s]?://\S+', '👑CLUB 10M', text)
        text = re.sub(r't\.me/\S+', '👑CLUB 10M', text)

        # Limpiar etiquetas HTML de custom emojis o tags corruptos (ej. <g id="2">)
        text = re.sub(r'</?g(?:\s+[^>]*)?>', '', text)
        text = re.sub(r'</?(?:tg-emoji|emoji)(?:\s+[^>]*)?>', '', text)
        # Limpiar viñetas o puntos huérfanos residuales al inicio de línea
        text = re.sub(r'^[·•\s]+(?=[A-Za-z0-9ÁÉÍÓÚáéíóú💎👑✅])', '', text, flags=re.MULTILINE)

        # Limpiar posibles fugas del razonamiento interno o reglas del prompt de la IA (CoT leakage)
        leak_patterns = [
            r'rule\s+\d+\s+says',
            r'let\'s\s+check\s+rule',
            r'writing\s+stop\s+loss',
            r'emojis\s+intact',
            r'elimina\s+slang\s+residual',
            r'respuesta\s+limpia',
            r'prohibido\s+agregar\s+contenido',
            r'only\s+translated\s+text',
            r'execution\s+terms',
            r'none\s+added'
        ]
        clean_lines = []
        for line in text.split('\n'):
            line_low = line.lower()
            if any(re.search(pat, line_low) for pat in leak_patterns):
                logger.warning(f"Sanitizer: Fuga de razonamiento de IA eliminada: '{line.strip()}'")
                continue
            clean_lines.append(line)
        text = "\n".join(clean_lines).strip()

        return text

    async def translate_with_gemini(self, text: str) -> str:
        """
        Traduce el texto usando la API oficial de Google Gemini con prompt especializado en Forex/Trading.
        Prueba múltiples modelos de Gemini (1.5-flash, 2.0-flash) y si la API no responde, aplica fallback a los traductores secundarios (Google / MyMemory).
        Retorna el texto traducido o None si la IA y los traductores de respaldo fallan.
        """
        if not text:
            return ""

        gemini_key = (os.getenv('GEMINI_API_KEY') or self.gemini_api_key or "").strip()
        if not gemini_key:
            logger.warning("Gemini: Clave GEMINI_API_KEY no configurada. Mensaje NO será traducido (grupos Gemini no usan Google Translate).")
            return None

        system_instruction = (
            "Eres un traductor y editor financiero experto en señales y análisis de trading de Forex, Oro (XAUUSD) y Cripto para Telegram.\n"
            "Tu tarea es traducir con la máxima precisión el mensaje al ESPAÑOL manteniendo un formato limpio y profesional.\n\n"
            "REGLAS ESTRICTAS:\n"
            "1. TRADUCE TODO EL TEXTO DESCRIPTIVO: Si el mensaje contiene párrafos, explicaciones o frases en cualquier idioma, tradúcelas completamente al español neutro de trading.\n"
            "2. PRESERVA TÉRMINOS TÉCNICOS: Conserva EXACTAMENTE y en mayúsculas términos de ejecución como: BUY, SELL, BUY LIMIT, SELL LIMIT, BUY STOP, SELL STOP, ENTRY, SL, STOP LOSS, TP, TP1, TP2, TP3, TP4, TP5, TP6, TP7, TP8, TP9, TP10, TAKE PROFIT, BREAK EVEN, BE, OPEN, HIT, PIPS, PIP, GOLD, XAUUSD.\n"
            "3. PRESERVA PRECIOS, NÚMEROS Y EMOJIS: No modifiques valores numéricos, rangos de entrada ni elimines emojis o saltos de línea.\n"
            "4. ELIMINA SLANG RESIDUAL: Traduce expresiones coloquiales malayas (ej. 'junam' -> 'fuerte caída', 'jom fly' -> 'vamos a subir/volar', 'kutip' -> 'asegurar ganancias', 'padu' -> 'sólido/excelente') al contexto financiero en español.\n"
            "5. RESPUESTA ÚNICA Y LIMPIA: Devuelve ÚNICAMENTE la traducción final limpia del mensaje. NUNCA incluyas tu proceso de pensamiento, reglas, reflexiones internas ('Rule 2 says:', 'Respuesta limpia:', etc.), ni explicaciones adicionales.\n"
            "6. PROHIBIDO AGREGAR CONTENIDO O CONSEJOS: Traduce EXACTAMENTE el mensaje original. NO añadas opiniones, recomendaciones financieras ni notas inventadas."
        )

        payload = {
            "system_instruction": {
                "parts": [
                    {"text": system_instruction}
                ]
            },
            "contents": [
                {
                    "parts": [
                        {"text": text}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 2048
            }
        }

        # Modelos a intentar en orden en caso de 404 o indisponibilidad
        models_to_try = [
            os.getenv('GEMINI_MODEL', self.gemini_model) or 'gemini-3.6-flash',
            'gemini-3.6-flash',
            'gemini-3.6-flash-8b',
            'gemini-3.6-pro'
        ]
        seen = set()
        models_to_try = [m for m in models_to_try if not (m in seen or seen.add(m))]

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                for model in models_to_try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
                    try:
                        response = await client.post(
                            url,
                            headers={"Content-Type": "application/json"},
                            json=payload
                        )
                        if response.status_code == 200:
                            data = response.json()
                            candidates = data.get('candidates', [])
                            if candidates and 'content' in candidates[0] and 'parts' in candidates[0]['content']:
                                gemini_text = candidates[0]['content']['parts'][0]['text'].strip()
                                if gemini_text:
                                    logger.info(f"Gemini ({model}): Traducción IA completada exitosamente.")
                                    return self.apply_spanish_terms(gemini_text)
                        else:
                            logger.warning(f"Gemini API model '{model}' devolvió status {response.status_code}. Intentando modelo de reserva...")
                            logger.warning(f"Respuesta de Gemini: {response.text}")
                    except Exception as e_mod:
                        logger.warning(f"Excepción consultando Gemini modelo '{model}': {e_mod}")
        except Exception as e:
            logger.error(f"Gemini Exception durante traducción: {e}.")

        logger.warning("Gemini: Todos los modelos de IA fallaron o no están disponibles. Mensaje NO será traducido (grupos Gemini no usan Google Translate).")
        return None

    def _is_video_message(self, message: Message) -> bool:
        """Determina si el mensaje contiene un video, nota de video o documento con formato de video."""
        if getattr(message, 'video', None) or getattr(message, 'video_note', None):
            return True
        doc = getattr(message, 'document', None)
        if doc and (getattr(doc, 'mime_type', '') or '').startswith('video/'):
            return True
        return False

    def _contains_bot_commands(self, text: str) -> bool:
        """Detecta comandos de Telegram (/signal, /start, /help, etc.) o menciones a comandos."""
        if not text:
            return False
        # Comandos tipo /signal, /start, /help (sin afectar pares como XAU/USD, fechas 17/11/2026 ni URLs)
        if re.search(r'(?<![A-Za-z0-9/:])/[a-zA-Z][a-zA-Z0-9_]{1,31}\b', text):
            return True
        if re.search(r'\b(COMANDO|COMANDOS|COMMAND|COMMANDS)\b', text, flags=re.IGNORECASE):
            return True
        return False

    # --- PIPELINE ---
    async def process_message(self, message: Message, priority: int, configs: list):
        source_id = str(message.chat_id)
        source_name = configs[0].get('name', 'Unknown') if configs else "Unknown"
        msg_id = message.id
        original_text = self.normalize_text(message.text or "")
        
        # Verificar si al menos un destino permite multimedia si no hay texto (respetando exclusión de videos)
        is_video = self._is_video_message(message)
        any_media_allowed = any(
            c.get('allow_media') and not (is_video and c.get('allow_video') is False)
            for c in configs
        )
        if not original_text and not (message.media and any_media_allowed):
            return

        # 0. Descartar mensajes con comandos de bot (/signal, /start, /help, "comandos", "commands")
        if self._contains_bot_commands(original_text):
            logger.info(f"Pipeline: Mensaje {msg_id} de {source_name} descartado por contener comandos de bot (/signal, comandos, etc.).")
            return

        # 0. Descartar GIFs completamente (Gif + Texto acompañante)
        if message.gif:
            logger.info(f"Pipeline: Mensaje {msg_id} descartado por ser un GIF.")
            return

        # 0.1 CONTROL DE QR CODES Y ROSTROS HUMANOS (IA / OPENCV)
        if message.photo:
            temp_path = f"temp_img_{msg_id}.jpg"
            try:
                await message.download_media(file=temp_path)
                if qr_detector.tiene_qr(temp_path):
                    logger.warning(f"Pipeline: Mensaje {msg_id} BLOQUEADO - QR detectado en la imagen.")
                    return # 🔥 BLOQUEA EL MENSAJE

                # Detección de rostros SOLO habilitada para los grupos autorizados (-1004438757585 y -1004308389038)
                if self.is_face_detection_enabled(source_id, configs):
                    gemini_key = (os.getenv('GEMINI_API_KEY') or self.gemini_api_key or "").strip()
                    if await face_detector.tiene_rostro_async(temp_path, gemini_key=gemini_key):
                        logger.warning(f"Pipeline: Mensaje {msg_id} BLOQUEADO - Rostro humano detectado en la imagen por IA / Visión (Grupo restringido).")
                        return # 🔥 BLOQUEA EL MENSAJE
            except Exception as e:
                logger.error(f"Error procesando análisis de imagen en Msg {msg_id}: {e}")
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        logger.info(f"Pipeline: Procesando mensaje de {source_name} ({source_id}). Msg ID: {msg_id}")

        # 1. Aplicar Filtros Manuales (Reemplazos y descartes por Zoom/Clases/Redes Sociales)
        skip_promo_filters = all(c.get('skip_promo_filters', False) for c in configs)
        if skip_promo_filters:
            text_filtered = original_text
        else:
            text_filtered = self.apply_manual_filters(original_text, source_name)
            if not text_filtered:
                logger.info(f"Pipeline: Mensaje {msg_id} descartado por filtros manuales.")
                return

        # Comprobar si algún destino tiene habilitado club10_style (ej. NeuralTradeML)
        neural_club10_text = None
        if any(c.get('club10_style', False) for c in configs):
            logger.info(f"Pipeline: Procesando señal con estilo CLUB 10M para Msg {msg_id} ({len(original_text)} caracteres).")
            neural_club10_text = self.format_neuraltrade_club10(original_text or text_filtered)
            if neural_club10_text:
                logger.info(f"Pipeline: Mensaje {msg_id} de {source_name} decorado exitosamente al estilo CLUB 10M.")
            else:
                logger.warning(
                    f"Pipeline: Msg {msg_id} de {source_name} no pudo ser decorado como señal CLUB 10M. "
                    f"Texto recibido:\n{repr((original_text or text_filtered)[:300])}"
                )

        # 2. Preparar Traducciones según los motores de cada destino
        has_gemini_dest = any(self.is_gemini_enabled(c) for c in configs)
        has_standard_dest = any(not self.is_gemini_enabled(c) for c in configs)

        gemini_text = None
        standard_text = None

        if has_gemini_dest:
            logger.info("Pipeline: Traducción con GEMINI IA activada para grupo de prueba.")
            gemini_res = await self.translate_with_gemini(text_filtered)
            gemini_text = self.sanitize_text(gemini_res) if gemini_res is not None else None

        if has_standard_dest:
            if neural_club10_text and all(c.get('club10_style', False) for c in configs):
                standard_text = neural_club10_text
            else:
                logger.info("Pipeline: Usando traducción ASÍNCRONA estándar para destinos regulares...")
                std_res = await self.smart_fragment_translation_async(text_filtered)
                standard_text = self.sanitize_text(std_res) if std_res is not None else None

        # 3. Publicar en todos los destinos configurados
        for config in configs:
            dest_id = config.get('dest')
            topic_id = config.get('topic')
            allow_media = config.get('allow_media', False)
            prefix = config.get('prefix', '')
            if prefix:
                clean_prefix = prefix.replace("**", "")
                if clean_prefix.startswith("REENVIADO POR "):
                    clean_prefix = clean_prefix.replace("REENVIADO POR ", "", 1)
                prefix = f"**REENVIADO POR {clean_prefix}**"

            # Filtro de calidad Mind / NeuralTrade (Botón verde + Confianza mínima)
            if config.get('require_green_indicator') or config.get('min_direction_confidence'):
                is_valid, q_reason = self._validate_mind_quality(original_text or text_filtered, config)
                if not is_valid:
                    logger.info(f"Pipeline: Msg {msg_id} DESCARTADO para {dest_id} por filtro Mind: {q_reason}.")
                    continue
                logger.info(f"Pipeline: Msg {msg_id} APROBADO para {dest_id} por filtro Mind ({q_reason}).")

            use_gem = self.is_gemini_enabled(config)
            if config.get('club10_style'):
                if not neural_club10_text:
                    logger.info(f"Pipeline: Mensaje {msg_id} DESCARTADO para {dest_id} - No contiene estructura completa de señal (Entrada, SL o TP).")
                    continue
                dest_final_text = neural_club10_text
            else:
                dest_final_text = gemini_text if use_gem else standard_text

            # SI EL TEXTO ERA REQUERIDO PERO LA TRADUCCIÓN FALLÓ COMPLETAMENTE (dest_final_text IS NONE):
            if dest_final_text is None and text_filtered:
                engine_name = "Gemini IA (y traductores de respaldo)" if use_gem else "Traducción Estándar (Google/MyMemory)"
                logger.error(
                    f"Pipeline: MENSAJE DESCARTADO - Msg {msg_id} NO ENVIADO a {dest_id} ({config.get('name', 'Unknown')}). "
                    f"Razón: Fallaron todos los motores de traducción [{engine_name}]."
                )
                continue

            # Descarte de seguridad post-traducción para comandos de bot (aplica a TODOS los grupos)
            if dest_final_text and self._contains_bot_commands(dest_final_text):
                logger.info(f"Pipeline: Mensaje {msg_id} DESCARTADO tras traducción por contener comandos de bot.")
                continue

            # Descarte de seguridad post-traducción (VIP OPEN, cupos, slots, tragamonedas, etc.)
            if dest_final_text and not config.get('skip_promo_filters', False):
                dest_upper = dest_final_text.upper()
                if re.search(r'\bVIP\s+OPEN\b', dest_upper) or re.search(r'\b(CUPO|CUPOS|SLOT|SLOTS|TRAGAMONEDAS|BILLETERA|BILLETERAS|PAGO|PAGOS|PARTICIPANTE|PARTICIPANTES|WALLET|WALLETS|POOL|POOLS|POLL|POLLS)\b', dest_upper):
                    logger.info(f"Pipeline: Mensaje {msg_id} DESCARTADO tras traducción por contener términos prohibidos (VIP OPEN / cupos / slots / pagos / pool).")
                    continue

            # Anteponer encabezado/título personalizado (ej: 👑 CLUB 10M | SEÑAL VIP 👑) si está configurado
            header = config.get('header') or config.get('custom_header')
            if header and dest_final_text:
                if not dest_final_text.startswith(header):
                    dest_final_text = f"{header}\n\n{dest_final_text}"

            # Anteponer prefijo al texto si está definido
            text_to_send = f"{prefix}\n\n{dest_final_text}".strip() if prefix and dest_final_text else dest_final_text

            # Comprobar restricciones multimedia (ej: allow_media=True pero allow_video=False)
            allow_video = config.get('allow_video', True)
            media_allowed_for_dest = allow_media and not (is_video and allow_video is False)
            file_to_send = message.media if media_allowed_for_dest else None

            # Si el destino no permite este archivo multimedia y el mensaje es solo media (sin texto), saltar
            if not text_to_send and not file_to_send:
                continue

            try:
                sent_msg = await self.client.send_message(
                    dest_id, 
                    text_to_send, 
                    reply_to=topic_id,
                    file=file_to_send
                )
                engine_name = "Gemini IA" if use_gem else "Estándar"
                logger.info(f"Pipeline: SUCCESS - Msg {msg_id} enviado a {dest_id} [{engine_name}, prefix='{prefix}'].")
                
                # Guardar en cache para soporte de ediciones posteriores (solo si NO es edit_as_new)
                if not config.get('edit_as_new', False):
                    message_cache.add_message(msg_id, sent_msg, prefix=prefix, sent_text=text_to_send)
            except Exception as e:
                logger.error(f"Pipeline: ERROR enviando Msg {msg_id} a {dest_id}: {e}")

    async def handle_message_edit(self, message: Message):
        """Maneja el evento de edición de un mensaje original usando el cache."""
        msg_id = message.id
        mappings = message_cache.get_message(msg_id)
        
        if not mappings:
            return

        logger.info(f"Edit: Detectada edición en Msg {msg_id}. Procesando actualización...")
        
        original_text = self.normalize_text(message.text or "")
        if self._contains_bot_commands(original_text):
            logger.info(f"Edit: Msg {msg_id} edición descartada por contener comandos de bot.")
            return
        
        # Reprocesar el texto a través del pipeline de filtros
        text_filtered = self.apply_manual_filters(original_text)
        if not text_filtered:
            return

        # Precomputar traducciones necesarias según motores de los destinos mapeados
        has_gemini_edit = any(self.is_gemini_dest_id(m.get("chat_id")) for m in mappings)
        has_standard_edit = any(not self.is_gemini_dest_id(m.get("chat_id")) for m in mappings)

        gemini_text = None
        standard_text = None

        if has_gemini_edit:
            gemini_res = await self.translate_with_gemini(text_filtered)
            gemini_text = self.sanitize_text(gemini_res) if gemini_res is not None else None

        if has_standard_edit:
            std_res = await self.smart_fragment_translation_async(text_filtered)
            standard_text = self.sanitize_text(std_res) if std_res is not None else None
        
        # Editar todas las réplicas encontradas en el cache
        for mapping in mappings:
            try:
                dest_chat_id = mapping["chat_id"]
                replicated_msg_id = mapping["replicated_id"]

                prefix = mapping.get('prefix', '')
                if prefix:
                    clean_prefix = prefix.replace("**", "")
                    if clean_prefix.startswith("REENVIADO POR "):
                        clean_prefix = clean_prefix.replace("REENVIADO POR ", "", 1)
                    prefix = f"**REENVIADO POR {clean_prefix}**"

                use_gem = self.is_gemini_dest_id(dest_chat_id)
                final_text = gemini_text if use_gem else standard_text

                if final_text is None and text_filtered:
                    logger.error(
                        f"Edit: EDICIÓN OMITIDA - Msg {msg_id} NO ACTUALIZADO en {dest_chat_id}. "
                        f"Razón: Fallaron todos los motores de traducción al procesar la edición."
                    )
                    continue

                # Descarte de seguridad post-traducción en ediciones
                if final_text:
                    dest_upper = final_text.upper()
                    if re.search(r'\bVIP\s+OPEN\b', dest_upper) or re.search(r'\b(CUPO|CUPOS|SLOT|SLOTS|TRAGAMONEDAS|BILLETERA|BILLETERAS|PAGO|PAGOS|PARTICIPANTE|PARTICIPANTES|WALLET|WALLETS|POOL|POOLS|POLL|POLLS)\b', dest_upper):
                        logger.info(f"Edit: Msg {msg_id} edición descartada tras traducción por contener términos prohibidos.")
                        continue

                header = mapping.get('header', '')
                if header and final_text and not final_text.startswith(header):
                    final_text = f"{header}\n\n{final_text}"

                text_to_send = f"{prefix}\n\n{final_text}".strip() if prefix and final_text else final_text

                # Protección anti-edición fantasma
                previously_sent = mapping.get('sent_text', '')
                if previously_sent and text_to_send.strip() == previously_sent.strip():
                    logger.info(f"Edit: Msg {msg_id} en {dest_chat_id} - texto sin cambios reales, edición omitida.")
                    continue
                
                await self.client.edit_message(
                    dest_chat_id,
                    replicated_msg_id,
                    text_to_send
                )
                logger.info(f"Edit: SUCCESS - Msg {msg_id} actualizado en chat {dest_chat_id}.")
            except Exception as e:
                logger.error(f"Edit: ERROR al actualizar Msg {msg_id} en {mapping.get('chat_id')}: {e}")
