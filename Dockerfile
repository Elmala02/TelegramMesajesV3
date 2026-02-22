# Usar una imagen base de Python ligera
FROM python:3.11-slim

# Evitar que Python genere archivos .pyc y habilitar el volcado de logs en tiempo real
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Establecer el directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema necesarias para construir librerías como cryptg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copiar el archivo de requerimientos e instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código del proyecto
COPY . .

# Crear archivos de log y base de datos vacíos si no existen para asegurar permisos correctos al montar volúmenes
RUN touch bot_execution.log debug_replicator.log trading_signals.db

# Comando para ejecutar la aplicación
CMD ["python", "main.py"]
