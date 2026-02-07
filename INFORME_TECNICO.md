# Informe Técnico de Análisis del Código Base: Antigraviti

## 1. Resumen Ejecutivo
**Antigraviti** es un sistema de automatización desarrollado en **Python** diseñado para replicar señales de trading desde múltiples canales de Telegram de origen hacia un canal de destino único. El sistema actúa como un "filtro inteligente" y orquestador, aplicando reglas estrictas de negocio, limpieza de contenido y normalización mediante Inteligencia Artificial (LLM) antes de republicar los mensajes.

El objetivo principal es consolidar señales de diversas fuentes con diferentes prioridades, evitando conflictos (ej. señales opuestas para el mismo activo) y garantizando un formato profesional y uniforme en el canal de destino.

## 2. Arquitectura del Sistema

### 2.1. Diagrama de Flujo de Alto Nivel
1.  **Ingesta (Listener)**: `Telethon` escucha eventos `NewMessage` de una lista predefinida de canales de origen.
2.  **Procesamiento (Pipeline)**:
    *   **Filtros Duros (Hard Filters)**: Validación sintáctica y limpieza básica (Keywords, eliminación de promociones).
    *   **Filtros Lógicos (Logical Filters)**: Reglas de negocio (Prioridad, Conflictos, Horario de Mercado). **Nota**: El bloqueo por prioridad se ha desactivado para permitir la replicación paralela a diferentes temas (topics) dentro del grupo destino.
15→    *   **Filtro AI (AI Filter)**: Validación semántica y normalización de formato vía API externa (`apifreellm`).
16→3.  **Estado (State Management)**: Persistencia local en JSON para rastrear señales activas e historial informativo de prioridades.
17→4.  **Publicación (Publisher)**: Envío del mensaje procesado al canal de destino con soporte para hilos (topics).

### 2.2. Componentes Principales

| Componente | Archivo(s) | Descripción |
| :--- | :--- | :--- |
| **Configuración** | `config.py` | Centraliza el `REPLICATION_MAP` y las constantes de filtrado. |
| **Orquestador** | `main.py` | Punto de entrada. Carga configuración, inicializa el cliente de Telegram y arranca el replicador. |
| **Replicador** | `replicator.py` | Núcleo del sistema. Contiene la clase `TelegramReplicator` que implementa el pipeline de procesamiento (`process_message`). |
| **Gestor de Estado** | `replicator.py` | Clase `SignalStateManager`. Gestiona `signal_state.json` para resolver conflictos de prioridad y duplicados. |
| **Utilidades de Auth** | `auth.py` | Script auxiliar para autenticación interactiva y generación de `StringSession`. |
| **Enviador de Historial** | `send_history_filtered.py` | Herramienta para escanear, filtrar con IA y enviar mensajes históricos de los canales. |
| **Analizador de Historial** | `analyze_history.py` | Genera reportes detallados (CSV) sobre la efectividad de los filtros en el historial. |
| **Verificador de Config** | `verify_config.py` | Valida permisos y existencia de los grupos de Telegram configurados. |

## 3. Análisis Detallado del Código

### 3.1. Stack Tecnológico
*   **Lenguaje**: Python 3.x
*   **Librería Telegram**: `Telethon` (Cliente MTProto asíncrono).
*   **Gestión de Entorno**: `python-dotenv`.
*   **HTTP Client**: `httpx` (para consumo de API de IA).
*   **Manejo de Tiempo**: `pytz`.
*   **Persistencia**: Archivo JSON local.

### 3.2. Flujo de Ejecución (Pipeline)
El método `process_message` en `TelegramReplicator` orquesta las siguientes etapas:

1.  **Hard Filters (`run_hard_filters`)**:
    *   **Keywords**: Verifica presencia de palabras clave (BUY, SELL, TP, SL, etc.).
    *   **Limpieza Promo**: Corta el mensaje si detecta palabras como "promo", "link", "únete".
    *   **Estructura**: Valida que parezca una señal o actualización válida.

