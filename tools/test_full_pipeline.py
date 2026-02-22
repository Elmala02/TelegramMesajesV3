import asyncio
import os
import logging
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from replicator import TelegramReplicator

# Configurar logging para ver el proceso
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("TestPipeline")

load_dotenv()

API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
SESSION_STRING = os.getenv('SESSION_STRING')

REPLICATION_MAP = {
    -1: {"dest": -2, "topic": 1, "name": "TEST", "priority": 1}
}

async def test_full_logic():
    print("=== INICIANDO PRUEBA DE PIPELINE COMPLETO (FILTROS + TRADUCCIÓN) ===\n")
    
    if not SESSION_STRING:
        print("Error: Se necesita SESSION_STRING en el .env para probar el filtro de IA.")
        return

    # Inicializamos el cliente solo para que el Replicator funcione, no necesitamos conectar para los filtros internos
    client = TelegramClient(StringSession(SESSION_STRING), int(API_ID), API_HASH)
    replicator = TelegramReplicator(client, REPLICATION_MAP)
    
    # Mensajes de prueba del usuario
    test_cases = [
        {
            "name": "SEÑAL SELL GOLD CON TP4 MULTIPLE (REPORTE USUARIO)",
            "text": """Sell Gold 5067 - 5059 
 
 Stop Loss 5071 
 
 TP1 5057 
 TP2 5055 
 TP3 5053 
 TP4 Open (5050/5047/5042/5036)"""
        },
        {
            "name": "NUEVO FORMATO (Vender Oro)",
            "text": """Vender Oro 5023.5 - 5019.5 
 
 Stop Loss 5027.5 
 
 TP1 5018 
 TP2 5016 
 TP3 5014 
 TP4 Abierto (5012/5010/5006/5001)"""
        },
        {
            "name": "TIPO DE SEÑAL 1 (Sell Gold)",
            "text": """Sell Gold 5067 - 5059 
Stop Loss 5071 
TP1 5057 
TP2 5055 
TP3 5053 
TP4 Open (5050/5047/5042/5036)"""
        },
        {
            "name": "TIPO DE SEÑAL 2 (High Risk XAUUSD)",
            "text": """HIGH RISK 
XAU USD BUY NOW 
4884 - 4880 
TP1 4886 
TP2 4888 
TP3 4890 
TP4 4892 
TP5 4899 
SL 4876"""
        },
        {
            "name": "TIPO DE SEÑAL 3 (Gold Buy Now List)",
            "text": """Gold Buy Now! 

XAUUSD/GOLD 

 • Signal: Buy 
 • Entry: 5045 
 • Take Profit: 5055 
 • Stop Loss: 5035"""
        },
        {
            "name": "SEÑAL CON EMOJIS REPETIDOS (REPORTE USUARIO)",
            "text": """4805-4800 
 
 🥇TP1 4807 
 🥈TP1 4809 
 🥉TP1 4811 
 🎖️TP1 4822 
 
 🚫SL 4797"""
        },
        {
            "name": "UPDATE VÁLIDO (TP HIT)",
            "text": "TP1 HIT ✅"
        },
        {
            "name": "UPDATE CORTO (SL)",
            "text": "SL HIT"
        },
        {
            "name": "UPDATE CORTO (BE)",
            "text": "BE"
        },
        {
            "name": "GESTIÓN DE RIESGO (BE COMPLEJO)",
            "text": "- Moving ALL stops to BE 💡"
        },
        {
            "name": "REPORTE DE ANÁLISIS (DEBE BLOQUEARSE)",
            "text": """Asia Session – 4th February 2026 
Gold’s Asia session opened near $4,948 and is now trading at $5,084 
Key Drivers 📌 
The bounce reflects strong safe-haven demand as traders digest renewed geopolitical tensions in the Middle East, which have lifted bullion alongside wider risk awareness. A softer US dollar tone has also helped attract buyers back into gold after last week’s sharp sell-off. 
Resistance 📉 
Near term, the $5,090-$5,100 region will test upside momentum given recent highs and psychological barriers..."""
        },
        {
            "name": "COMENTARIO PERSONAL (DEBE BLOQUEARSE)",
            "text": "I’m adjusting my zones and managing risk accordingly - adapting is key 🔑"
        },
        {
            "name": "MENSAJE DE CHARLA LARGO (DEBE BLOQUEARSE)",
            "text": """Wow guys, we have to laugh today 😂 Gold is playing games, entry missed by 1 pip and straight to TP7 falling over 250 pips, and it couldn’t be closer 💯 
 
 The reason I’ve been successful in trading for over 17 years, is that I stick to zones and stick to my strategy - This requires discipline ✅ 
 
 I don’t trade to have fun, I trade to make money. Price action just didn’t want to enter our zones today, I’m still here and will keep you updated if I go for another trade ❤️"""
        }
    ]

    for case in test_cases:
        print(f"--- PROBANDO: {case['name']} ---")
        print(f"ENTRADA:\n{case['text']}\n")
        
        # 1. Hard Filter
        clean_text = replicator.run_hard_filters(case['text'])
        if not clean_text:
            print("RESULTADO: ❌ BLOQUEADO por Filtro Duro (Correcto si es basura/análisis)\n")
            continue
            
        print("PASÓ FILTRO DURO ✅")
        
        # 2. AI Filter (Traducción y Formato)
        print("Procesando con IA para traducción...")
        final_text = await replicator.run_ai_filter(clean_text)
        
        if not final_text:
            print("RESULTADO: ❌ RECHAZADO por la IA o Error de API (Usando manual como respaldo)\n")
            passed, parsed_data = replicator.run_logical_filters(clean_text, 1)
            final_text = replicator.format_signal_manually(parsed_data, raw_text=clean_text)
        
        print(f"RESULTADO FINAL:\n{final_text}\n")
        
        # Esperar un poco para evitar Rate Limit de la API gratuita
        await asyncio.sleep(5)
        print("-" * 30)

if __name__ == "__main__":
    asyncio.run(test_full_logic())
