# Telegram Message Replicator

Este sistema escucha mensajes de un grupo origen y los publica como mensajes nuevos en un grupo destino, evitando etiquetas de reenvío.

## Requisitos

- Python 3.8+
- Una cuenta de Telegram
- `API_ID` y `API_HASH` de [my.telegram.org](https://my.telegram.org)

## Instalación

1. Clonar el repositorio.
2. Crear un entorno virtual e instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```
3. Configurar variables de entorno:
   - Copia `.env.example` a `.env`.
   - Edita `.env` con tus credenciales y los IDs/Usernames de los grupos.

## Uso

### Paso 1: Autenticación
La primera vez debes iniciar sesión para crear el archivo de sesión.
```bash
python auth.py
```
Sigue las instrucciones en pantalla.

### Paso 2: Ejecución
Inicia el replicador:
```bash
python main.py
```

## Notas
- **El archivo `.session` es sensible.** Contiene acceso completo a tu cuenta de Telegram. No lo compartas.
- Para obtener IDs de canales numéricos (ej. -100...), puedes usar bots como `@username_to_id_bot` o clientes alternativos.
