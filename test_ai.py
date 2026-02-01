import os
import httpx
import json
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def test_ai():
    url = "https://apifreellm.com/api/v1/chat"
    key = os.getenv('AI_API_KEY')
    
    system_prompt = (
        "Eres un transcriptor experto. Tu ÚNICA misión es recibir un mensaje y reescribirlo siguiendo estas 3 REGLAS DE ORO:\n"
        "1. REEMPLAZA OBLIGATORIAMENTE cualquier nombre de usuario (ej. @GoldMaster) por: @josejaqueoficial.\n"
        "2. REEMPLAZA OBLIGATORIAMENTE palabras como 'club', 'hermandad', 'brotherhood', 'familia', 'family' por: Club 10M.\n"
        "3. TRADUCE al español latino neutro si está en inglés, manteniendo un formato profesional y sin emojis.\n\n"
        "Si el mensaje es un reporte de resultados pasados (ej. 'TP hit', 'pips smashed'), responde solo: REJECT.\n"
        "Si el mensaje es charla irrelevante, responde: REJECT.\n"
        "Si el mensaje es una señal o información válida, devuelve el texto procesado SIN comentarios adicionales."
    )
    
    text = "Join our gold brotherhood, ask @GoldMaster for the next entry."
    full_prompt = f"{system_prompt}\n\nMensaje a procesar:\n{text}"
    
    print(f"Sending to {url} with key {key[:5]}...")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key}"
                },
                json={
                    "message": full_prompt,
                    "model": "apifreellm"
                },
                timeout=30.0
            )
            print(f"Status: {response.status_code}")
            data = response.json()
            print(f"Success: {data.get('success')}")
            print(f"Response: {data.get('response')}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_ai())
