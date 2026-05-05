# config.py
# Configuración centralizada para el Replicador de Telegram

# Mapeo de Replicación (ID Origen -> Lista de {ID Destino, Topic ID, Prioridad, Nombre})
REPLICATION_MAP = {
    -1002148227049: [
        {"dest": -1003797962974, "topic": 2, "name": "GTS VIP", "priority": 1}
    ],
    -1002310215234: [
        {"dest": -1003797962974, "topic": 3, "name": "44's Clup", "priority": 2, "allow_media": True},
        {"dest": -1003744952102, "name": "44's Clup (Espejo)", "priority": 2, "allow_media": True},
        {"dest": -1002490959467, "name": "44's Clup Nuevo", "priority": 2, "allow_media": True, "schedule": {"days": [1, 3], "start": "05:00", "end": "12:00", "timezone": "America/Bogota"}},
        {"dest": -1005211269420, "name": "77 Club → Nuevo Grupo", "priority": 2, "allow_media": True, "prefix": "🏆 77 Club"}
    ],
    -1002108856565: [
        {"dest": -1003797962974, "topic": 4, "name": "Gold Trader Sunny", "priority": 3},
        {"dest": -1005211269420, "name": "Sr Sniper → Nuevo Grupo", "priority": 3, "prefix": "🎯 Sr Sniper"}
    ],
    -1003737486306: [
        {"dest": -1003807690832, "name": "TEST CHANNEL", "priority": 10}
    ],
    -1003020297428: [
        {"dest": -1003827068341, "name": "fXKINGS", "priority": 5, "allow_media": True}
    ]
}

# Configuración de Filtros
PROMO_TRIGGERS = [
    "promo", "promoción", "promocion", "canal", "únete", 
    "link", "publicidad", "siguenos", "síguenos", "contact", 
    "@", "vip", "t.me/", "http", "www.", "join", "bonus", 
    "discount", "oferta", "premium", "free trial", "subscribe",
    "member", "lifetime", "payment", "binance", "bybit", 
    "registration", "account", "broker", "invest", "profit share"
]
