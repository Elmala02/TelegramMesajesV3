import asyncio
import os
import sys
from dotenv import load_dotenv
from replicator import TelegramReplicator

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

load_dotenv()

async def test_translation():
    # Mock behavior of TelegramClient and replication_map
    replication_map = {}
    replicator = TelegramReplicator(None, replication_map)
    
    test_message = """Sesión de Asia – 23 de febrero de 2026

Gold opened the Asian session above the key $5,100 area and is now trading at $5,140

Impulsores clave 📌
The main driver of today’s strength is renewed uncertainty from a major US court ruling and the US response on tariff policy, which has softened the dollar and pushed investors toward safe havens like gold. Los mercados asiáticos estuvieron mixtos, y con los cierres festivos en China y Japón reduciendo la liquidez, el lingote se ha beneficiado de los flujos de aversión al riesgo junto con el dólar más débil.. 

Resistencia 📉
El interés alcista se ha centrado en torno a los máximos de 5.150 dólares a 5.170-5.180 dólares, donde los vendedores han limitado los movimientos hasta ahora y pueden frenar nuevas ganancias hoy.

Apoyo 📈
En el lado negativo, el área de $5,100 sigue siendo un pivote clave. Una ruptura clara por debajo de esa zona podría hacer que los compradores hagan una pausa y el precio pruebe el soporte inferior más cerca de los mínimos iniciales de la sesión.

Sentimiento 💡
The tone stays positive for gold into the European and US sessions. Las ofertas de refugio seguro y un contexto más débil del dólar mantienen la inclinación alcista, aunque la escasa liquidez de Asia significa que las oscilaciones de precios podrían exagerarse desde el principio antes de que surja una dirección más clara."""

    print("--- TEXTO ORIGINAL ---")
    print(test_message)
    print("\n--- TRADUCCIÓN (FALLBACK MANUAL SÍNCRONO) ---")
    # Test manual fallback first
    fallback_result = replicator.smart_fragment_translation(test_message)
    print(fallback_result)

    print("\n--- TRADUCCIÓN (FALLBACK MANUAL ASÍNCRONO) ---")
    fallback_result_async = await replicator.smart_fragment_translation_async(test_message)
    print(fallback_result_async)
    
    print("\n--- PRUEBA 2: MENSAJE CON FUENTES ESPECIALES UNICODE, UZBEKO Y CIRÍLICO ---")
    test_message_2 = """𝗔𝗦𝗦𝗔𝗟𝗢𝗠 𝗔𝗟𝗘𝗞𝗨𝗠 𝗫𝗨𝗥𝗠𝗔𝗧𝗟𝗜   𝗧𝗥𝗔𝗗𝗘𝗥𝗟𝗔𝗥 

ЛАА ХАВЛА ВА ЛАА КУВВАТА ИЛАА БИЛЛАХИ"""
    print(f"Texto original:\n{test_message_2}")
    
    # 1. Probar paso por filtros manuales
    filtered_2 = replicator.apply_manual_filters(test_message_2)
    print(f"\nDespués de filtros manuales / normalización:\n{filtered_2}")
    
    # 2. Probar traducción asíncrona
    translated_2 = await replicator.smart_fragment_translation_async(filtered_2)
    print(f"\nResultado traducción asíncrona:\n{translated_2}")

    print("\n--- PRUEBA 4: ENRUTAMIENTO SELECTIVO POR DESTINO (GEMINI VS ESTÁNDAR) ---")
    from config import REPLICATION_MAP
    test_rep = TelegramReplicator(None, REPLICATION_MAP)
    
    test_configs = [
        {"dest": -1004438757585, "name": "Nuevo Destino (Gemini)", "priority": 1, "use_gemini": True},
        {"dest": -1003797962974, "name": "GTS VIP (Estándar)", "priority": 1},
        {"dest": -1003425756296, "name": "SR SNIPER VIP (Estándar)", "priority": 1}
    ]
    for cfg in test_configs:
        is_gem = test_rep.is_gemini_enabled(cfg)
        engine = "🤖 GEMINI IA" if is_gem else "⚙️ ESTÁNDAR"
        print(f"Destino {cfg['dest']} ({cfg['name']}) -> Motor: {engine}")

    print("\n--- PRUEBA 5: TRADUCCIÓN CON GEMINI (O FALLBACK SI NO HAY API KEY) ---")
    malay_signal = "Jom kita fly lagi Gold! Junam kuat tadi tapi sekarang breakout. Kutip profit TP1."
    print(f"Texto malayo original: {malay_signal}")
    gem_result = await test_rep.translate_with_gemini(malay_signal)
    print(f"Resultado Gemini / Fallback: {gem_result}")

if __name__ == "__main__":
    asyncio.run(test_translation())

