"""Decode only meanings declared by the connected inverter's own map."""

from .sse import finite_number

ALARM_FIELDS = {
    10: "inverter_alarm",
    12: "inverter_code_1",
    13: "inverter_code_2",
    14: "inverter_code_3",
    28: "battery_alarm",
    73: "bms_warning",
    74: "bms_error",
    75: "bms_fault",
    76: "bms_protection",
}


def raw_integer(value):
    number = finite_number(value, minimum=0)
    return int(number) if number is not None and number.is_integer() else None


def label_for(mapping: dict, address: int, code: int, language: str) -> str | None:
    field = next(
        (
            f
            for f in mapping.get("online", [])
            if isinstance(f, dict) and f.get("add") == address
        ),
        {},
    )
    values = mapping.get("customtypes", {}).get(field.get("ty"), {}).get("values", {})
    tid = values.get(f"0{code}")
    lang = {"es": "SPANISH", "it": "ITALIAN"}.get(language, "ENGLISH")
    label = mapping.get("langs", {}).get(lang, {}).get(tid)
    if not isinstance(label, str) or label.lower().startswith(
        ("bit ", "freeuse", "libre")
    ):
        return None
    return label


def decode_alarms(
    online: dict, mapping: dict, language="en"
) -> tuple[list[dict], dict]:
    alarms, raw = [], {}
    for address, category in ALARM_FIELDS.items():
        value = raw_integer(online.get((address, 0)))
        if value is None:
            continue
        raw[category] = f"0x{value:08X}" if address == 10 else f"0x{value:04X}"
        for bit in range(value.bit_length()):
            if value & (1 << bit):
                label = label_for(mapping, address, bit, language)
                alarms.append(
                    {
                        "category": category,
                        "address": address,
                        "bit": bit,
                        "code": f"0x{1 << bit:X}",
                        "documented": label is not None,
                        "description": label
                        or (
                            f"Código no documentado: bit {bit}"
                            if language == "es"
                            else f"Undocumented code: bit {bit}"
                        ),
                    }
                )
    return alarms, raw


def flow_state(value, positive, negative, threshold=10):
    value = finite_number(value)
    if value is None:
        return None
    return positive if value > threshold else negative if value < -threshold else "idle"
