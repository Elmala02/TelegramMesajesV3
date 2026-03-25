import cv2
import logging
import os

logger = logging.getLogger(__name__)

def tiene_qr(ruta_imagen):
    """
    Detecta si una imagen contiene un código QR.
    """
    if not os.path.exists(ruta_imagen):
        logger.error(f"Archivo no encontrado: {ruta_imagen}")
        return False

    try:
        # Leer la imagen
        img = cv2.imread(ruta_imagen)
        if img is None:
            logger.error(f"No se pudo cargar la imagen: {ruta_imagen}")
            return False

        # Inicializar el detector de QR
        detector = cv2.QRCodeDetector()

        # Intentar detectar y decodificar
        # data puede ser una cadena vacía si no detecta nada
        data, bbox, _ = detector.detectAndDecode(img)

        if data:
            logger.info(f"QR Detectado: {data}")
            return True
        else:
            # A veces el detector básico falla, podemos probar con una versión más robusta 
            # (opcionalmente podrías usar pyzbar si estuviera instalado)
            return False
            
    except Exception as e:
        logger.error(f"Error detectando QR en {ruta_imagen}: {e}")
        return False
