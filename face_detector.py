import cv2
import os
import logging
import httpx
import base64

logger = logging.getLogger(__name__)

# Cargar clasificadores en cascada de OpenCV para detección frontal y de perfil
try:
    frontal_cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    profile_cascade_path = cv2.data.haarcascades + 'haarcascade_profileface.xml'
    
    face_cascade = cv2.CascadeClassifier(frontal_cascade_path)
    profile_cascade = cv2.CascadeClassifier(profile_cascade_path)
except Exception as e:
    logger.error(f"Error cargando clasificadores de rostro de OpenCV: {e}")
    face_cascade = None
    profile_cascade = None

def detect_face_opencv(ruta_imagen: str) -> bool:
    """
    Detecta rostros humanos en la imagen usando OpenCV (frontal y perfil).
    """
    if not os.path.exists(ruta_imagen):
        return False
        
    try:
        img = cv2.imread(ruta_imagen)
        if img is None:
            return False

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)

        # Detección frontal
        if face_cascade and not face_cascade.empty():
            faces = face_cascade.detectMultiScale(
                gray, 
                scaleFactor=1.1, 
                minNeighbors=5, 
                minSize=(40, 40)
            )
            if len(faces) > 0:
                logger.info(f"Rostro humano detectado por OpenCV (Frontal): {len(faces)} rostro(s).")
                return True

        # Detección perfil
        if profile_cascade and not profile_cascade.empty():
            profiles = profile_cascade.detectMultiScale(
                gray, 
                scaleFactor=1.1, 
                minNeighbors=5, 
                minSize=(40, 40)
            )
            if len(profiles) > 0:
                logger.info(f"Rostro humano detectado por OpenCV (Perfil): {len(profiles)} rostro(s).")
                return True

    except Exception as e:
        logger.error(f"Excepción en detección OpenCV de rostros en {ruta_imagen}: {e}")

    return False

async def detect_face_gemini(ruta_imagen: str, gemini_key: str) -> bool:
    """
    Usa la API de Google Gemini Vision para detectar si hay caras/rostros humanos en la imagen.
    """
    if not gemini_key or not os.path.exists(ruta_imagen):
        return False

    try:
        with open(ruta_imagen, "rb") as f:
            image_bytes = f.read()
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        prompt = (
            "¿Esta imagen contiene el rostro, cara o cabeza de una persona humana? "
            "Responde ÚNICAMENTE con 'SI' o 'NO'."
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": image_b64
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 10
            }
        }

        models_to_try = ['gemini-1.5-flash', 'gemini-3.6-flash', 'gemini-2.0-flash']
        async with httpx.AsyncClient(timeout=10.0) as client:
            for model in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
                try:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get('candidates', [])
                        if candidates and 'content' in candidates[0] and 'parts' in candidates[0]['content']:
                            text_res = candidates[0]['content']['parts'][0]['text'].strip().upper()
                            if "SI" in text_res or "SÍ" in text_res or "YES" in text_res:
                                logger.info(f"Gemini IA Visión ({model}): Rostro humano detectado en la imagen.")
                                return True
                            else:
                                return False
                except Exception as e_mod:
                    logger.warning(f"Excepción verificando rostro con Gemini modelo '{model}': {e_mod}")
    except Exception as e:
        logger.warning(f"Excepción en detección Gemini IA Visión de rostros: {e}")

    return False

async def tiene_rostro_async(ruta_imagen: str, gemini_key: str = None) -> bool:
    """
    Verifica si la imagen contiene un rostro humano usando OpenCV local y Gemini Vision IA si está disponible.
    """
    # 1. Detección rápida local con OpenCV
    if detect_face_opencv(ruta_imagen):
        return True

    # 2. Detección por IA Visión con Gemini (si hay API Key disponible)
    if gemini_key:
        if await detect_face_gemini(ruta_imagen, gemini_key):
            return True

    return False

def tiene_rostro(ruta_imagen: str) -> bool:
    """Versión síncrona usando OpenCV local."""
    return detect_face_opencv(ruta_imagen)
