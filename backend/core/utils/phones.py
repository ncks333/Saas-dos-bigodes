import re


_PHONE_CHARACTERS = re.compile(r"^\+?[\d\s().-]+$")


def normalize_brazilian_whatsapp(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("WhatsApp inválido")

    candidate = value.strip()
    if not candidate or not _PHONE_CHARACTERS.fullmatch(candidate):
        raise ValueError("WhatsApp inválido")

    digits = re.sub(r"\D", "", candidate)
    if candidate.startswith("+"):
        if len(digits) in (12, 13) and digits.startswith("55"):
            return digits
        raise ValueError("WhatsApp inválido")
    if len(digits) in (10, 11):
        return f"55{digits}"
    if len(digits) in (12, 13) and digits.startswith("55"):
        return digits
    raise ValueError("WhatsApp inválido")


def brazilian_whatsapp_lookup_values(value: str) -> tuple[str, str]:
    canonical = normalize_brazilian_whatsapp(value)
    return canonical, canonical[2:]
