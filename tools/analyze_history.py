import os
import asyncio
import logging
import json
import csv
from datetime import datetime
from collections import Counter
from telethon import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv
from replicator import TelegramReplicator

# --- CONFIGURACIÓN ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("analysis_debug.log"), logging.StreamHandler()]
)
logger = logging.getLogger("Analyzer")

load_dotenv()

API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
SESSION_STRING = os.getenv('SESSION_STRING')

REPLICATION_MAP = {
    -1002148227049: {"dest": -1003797962974, "topic": 2, "name": "GTS VIP", "priority": 1},
    -1002310215234: {"dest": -1003797962974, "topic": 3, "name": "44's Clup", "priority": 2},
    -1002108856565: {"dest": -1003797962974, "topic": 4, "name": "Gold Trader Sunny", "priority": 3},
    -1003020297428: {"dest": -1003797962974, "topic": 5, "name": "FXKINGS SIGNALS", "priority": 4},
    -1003759405936: {"dest": -1003797962974, "topic": 6, "name": "GRUPO DE PRUEBAS", "priority": 5}
}

async def analyze_group_history(client, group_id, group_name, limit=50):
    logger.info(f"Analizando últimos {limit} mensajes de {group_name}...")
    
    # Instanciamos el replicador para usar sus filtros
    replicator = TelegramReplicator(client, REPLICATION_MAP)
    
    results = []
    
    try:
        messages = await client.get_messages(group_id, limit=limit)
        
        for msg in messages:
            original_text = msg.text or ""
            if not original_text:
                continue
            
            # 1. Hard Filter
            hard_clean = replicator.run_hard_filters(original_text)
            hard_passed = hard_clean is not None
            
            # 2. Logical Filter (solo si pasó Hard)
            logical_passed = False
            asset = None
            direction = None
            if hard_passed:
                priority = REPLICATION_MAP[group_id]['priority']
                logical_passed, asset, direction = replicator.run_logical_filters(hard_clean, priority)
            
            # 3. Clasificación
            status = "DESCARTADO"
            reason = "No es señal/update"
            
            if not hard_passed:
                reason = "Filtro Duro (Keywords/Estructura)"
            elif not logical_passed:
                reason = "Filtro Lógico (Prioridad/Horario/Duplicado)"
            else:
                status = "PASÓ"
                reason = "Válido"

            results.append({
                "Group": group_name,
                "Message ID": msg.id,
                "Date": msg.date.strftime("%Y-%m-%d %H:%M:%S") if msg.date else "N/A",
                "Original Text": original_text[:100].replace("\n", " ") + ("..." if len(original_text) > 100 else ""),
                "Status": status,
                "Reason": reason,
                "Asset": asset,
                "Direction": direction,
                "Passed Hard": hard_passed,
                "Passed Logical": logical_passed
            })
            
    except Exception as e:
        logger.error(f"Error analizando {group_name}: {e}")
        
    return results

async def main():
    if not API_ID or not API_HASH:
        logger.error("Faltan credenciales.")
        return

    client = TelegramClient(StringSession(SESSION_STRING), int(API_ID), API_HASH)
    
    try:
        await client.start()
        
        all_results = []
        for g_id, cfg in REPLICATION_MAP.items():
            group_results = await analyze_group_history(client, g_id, cfg['name'], limit=50)
            all_results.extend(group_results)
            
        # Guardar resultados en CSV para análisis
        keys = all_results[0].keys() if all_results else []
        if keys:
            with open("analisis_mensajes.csv", "w", encoding='utf-8-sig', newline='') as f:
                dict_writer = csv.DictWriter(f, fieldnames=keys)
                dict_writer.writeheader()
                dict_writer.writerows(all_results)
        
        # Generar Reporte Markdown
        report = []
        report.append("# Reporte de Análisis de Filtros (Últimos 50 mensajes por grupo)")
        report.append(f"Fecha de análisis: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        for name in [cfg['name'] for cfg in REPLICATION_MAP.values()]:
            group_rows = [r for r in all_results if r['Group'] == name]
            total = len(group_rows)
            passed_rows = [r for r in group_rows if r['Status'] == "PASÓ"]
            passed = len(passed_rows)
            discarded = total - passed
            
            report.append(f"## Grupo: {name}")
            report.append(f"- **Total analizados:** {total}")
            report.append(f"- **Pasaron filtros:** {passed}")
            report.append(f"- **Descartados:** {discarded}")
            
            if discarded > 0:
                report.append("\n### Desglose de Descartes:")
                reasons = Counter([r['Reason'] for r in group_rows if r['Status'] == "DESCARTADO"])
                for reason, count in reasons.items():
                    report.append(f"- {reason}: {count}")
            
            if passed > 0:
                report.append("\n### Señales Identificadas (Muestra):")
                samples = passed_rows[:5]
                for row in samples:
                    report.append(f"- **ID {row['Message ID']}**: {row['Asset']} {row['Direction']} ({row['Date']})")
            
            report.append("\n---\n")
            
        with open("REPORTE_ANALISIS_FILTROS.md", "w", encoding='utf-8') as f:
            f.write("\n".join(report))
            
        logger.info("Análisis completado. Reporte generado en REPORTE_ANALISIS_FILTROS.md y datos en analisis_mensajes.csv")

    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
