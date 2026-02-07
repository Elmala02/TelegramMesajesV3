# config.py
# Configuración centralizada para el Replicador de Telegram

# Mapeo de Replicación (ID Origen -> {ID Destino, Topic ID, Prioridad, Nombre})
# Prioridad: 1 es la más alta.
REPLICATION_MAP = {
    -1002148227049: {"dest": -1003797962974, "topic": 2, "name": "GTS VIP", "priority": 1},
    -1002310215234: {"dest": -1003797962974, "topic": 3, "name": "44's Clup", "priority": 2},
    -1002108856565: {"dest": -1003797962974, "topic": 4, "name": "Gold Trader Sunny", "priority": 3},
    -1003020297428: {"dest": -1003797962974, "topic": 5, "name": "FXKINGS SIGNALS", "priority": 4},
    -1003759405936: {"dest": -1003797962974, "topic": 6, "name": "GRUPO DE PRUEBAS", "priority": 5}
}

# Configuración de Filtros
KEYWORDS_OBLIGATORIAS = [
    "BUY", "SELL", "TP", "SL", "HIT", "TARGET", "BE", 
    "BREAK EVEN", "ENTRY", "TAKE PROFIT", "STOP LOSS", 
    "SIGNAL", "MOVING STOPS", "STOPS TO BE",
    "COMPRA", "VENTA", "VENDER", "COMPRAR", "ENTRADA", "ORO"
]

ANALYSIS_KEYWORDS = [
    "RESISTANCE", "SUPPORT", "SENTIMENT", "DRIVERS", 
    "SESSION OPENED", "TRADING AT"
]

PROMO_TRIGGERS = [
    "promo", "promoción", "promocion", "canal", "únete", 
    "link", "publicidad", "siguenos", "síguenos", "contact", 
    "@", "vip", "t.me/", "http", "www.", "join", "bonus", 
    "discount", "oferta", "premium", "free trial", "subscribe",
    "member", "lifetime", "payment", "binance", "bybit", 
    "registration", "account", "broker", "invest", "profit share"
]
