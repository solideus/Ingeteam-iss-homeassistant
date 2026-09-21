"""Add the 0.4.0 keys consistently without changing existing entity names."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ingeteam_iss"
KEYS = (
    "grid_import_power",
    "grid_export_power",
    "battery_charge_power",
    "battery_discharge_power",
    "pv_energy",
    "load_energy",
    "grid_import_energy",
    "grid_export_energy",
    "battery_charge_energy",
    "battery_discharge_energy",
    "sse_last_event",
    "sse_last_disconnect",
)
LANGUAGES = {
    "en": (
        [
            "Grid import power",
            "Grid export power",
            "Battery charging power",
            "Battery discharging power",
            "PV energy",
            "Household consumption energy",
            "Grid import energy",
            "Grid export energy",
            "Battery charge energy",
            "Battery discharge energy",
            "Last valid SSE event",
            "Last SSE interruption",
        ],
        "Energy",
        "SSE telemetry connected",
        "HTTP polling interval (seconds)",
        "SSE data timeout (seconds)",
        "Enter the local inverter credentials. Use a dedicated user with Installer permissions. Reference firmware: ABH1007AE.",
    ),
    "es": (
        [
            "Potencia importada de red",
            "Potencia exportada a red",
            "Potencia de carga de batería",
            "Potencia de descarga de batería",
            "Energía fotovoltaica",
            "Energía consumida por la vivienda",
            "Energía importada de red",
            "Energía exportada a red",
            "Energía de carga de batería",
            "Energía de descarga de batería",
            "Último evento SSE válido",
            "Última interrupción SSE",
        ],
        "Energía",
        "Telemetría SSE conectada",
        "Intervalo de sondeo HTTP (segundos)",
        "Tiempo sin datos SSE (segundos)",
        "Introduce el acceso local del inversor. Utiliza un usuario específico con permisos de Instalador. Firmware de referencia: ABH1007AE.",
    ),
    "fr": (
        [
            "Puissance importée du réseau",
            "Puissance injectée au réseau",
            "Puissance de charge de la batterie",
            "Puissance de décharge de la batterie",
            "Énergie photovoltaïque",
            "Énergie consommée par le logement",
            "Énergie importée du réseau",
            "Énergie injectée au réseau",
            "Énergie de charge de la batterie",
            "Énergie de décharge de la batterie",
            "Dernier événement SSE valide",
            "Dernière interruption SSE",
        ],
        "Énergie",
        "Télémétrie SSE connectée",
        "Intervalle de lecture HTTP (secondes)",
        "Délai sans données SSE (secondes)",
        "Saisissez les identifiants locaux de l’onduleur. Utilisez un utilisateur dédié avec les droits Installateur. Micrologiciel de référence : ABH1007AE.",
    ),
    "de": (
        [
            "Netzbezugsleistung",
            "Netzeinspeiseleistung",
            "Batterieladeleistung",
            "Batterieentladeleistung",
            "PV-Energie",
            "Haushaltsverbrauch",
            "Netzbezugsenergie",
            "Netzeinspeiseenergie",
            "Batterieladeenergie",
            "Batterieentladeenergie",
            "Letztes gültiges SSE-Ereignis",
            "Letzte SSE-Unterbrechung",
        ],
        "Energie",
        "SSE-Telemetrie verbunden",
        "HTTP-Abfrageintervall (Sekunden)",
        "Zeitlimit ohne SSE-Daten (Sekunden)",
        "Gib die lokalen Zugangsdaten des Wechselrichters ein. Verwende einen eigenen Benutzer mit Installateurrechten. Referenz-Firmware: ABH1007AE.",
    ),
    "it": (
        [
            "Potenza prelevata dalla rete",
            "Potenza immessa in rete",
            "Potenza di carica della batteria",
            "Potenza di scarica della batteria",
            "Energia fotovoltaica",
            "Energia consumata dall’abitazione",
            "Energia prelevata dalla rete",
            "Energia immessa in rete",
            "Energia di carica della batteria",
            "Energia di scarica della batteria",
            "Ultimo evento SSE valido",
            "Ultima interruzione SSE",
        ],
        "Energia",
        "Telemetria SSE connessa",
        "Intervallo di lettura HTTP (secondi)",
        "Tempo senza dati SSE (secondi)",
        "Inserisci le credenziali locali dell’inverter. Usa un utente dedicato con permessi Installatore. Firmware di riferimento: ABH1007AE.",
    ),
    "pt": (
        [
            "Potência importada da rede",
            "Potência exportada para a rede",
            "Potência de carga da bateria",
            "Potência de descarga da bateria",
            "Energia fotovoltaica",
            "Energia consumida pela habitação",
            "Energia importada da rede",
            "Energia exportada para a rede",
            "Energia de carga da bateria",
            "Energia de descarga da bateria",
            "Último evento SSE válido",
            "Última interrupção SSE",
        ],
        "Energia",
        "Telemetria SSE ligada",
        "Intervalo de leitura HTTP (segundos)",
        "Tempo sem dados SSE (segundos)",
        "Introduza as credenciais locais do inversor. Utilize um utilizador dedicado com permissões de Instalador. Firmware de referência: ABH1007AE.",
    ),
    "nl": (
        [
            "Vermogen afgenomen van het net",
            "Vermogen teruggeleverd aan het net",
            "Laadvermogen batterij",
            "Ontlaadvermogen batterij",
            "Zonne-energie",
            "Energieverbruik woning",
            "Energie afgenomen van het net",
            "Energie teruggeleverd aan het net",
            "Laadenergie batterij",
            "Ontlaadenergie batterij",
            "Laatste geldige SSE-gebeurtenis",
            "Laatste SSE-onderbreking",
        ],
        "Energie",
        "SSE-telemetrie verbonden",
        "HTTP-peilinterval (seconden)",
        "Time-out zonder SSE-gegevens (seconden)",
        "Voer de lokale inloggegevens van de omvormer in. Gebruik een aparte gebruiker met installateursrechten. Referentiefirmware: ABH1007AE.",
    ),
    "pl": (
        [
            "Moc pobierana z sieci",
            "Moc oddawana do sieci",
            "Moc ładowania akumulatora",
            "Moc rozładowania akumulatora",
            "Energia fotowoltaiczna",
            "Energia zużyta w domu",
            "Energia pobrana z sieci",
            "Energia oddana do sieci",
            "Energia ładowania akumulatora",
            "Energia rozładowania akumulatora",
            "Ostatnie poprawne zdarzenie SSE",
            "Ostatnia przerwa SSE",
        ],
        "Energia",
        "Telemetria SSE połączona",
        "Interwał odczytu HTTP (sekundy)",
        "Limit czasu bez danych SSE (sekundy)",
        "Wprowadź lokalne dane logowania falownika. Użyj osobnego użytkownika z uprawnieniami instalatora. Referencyjne oprogramowanie: ABH1007AE.",
    ),
}


def main():
    for code, (
        names,
        group,
        connected,
        interval,
        timeout,
        description,
    ) in LANGUAGES.items():
        path = ROOT / "translations" / f"{code}.json"
        data = json.loads(path.read_text())
        data["entity"]["sensor"].update(
            {k: {"name": v} for k, v in zip(KEYS, names, strict=True)}
        )
        data["entity"]["binary_sensor"] = {"sse_connected": {"name": connected}}
        data["device"]["energy"] = {"name": f"Ingeteam ISS · {group}"}
        data["options"]["step"]["init"]["data"].update(
            scan_interval=interval, sse_timeout=timeout
        )
        data["config"]["step"]["user"]["description"] = description
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    (ROOT / "strings.json").write_text((ROOT / "translations/en.json").read_text())


if __name__ == "__main__":
    main()
