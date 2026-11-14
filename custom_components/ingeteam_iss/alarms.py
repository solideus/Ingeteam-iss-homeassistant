"""Decode only meanings declared by the connected inverter's own map."""

from .sse import finite_number


def _default_alarm_fields():
    from .profiles import get_profile

    return get_profile().alarm_fields


def raw_integer(value):
    number = finite_number(value, minimum=0)
    return int(number) if number is not None and number.is_integer() else None


def label_for(mapping: dict, address: int, code: int, language: str) -> str | None:
    fields = mapping.get("online")
    field = next(
        (
            f
            for f in (fields if isinstance(fields, list) else [])
            if isinstance(f, dict) and f.get("add") == address
        ),
        {},
    )
    types = mapping.get("customtypes")
    types = types if isinstance(types, dict) else {}
    name = field.get("ty")
    custom_type = types.get(name) if isinstance(name, str) else None
    values = custom_type.get("values") if isinstance(custom_type, dict) else None
    values = values if isinstance(values, dict) else {}
    tid = values.get(f"0{code}")
    if not isinstance(tid, str):
        return None
    lang = {"es": "SPANISH", "it": "ITALIAN"}.get(language, "ENGLISH")
    langs = mapping.get("langs")
    labels = langs.get(lang) if isinstance(langs, dict) else None
    label = labels.get(tid) if isinstance(labels, dict) else None
    if (
        not isinstance(label, str)
        or not label.strip()
        or label.strip().lower().startswith(("bit ", "freeuse", "libre"))
    ):
        return None
    return label


def decode_alarms(
    online: dict, mapping: dict, language="en", fields=None, hex_widths=None
) -> tuple[list[dict], dict]:
    alarms, raw = [], {}
    if fields is None:
        from .profiles import get_profile

        profile = get_profile()
        fields = profile.alarm_fields
        if hex_widths is None:
            hex_widths = profile.alarm_hex_widths
    hex_widths = hex_widths or {}
    for address, category in fields.items():
        value = raw_integer(online.get((address, 0)))
        if value is None:
            continue
        raw[category] = f"0x{value:0{hex_widths.get(address, 4)}X}"
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


def __getattr__(name):
    if name == "ALARM_FIELDS":
        return _default_alarm_fields()
    raise AttributeError(name)
