import sys
import io
from replicator import TelegramReplicator

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def test_filters_and_sanitizer():
    replicator = TelegramReplicator(None, {})
    
    # 1. PRUEBAS DE PALABRAS PROHIBIDAS (billetera, pagos, participantes, wallet)
    filter_test_cases = [
        ("NUEVA SEÑAL XAUUSD BUY ENTRY: 2000 TP: 2010 SL: 1990", True),
        ("Por favor envíen su billetera para el depósito.", False),
        ("Los pagos se procesarán al finalizar el día.", False),
        ("Atención a todos los participantes de la clase.", False),
        ("Asegúrate de que la dirección de la wallet sea correcta.", False),
        ("Detalles de pago y cuenta bancaria", False),
        ("Revisar las wallets digitales", False),
        ("Lista de participantes actualizados", False),
        ("MENSAJE NORMAL DE TRADING GOLD BUY 2600", True),
    ]
    
    print("--- 1. PRUEBAS DE FILTRADO DE PALABRAS ---")
    all_passed = True
    for text, expected_to_pass in filter_test_cases:
        result = replicator.apply_manual_filters(text)
        passed = (result is not None) == expected_to_pass
        status = "PASÓ" if passed else "FALLÓ"
        print(f"[{status}] Texto: '{text[:45]}...' -> Permite envío: {result is not None}")
        if not passed:
            all_passed = False

    # 2. PRUEBA DE LIMPIEZA DE FUGA DE PENSAMIENTO DE IA (CoT Leakage)
    print("\n--- 2. PRUEBA DE LIMPIEZA DE FUGA DE IA (CoT LEAKAGE) ---")
    leaked_text = """execution terms. Rule 2 says: "Conserva EXACTAMENTE y en mayúsculas términos de ejecución como: BUY, SELL... STOP LOSS... TAKE PROFIT...". Let's write STOP LOSS and TAKE PROFIT or keep Stoploss / Takeprofit. Writing Stop Loss or STOP LOSS is safe. Let's check rule 2 exact wording: "Cons
BUY GOLD AHORA 4350
45, 4350, 4335, 4359, 4370, 4380, emojis intact.
4. Elimina slang residual: N/A here.
5. Respuesta limpia: Only translated text.
6. Prohibido agregar contenido: None added.
SL 4335"""

    sanitized = replicator.sanitize_text(leaked_text)
    print("Texto limpio resultante:")
    print(sanitized)
    
    # Verificar que no quedaron las líneas con fuga
    if "Rule 2 says" in sanitized or "emojis intact" in sanitized or "Respuesta limpia" in sanitized:
        print("\nFALLÓ: El sanitizador no eliminó las fugas del prompt de IA.")
        all_passed = False
    else:
        print("\nPASÓ: Las fugas de la IA fueron filtradas correctamente.")

    if all_passed:
        print("\nTODAS LAS PRUEBAS PASARON EXITOSAMENTE.")
    else:
        print("\nEXISTEN ERRORES EN LAS PRUEBAS.")
        sys.exit(1)

if __name__ == "__main__":
    test_filters_and_sanitizer()
