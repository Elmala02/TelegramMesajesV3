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


---------------------------------------------------
🔹 PROMPT OPERATIVO PARA ANTIGRAVITI
Sistema de filtrado, validación y normalización de señales de trading
🎯 Objetivo del sistema

Diseñar una automatización que escuche mensajes entrantes desde múltiples grupos de Telegram y publique únicamente señales de trading claras, coherentes y profesionales, aplicando filtros estrictos y una IA como editor final, de modo que todos los mensajes publicados parezcan enviados por una sola fuente confiable.

🧩 Flujo obligatorio de procesamiento

Antigraviti debe ejecutar las siguientes etapas en este orden exacto:

1. Recepción del mensaje
2. Filtros duros (código)
3. Filtros lógicos (código)
4. Evaluación y normalización con IA
5. Publicación (solo si es válido)


Si un mensaje falla en cualquier etapa, debe ser descartado sin publicarse.

1️⃣ Filtros duros (obligatorios, sin IA)

Antigraviti debe ignorar completamente cualquier mensaje que no cumpla TODAS estas condiciones:

🔹 1.1 Palabras clave obligatorias

El mensaje debe contener al menos una de las siguientes palabras (sin distinguir mayúsculas):

BUY
SELL
TP
SL

🔹 1.2 Contenido mínimo estructural

El mensaje debe contener:

Una dirección clara (BUY o SELL)

Una entrada o rango de entrada

Un Stop Loss explícito

Si falta cualquiera de estos elementos → descartar.

🔹 1.3 Eliminación de contenido promocional

Si el mensaje contiene palabras como:

promo
promoción
promocion
canal
únete
link


Antigraviti debe:

Eliminar esa palabra

Eliminar todo el contenido que se encuentre debajo de ella

Si después del corte el mensaje queda vacío o incompleto → descartar.

2️⃣ Filtros lógicos (criterio del club)
🔹 2.1 Conflictos de dirección

Antigraviti no debe permitir publicar señales BUY y SELL simultáneas sobre el mismo activo.

Si existe conflicto → descartar la nueva señal.

🔹 2.2 Señales duplicadas

Si ya se publicó recientemente una señal con:

El mismo activo

La misma dirección

Entrada similar

La nueva señal debe ser ignorada.

🔹 2.3 Horarios de envío

Las señales deben publicarse preferiblemente durante:

Sesión de Londres

Sesión de Nueva York

Fuera de estos horarios, Antigraviti debe aplicar criterio conservador o descartar.

3️⃣ Evaluación y normalización con IA (editor final)

Solo los mensajes que superen las etapas anteriores deben enviarse a la IA.

🧠 Rol de la IA

La IA actúa como editor profesional de un club de trading, no como trader.

Debe:

Validar que la señal sea clara y profesional

Normalizar el formato

Mantener el contenido técnico intacto

Permitir emojis si vienen en el mensaje original

❌ Reglas estrictas para la IA

La IA NO PUEDE:

Agregar información nueva

Cambiar precios, TP, SL o dirección

Agregar opiniones

Agregar contenido promocional

Cambiar el sentido de la señal

✅ Criterios de aceptación por la IA

La IA solo debe aceptar señales que:

Sean legibles en menos de 5 segundos

Tengan dirección clara

Incluyan entrada, SL y al menos un TP

No generen confusión para el usuario final

🧾 Formato oficial obligatorio (salida de la IA)

Si la señal es válida, la IA debe responder únicamente con el mensaje en este formato exacto:

Activo: [activo]

Dirección: BUY / SELL

Entrada: [precio o rango]

TP1:
TP2:

SL:

Riesgo recomendado: 1–2%

Estado: Activa


Los emojis pueden mantenerse si estaban presentes originalmente.

❌ Señal inválida (salida de la IA)

Si la señal no cumple los criterios, la IA debe responder solo con:

REJECT

4️⃣ Publicación

Antigraviti debe:

Publicar el mensaje solo si la respuesta de la IA NO es REJECT

Publicar el mensaje como contenido original

No añadir textos adicionales

Mantener siempre una sola voz y estilo del club

✅ Resultado esperado

Un sistema automatizado que:

Publica menos señales, pero más claras

Mantiene coherencia, criterio y autoridad

Transmite confianza y profesionalismo

Funciona como un club serio, no como un grupo improvisado

🔒 Principios no negociables

Claridad > cantidad

Criterio > velocidad

Consistencia > hype