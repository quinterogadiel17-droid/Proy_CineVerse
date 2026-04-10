from datetime import datetime

try:
    from catalog import PAYMENT_METHODS as CATALOG_PAYMENT_METHODS
except ImportError:
    CATALOG_PAYMENT_METHODS = ["tarjeta", "nequi", "bancolombia", "otro"]


PAYMENT_LABELS = {
    "tarjeta": "Tarjeta",
    "nequi": "Nequi",
    "bancolombia": "Bancolombia",
    "otro": "Otro metodo local",
}

METHOD_ALIASES = {
    "credito": "tarjeta",
    "debito": "tarjeta",
    "credit-card": "tarjeta",
    "card": "tarjeta",
    "transferencia": "bancolombia",
    "cuenta": "bancolombia",
}


def _clean_text(value, fallback=""):
    text = " ".join(str(value or "").strip().split())
    return text or fallback


def _digits(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _mask_value(value, fallback="simulado"):
    cleaned = _digits(value) or _clean_text(value)
    if not cleaned:
        return fallback
    visible = cleaned[-4:] if len(cleaned) >= 4 else cleaned
    return f"***{visible}"


def _normalize_method(method):
    candidate = _clean_text(method).lower()
    if not candidate:
        return "otro"
    candidate = METHOD_ALIASES.get(candidate, candidate)
    if candidate in CATALOG_PAYMENT_METHODS:
        return candidate
    return "otro"


def _build_reference(method_key):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"SIM-{method_key.upper()}-{timestamp}"


def _build_details(method_key, payload):
    if method_key == "tarjeta":
        month = _clean_text(payload.get("exp_month"))
        year = _clean_text(payload.get("exp_year"))
        expiration = f"{month}/{year}" if month and year else "No proporcionada"
        return {
            "holder_name": _clean_text(payload.get("holder_name"), "Cliente CineVerse"),
            "masked_instrument": _mask_value(payload.get("card_number")),
            "expiration": expiration,
        }

    if method_key == "nequi":
        return {
            "holder_name": _clean_text(payload.get("holder_name"), "Cliente CineVerse"),
            "masked_instrument": _mask_value(payload.get("phone")),
        }

    if method_key == "bancolombia":
        return {
            "holder_name": _clean_text(payload.get("owner_name"), "Cliente CineVerse"),
            "account_type": _clean_text(payload.get("account_type"), "No especificada"),
            "masked_instrument": _mask_value(payload.get("account_number")),
        }

    return {
        "provider": _clean_text(payload.get("provider"), "Metodo local simulado"),
        "reference_hint": _clean_text(payload.get("reference"), "Sin referencia"),
    }


def validate_payment(method, payload):
    """
    Simula pagos para el entorno academico.

    No valida si el medio de pago es real, no consulta servicios externos
    y aprueba la transaccion con base en el formato general recibido.
    """
    payment_payload = payload if isinstance(payload, dict) else {}
    method_key = _normalize_method(method or payment_payload.get("method"))
    approved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    normalized = {
        "method": PAYMENT_LABELS.get(method_key, "Otro metodo local"),
        "reference": _build_reference(method_key),
        "status": "Aprobado",
        "simulation": True,
        "processed_at": approved_at,
        "details": {
            "channel": method_key,
            "note": (
                "Pago procesado en modo simulacion academica. "
                "No se verifico autenticidad ni se consultaron pasarelas externas."
            ),
            **_build_details(method_key, payment_payload),
        },
    }

    return True, None, normalized
