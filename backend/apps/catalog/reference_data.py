"""Reference data loaded by migration (production needs it too, not only dev seed)."""

CATEGORIES = [
    # slug, name_es, name_en, icon (Ionicons)
    ("art", "Arte", "Art", "color-palette"),
    ("music", "Música", "Music", "musical-notes"),
    ("theater", "Teatro y artes escénicas", "Theater & Performance", "film"),
    ("comedy", "Comedia", "Comedy", "happy"),
    ("beauty", "Belleza y maquillaje", "Beauty & Makeup", "sparkles"),
    ("mechanics", "Mecánica y oficios", "Mechanics & Trades", "construct"),
    ("languages", "Idiomas", "Languages", "language"),
    ("technology", "Tecnología", "Technology", "code-slash"),
    ("sports", "Deporte y movimiento", "Sports & Movement", "bicycle"),
    ("wellbeing", "Espiritualidad y bienestar", "Spirituality & Wellbeing", "leaf"),
    ("cooking", "Cocina", "Cooking", "restaurant"),
    ("crafts", "Manualidades", "Crafts", "cut"),
    ("business", "Negocios", "Business", "briefcase"),
    ("photography", "Fotografía y video", "Photography & Video", "camera"),
    ("dance", "Baile", "Dance", "body"),
]

# slug, name, alcaldía, lat, lng (approximate centroids)
CDMX_AREAS = [
    ("roma-norte", "Roma Norte", "Cuauhtémoc", 19.4194, -99.1617),
    ("roma-sur", "Roma Sur", "Cuauhtémoc", 19.4065, -99.1620),
    ("condesa", "Condesa", "Cuauhtémoc", 19.4123, -99.1737),
    ("juarez", "Juárez", "Cuauhtémoc", 19.4270, -99.1600),
    ("cuauhtemoc", "Cuauhtémoc", "Cuauhtémoc", 19.4316, -99.1620),
    ("centro-historico", "Centro Histórico", "Cuauhtémoc", 19.4326, -99.1332),
    ("santa-maria-la-ribera", "Santa María la Ribera", "Cuauhtémoc", 19.4480, -99.1610),
    ("san-rafael", "San Rafael", "Cuauhtémoc", 19.4380, -99.1640),
    ("tabacalera", "Tabacalera", "Cuauhtémoc", 19.4360, -99.1520),
    ("doctores", "Doctores", "Cuauhtémoc", 19.4210, -99.1450),
    ("obrera", "Obrera", "Cuauhtémoc", 19.4150, -99.1400),
    ("polanco", "Polanco", "Miguel Hidalgo", 19.4330, -99.1910),
    ("anzures", "Anzures", "Miguel Hidalgo", 19.4290, -99.1800),
    ("escandon", "Escandón", "Miguel Hidalgo", 19.4010, -99.1800),
    ("san-miguel-chapultepec", "San Miguel Chapultepec", "Miguel Hidalgo", 19.4120, -99.1860),
    ("tacubaya", "Tacubaya", "Miguel Hidalgo", 19.4020, -99.1900),
    ("lomas-de-chapultepec", "Lomas de Chapultepec", "Miguel Hidalgo", 19.4230, -99.2140),
    ("del-valle", "Del Valle", "Benito Juárez", 19.3880, -99.1660),
    ("narvarte", "Narvarte", "Benito Juárez", 19.3960, -99.1530),
    ("napoles", "Nápoles", "Benito Juárez", 19.3940, -99.1760),
    ("portales", "Portales", "Benito Juárez", 19.3670, -99.1470),
    ("mixcoac", "Mixcoac", "Benito Juárez", 19.3760, -99.1880),
    ("insurgentes-mixcoac", "Insurgentes Mixcoac", "Benito Juárez", 19.3720, -99.1820),
    ("xoco", "Xoco", "Benito Juárez", 19.3600, -99.1680),
    ("coyoacan-centro", "Coyoacán Centro", "Coyoacán", 19.3500, -99.1620),
    ("copilco", "Copilco", "Coyoacán", 19.3370, -99.1770),
    ("san-angel", "San Ángel", "Álvaro Obregón", 19.3460, -99.1900),
    ("santa-fe", "Santa Fe", "Álvaro Obregón", 19.3600, -99.2600),
    ("tlalpan-centro", "Tlalpan Centro", "Tlalpan", 19.2900, -99.1660),
    ("lindavista", "Lindavista", "Gustavo A. Madero", 19.4890, -99.1300),
    ("azcapotzalco-centro", "Azcapotzalco Centro", "Azcapotzalco", 19.4840, -99.1860),
]

STANDARD_POLICY = {
    "code": "standard",
    "name_es": "Estándar",
    "name_en": "Standard",
    "description_es": (
        "Cancela 24 horas o más antes del inicio y recibes el 100% (incluida la tarifa de servicio). "
        "Con menos de 24 horas recibes el 50% del precio publicado; la tarifa de servicio no se reembolsa. "
        "Si no asistes, no hay reembolso."
    ),
    "description_en": (
        "Cancel 24 hours or more before the start for a 100% refund, service fee included. "
        "Less than 24 hours before: 50% of the listed price; the service fee is not refunded. "
        "No-shows are not refunded."
    ),
    "rules": [
        # applies_to, min_h, max_h, listed_pct, refund_fee
        ("learner_cancel", 24, None, 100, True),
        ("learner_cancel", 0, 24, 50, False),
        ("no_show", 0, None, 0, False),
    ],
}
