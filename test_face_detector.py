import asyncio
import os
import cv2
import numpy as np
import face_detector

async def main():
    print("--- PRUEBA DE DETECTOR DE ROSTROS ---")
    
    # 1. Crear una imagen negra sin rostro
    no_face_img = "test_no_face.jpg"
    black_canvas = np.zeros((300, 300, 3), dtype=np.uint8)
    cv2.imwrite(no_face_img, black_canvas)

    has_face = await face_detector.tiene_rostro_async(no_face_img)
    print(f"Imagen sin rostro (Lienzo negro) -> Rostro detectado: {has_face}")
    
    if os.path.exists(no_face_img):
        os.remove(no_face_img)
        
    print("Prueba completada con éxito.")

if __name__ == "__main__":
    asyncio.run(main())