2.  **Logical Filters (`run_logical_filters`)**:
    *   **Parsing**: Extrae el Activo (ej. XAUUSD) y Dirección (BUY/SELL) usando Regex.
    *   **Prioridad y Conflictos**: Consulta `SignalStateManager`.
        *   **Actualización**: Ya no se bloquean mensajes por baja prioridad. Dado que cada fuente tiene su propio tema (topic) en el destino, se permite la coexistencia de múltiples señales para el mismo activo. La prioridad ahora se registra solo de forma informativa en `signal_state.json`.
    *   **Horario**: Verifica si es horario de mercado (Londres/NY).

3.  **AI Filter (`run_ai_filter`)**:
    *   Envía el mensaje limpio a `https://apifreellm.com/api/v1/chat`.
    *   **Prompt**: Instruye a la IA para actuar como editor, normalizar formato (🎯 **TP1 / TP2**, ⛔ **SL**), traducir y reemplazar términos específicos ("Club 10M").
    *   **Validación**: Si la IA responde "REJECT" (Rechazo Semántico), el mensaje se descarta (salvo fallback).

4.  **Fallback & Publicación**:
    *   Existe una lógica de **fallback**: Si la IA falla o rechaza, pero el filtro lógico detectó claramente un Activo y Dirección, se publica el mensaje "crudo" con una alerta.
    *   Se envía al canal destino y se actualiza el estado.

### 3.3. Configuración y Datos
*   **Variables de Entorno (.env)**: Credenciales de Telegram (`API_ID`, `API_HASH`), Session String.
*   **Mapeo de Fuentes**: Diccionario `REPLICATION_MAP` centralizado en `config.py`.
*   **Estado**: `signal_state.json` almacena lista de señales activas: `{asset, direction, priority, timestamp}`.

## 4. Áreas Críticas y Puntos de Atención

### 4.1. Lógica de Fallback de IA
*   **Riesgo**: En las líneas 342-346 de `replicator.py`, si la IA rechaza el mensaje (posiblemente por ser spam bien disfrazado), el sistema hace un fallback y lo publica de todas formas si detectó un activo y dirección. Esto podría permitir la fuga de mensajes no deseados que la IA filtró correctamente.

### 4.2. Prompt de IA Hardcodeado
*   El prompt del sistema (líneas 270-297 en `replicator.py`) contiene reglas de negocio muy específicas ("Club 10M", "@josejaqueoficial"). Si se cambia el branding o el propósito, se debe modificar el código fuente.

### 4.3. Manejo de Errores
*   Si la API de IA falla (`Exception` o status != 200), retorna `None`. El pipeline lo maneja descartando el mensaje (o usando fallback), lo cual es seguro, pero la dependencia de un servicio externo es un punto único de fallo para la normalización.

### 4.4. Persistencia
*   El uso de un archivo JSON (`signal_state.json`) no es transaccional ni seguro para concurrencia alta (aunque `asyncio` mitiga esto al ser single-threaded en ejecución). Si el bot se reinicia, carga el estado, lo cual es bueno.

## 5. Recomendaciones para Futuras Modificaciones

1.  **Modularización del Prompt**: Extraer el prompt de la IA a un archivo de texto o variable de configuración para facilitar ajustes de "personalidad" sin tocar el código lógico.
2.  **Revisión del Fallback**: Evaluar si el fallback de publicación "cruda" es deseado. Si la IA rechaza, probablemente debería ser definitivo, o enviarse a un canal de logs/admin para revisión manual, no al canal público.
3.  **Logging Estructurado**: Mejorar el sistema de logs para registrar *por qué* se descartó un mensaje (ej. "Rechazado por Filtro Promo", "Rechazado por Conflicto de Prioridad", "Rechazado por IA").

Este análisis confirma que el sistema está bien estructurado y sigue una lógica clara, pero tiene oportunidades de mejora en mantenibilidad y configuración.
