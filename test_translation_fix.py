import asyncio
import os
from dotenv import load_dotenv
from replicator import TelegramReplicator

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
    print("\n--- TRADUCCIÓN (FALLBACK MANUAL) ---")
    # Test manual fallback first
    fallback_result = replicator.smart_fragment_translation(test_message)
    print(fallback_result)
    
    print("\n--- TRADUCCIÓN (IA) ---")
    # Test AI (if key is available)
    if os.getenv('AI_API_KEY'):
        ai_result = await replicator.run_ai_filter(test_message)
        print(ai_result)
    else:
        print("AI_API_KEY no encontrada. Saltando prueba de IA.")

if __name__ == "__main__":
    asyncio.run(test_translation())
