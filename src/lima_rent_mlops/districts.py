"""Distritos de Lima Metropolitana y Callao: nombre oficial, UBIGEO y alias de los portales."""

from __future__ import annotations

import unicodedata

# UBIGEO del INEI -> nombre oficial. Lima Metropolitana (1501xx) y Callao (0701xx).
UBIGEO = {
    "150101": "Lima",
    "150102": "Ancón",
    "150103": "Ate",
    "150104": "Barranco",
    "150105": "Breña",
    "150106": "Carabayllo",
    "150107": "Chaclacayo",
    "150108": "Chorrillos",
    "150109": "Cieneguilla",
    "150110": "Comas",
    "150111": "El Agustino",
    "150112": "Independencia",
    "150113": "Jesús María",
    "150114": "La Molina",
    "150115": "La Victoria",
    "150116": "Lince",
    "150117": "Los Olivos",
    "150118": "Lurigancho",
    "150119": "Lurín",
    "150120": "Magdalena del Mar",
    "150121": "Pueblo Libre",
    "150122": "Miraflores",
    "150123": "Pachacámac",
    "150124": "Pucusana",
    "150125": "Puente Piedra",
    "150126": "Punta Hermosa",
    "150127": "Punta Negra",
    "150128": "Rímac",
    "150129": "San Bartolo",
    "150130": "San Borja",
    "150131": "San Isidro",
    "150132": "San Juan de Lurigancho",
    "150133": "San Juan de Miraflores",
    "150134": "San Luis",
    "150135": "San Martín de Porres",
    "150136": "San Miguel",
    "150137": "Santa Anita",
    "150138": "Santa María del Mar",
    "150139": "Santa Rosa",
    "150140": "Santiago de Surco",
    "150141": "Surquillo",
    "150142": "Villa El Salvador",
    "150143": "Villa María del Triunfo",
    "070101": "Callao",
    "070102": "Bellavista",
    "070103": "Carmen de la Legua Reynoso",
    "070104": "La Perla",
    "070105": "La Punta",
    "070106": "Ventanilla",
    "070107": "Mi Perú",
}
DISTRICTS = sorted(set(UBIGEO.values()))


def _key(name: str) -> str:
    text = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return " ".join(text.lower().replace("-", " ").split())


# Variantes que usan los portales y las fuentes públicas.
_ALIASES = {
    "ate vitarte": "Ate",
    "cercado de lima": "Lima",
    "lima cercado": "Lima",
    "cercado": "Lima",
    "magdalena": "Magdalena del Mar",
    "surco": "Santiago de Surco",
    "san martin de porras": "San Martín de Porres",
    "smp": "San Martín de Porres",
    "sjl": "San Juan de Lurigancho",
    "sjm": "San Juan de Miraflores",
    "villa maria del triunfo": "Villa María del Triunfo",
    "carmen de la legua": "Carmen de la Legua Reynoso",
    "pachacamac": "Pachacámac",
}
_BY_KEY = {_key(name): name for name in DISTRICTS} | _ALIASES


def normalize(name: str | None) -> str | None:
    """Devuelve el nombre oficial del distrito, o None si no es de Lima Metropolitana/Callao."""
    if not name:
        return None
    return _BY_KEY.get(_key(name))


# Series trimestrales del BCRP (fuente: avisos de Urbania procesados por el BCRP).
# Precio de venta de departamentos en US$ por m² y PER (precio / alquiler anual).
BCRP_SERIES = {
    "Barranco": ("PD37957PQ", "PD41940PQ"),
    "Jesús María": ("PD17464PQ", "PD41941PQ"),
    "La Molina": ("PD17459PQ", "PD41942PQ"),
    "Lince": ("PD17465PQ", "PD41943PQ"),
    "Magdalena del Mar": ("PD17466PQ", "PD41944PQ"),
    "Miraflores": ("PD17460PQ", "PD41945PQ"),
    "Pueblo Libre": ("PD17467PQ", "PD41946PQ"),
    "San Borja": ("PD17461PQ", "PD41947PQ"),
    "San Isidro": ("PD17462PQ", "PD41948PQ"),
    "San Miguel": ("PD17468PQ", "PD41949PQ"),
    "Santiago de Surco": ("PD17463PQ", "PD41950PQ"),
    "Surquillo": ("PD37958PQ", "PD41951PQ"),
}
