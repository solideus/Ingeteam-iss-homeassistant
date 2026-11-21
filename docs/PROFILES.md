# Guía para aportar un perfil de inversor

Esta guía describe la base de perfiles de 0.6.0. Su primer objetivo es conservar el comportamiento del **INGECON SUN STORAGE 1Play TL M — 2 MPPT**, probado en el **6TL M** con firmware de portal de referencia **ABH1007AE**. El identificador interno del perfil es `tl_m`.

La generación **INGECON SUN STORAGE 1Play TL — 1 MPPT, sin M** utiliza otros registros y eventos. No queda soportada por preparar esta arquitectura. Su incorporación corresponde a un PR posterior; el [PR #8 cerrado sin fusionar](https://github.com/solideus/Ingeteam-iss-homeassistant/pull/8) conserva la investigación del colaborador.

## Límite entre perfil e infraestructura

El perfil describe lo que significa la información de un modelo. La infraestructura mantiene la conexión, publica entidades y conserva energía. Añadir un modelo no debería requerir editar el directorio `profiles/tl_m/` ni introducir condiciones como `if model == ...` en las plataformas comunes.

La separación reduce el riesgo, pero no ofrece aislamiento absoluto: ambos perfiles compartirán Home Assistant, el cliente HTTP/SSE, las entidades base y la contabilidad. Un cambio en esa infraestructura requiere su propia justificación y regresiones del TL M, aunque se haya originado en otro modelo.

| Responsabilidad | Ubicación |
|---|---|
| Contrato del perfil | `custom_components/ingeteam_iss/profiles/base.py` |
| Tipos de descripción de entidades | `profiles/descriptions.py` |
| Registro explícito y resolución de perfil | `profiles/__init__.py` |
| Registros y capacidades del modelo | `profiles/<id>/registers.py` |
| Definiciones de sensores y controles | `profiles/<id>/entities.py` |
| Decodificación de telemetría del modelo | `profiles/<id>/telemetry.py` |
| Interpretación de estados operativos | `profiles/<id>/states.py` |
| Cliente HTTP, coordinadores y plataformas genéricas | Módulos comunes de `ingeteam_iss` |
| Integración numérica, calendario, persistencia y Recorder | Infraestructura energética común |

El registro es explícito. Un identificador introducido en un formulario no puede convertirse en una ruta de importación ni cargar código arbitrario. Las entradas anteriores sin perfil siguen usando `tl_m`; un identificador desconocido debe generar un error controlado.

En 0.6.0 el alta muestra únicamente el perfil registrado `tl_m`. La reconfiguración conserva el perfil de la entrada y rechaza un cambio implícito de modelo; no ofrece un selector para hacerlo. Que exista el contrato no permite seleccionar por adelantado `storage_1play` ni activar el soporte del TL anterior mediante un identificador oculto. Una futura migración de perfil necesita un proceso revisado que demuestre la conservación de identidades e históricos.

## 1. Identificar el equipo y reunir evidencia

Antes de escribir código, aporta:

- Modelo completo de la placa, incluida la presencia o ausencia de **M**, potencia y variante. Oculta el número de serie.
- Modelo de tarjeta, versión del portal, API y referencias del mapa. Distingue la versión instalada de la mera declaración `compatible.firmware`.
- Mapa completo anonimizado y documentación original con revisión y fecha.
- Eventos completos de cada tipo relevante en situaciones normales: producción solar, descarga nocturna, carga desde red y exportación, cuando existan en esa instalación.
- Descripción del cableado que afecte a la medición: cargas críticas, otras cargas, vatímetro, generación externa y número de inversores por tarjeta.

No identifiques la generación contando conectores: el TL anterior puede tener dos entradas FV y un único MPPT. No deduzcas compatibilidad de una fecha reciente, de API 102 o de un prefijo de firmware aislado. No incluyas contraseñas, tokens, cabeceras de autorización, direcciones privadas, seriales ni registros sin anonimizar.

## 2. Crear el perfil sin modificar el existente

Crea un directorio propio bajo `profiles/` y declara una instancia del contrato `ModelProfile`. Usa `tl_m` como ejemplo de estructura, no como tabla universal de direcciones. Registra el nuevo perfil explícitamente en `profiles/__init__.py` junto con su identificación y pruebas.

El contrato agrupa las descripciones `sensors`, `numbers`, `selects`, `switches`, `times`, `operating_states` y `flow_states`, los rangos de lectura, los campos de alarma, su anchura hexadecimal de presentación (`alarm_hex_widths`) y las reglas de batería y capacidades. `id` es estable; `name` identifica la familia y `reference_firmware` documenta la referencia comprobada, no una garantía universal de compatibilidad.

Las definiciones son inmutables: rangos `ReadRange(address, length)` en tuplas, descripciones congeladas y campos de alarma en un mapa de solo lectura. `ReadRange.payload()` crea el diccionario de petición; no modifiques objetos del perfil para construir una lectura o adaptar una entrada. Las descripciones de estado operativo indican si consumen datos de telemetría (`source="telemetry"`) o HTTP (`source="http"`) y una función `evaluator(data)` que devuelve `True`, `False` o `None`.

Los estados de flujo, como importación/exportación o carga/descarga, utilizan `FlowStateDescription`: una clave estable, una tupla de opciones y `evaluator(data)` que devuelve una de esas opciones o `None`. Sus reglas y umbrales pertenecen al perfil, no al sensor común. `alarm_hex_widths` asocia direcciones de alarma a la anchura hexadecimal de presentación; debe describir ese mapa, sin asumir que una dirección concreta siempre representa 16 o 32 bits.

`map_validator(capabilities)` devuelve un motivo de incompatibilidad o `None`; `resolve_profile()` combina la selección explícita con esa validación. La regla debe detectar contradicciones demostradas y no confundir firmware de portal, firmware interno y referencia compatible del mapa. `battery_available(sample)` define la disponibilidad de medidas HTTP dependientes de una batería válida.

El TL M conserva su comportamiento histórico cuando no hay mapa; un mapa que identifica al TL sin M se rechaza antes del primer sondeo. No copies ese fallback automáticamente a un perfil nuevo: su evidencia de identificación y el comportamiento sin mapa deben definirse y probarse expresamente.

Utiliza las firmas y tipos definidos en `base.py` y `descriptions.py` de la revisión concreta sobre la que trabajas. No añadas una importación del nuevo perfil a una plataforma genérica: el perfil debe entregar las descripciones que esa plataforma consume.

Una nueva entidad necesita una clave estable, traducción, unidad, clase de dispositivo/estado cuando corresponda, disponibilidad y origen demostrado. Expón una selección útil para el uso cotidiano. Los diagnósticos avanzados deben estar deshabilitados por defecto; no conviertas todo el mapa en entidades.

Para el modelo nuevo, documenta cualquier entidad que no exista o cuyo significado difiera. No reutilices una clave de una magnitud para otra distinta. Si una función necesita cambiar el contrato o el cliente común, propón ese cambio aparte antes de incorporar el modelo.

### Ejemplo de construcción y registro

Este esquema muestra un perfil nuevo inicialmente sin controles. Los módulos importados deben implementarse con datos propios comprobados; los nombres de ejemplo no añaden soporte real a ningún inversor:

```python
# profiles/new_model/__init__.py
from ..base import ModelProfile
from .entities import SENSORS
from .registers import (
    ALARM_FIELDS, ALARM_HEX_WIDTHS, ONLINE_READS, validate_map,
)
from .states import FLOW_STATES, OPERATING_STATES, battery_available
from .telemetry import NewModelDecoder

PROFILE = ModelProfile(
    id="new_model",
    name="Modelo documentado — experimental",
    reference_firmware="referencia_comprobada",
    platforms=("sensor", "binary_sensor"),
    holding_ranges=(),
    online_ranges=ONLINE_READS,
    alarm_fields=ALARM_FIELDS,
    alarm_hex_widths=ALARM_HEX_WIDTHS,
    create_decoder=NewModelDecoder,
    map_validator=validate_map,
    battery_available=battery_available,
    sensors=SENSORS,
    numbers=(),
    selects=(),
    switches=(),
    times=(),
    operating_states=OPERATING_STATES,
    flow_states=FLOW_STATES,
)
```

En `profiles/__init__.py`, añade la importación y una entrada al mapa explícito existente, conservando el TL M y su identificador predeterminado:

```python
from .new_model import PROFILE as NEW_MODEL_PROFILE

PROFILES = MappingProxyType({
    PROFILE.id: PROFILE,  # Perfil TL M ya registrado.
    NEW_MODEL_PROFILE.id: NEW_MODEL_PROFILE,
})
```

Añade también la etiqueta del nuevo identificador al selector de perfil en los ocho idiomas y en `strings.json`. Antes de habilitar controles, añade sus descripciones y plataformas al propio perfil, y amplía sus pruebas y evidencia física. No uses `dataclasses.replace()` sobre el perfil TL M para construir el de otro modelo: una nueva generación debe declarar sus propias correspondencias y reglas de forma explícita.

## 3. Proteger la identificación y las escrituras

Una dirección presente no garantiza una función compatible: en el TL sin M, HR58 es un umbral de tensión de salida digital, mientras el TL M lo utiliza para otro control. La identificación debe contrastar capacidades y significados relevantes, no aceptar simplemente que una lectura devuelve datos.

Empieza el perfil experimental con monitorización. Añade controles después de documentar, para cada uno:

| Dato necesario | Comprobación |
|---|---|
| Dirección y bit | Coinciden con el campo propio del modelo |
| Tipo, escala, rango y opciones | Coinciden con la documentación y las respuestas reales |
| Significado y permisos | El ajuste es el anunciado y el usuario tiene acceso suficiente |
| Escritura | Solo los campos solicitados; rechazo antes de HTTP de campos/valores no permitidos |
| Confirmación | Respuesta de aceptación, relectura inmediata y comparación |
| Registro compartido | Los demás campos permanecen intactos |
| Restauración | El valor original se recupera y se vuelve a confirmar |

No pruebes protecciones, normativa, tipo de batería ni límites eléctricos arbitrariamente. Las pruebas físicas deben usar cambios previamente seguros y conocidos por el responsable de la instalación. Un readback correcto demuestra aceptación y conservación del valor; no demuestra todos sus efectos operativos ni convierte el rango de la interfaz en una recomendación eléctrica.

Las escrituras deben estar serializadas. Una operación con varios campos, alguno inválido, se rechaza antes de enviar cualquier petición. Setup, sondeo y validación de conexión no escriben. No cambies el historial del equipo para probar otro perfil ni elimines entidades como parte del arranque.

## 4. Telemetría y contrato energético

`create_decoder()` construye una instancia nueva por entrada de configuración. Nunca guardes el último evento, estado de batería o temporizador en la definición global del perfil. La instancia implementa:

- `decode(event, now)`: recibe un `SSEEvent` completo y tiempo monotónico; devuelve una muestra normalizada o `None`.
- `is_sample_event(event)`: indica si el evento corresponde a muestras de potencia de este perfil. Si una de esas muestras es inválida, la infraestructura puede romper las anclas energéticas sin tratarla como un evento auxiliar ajeno.
- `reset()`: descarta estados y anclas auxiliares del decodificador al desconectar o detener la entrada.

Solo devuelve una muestra normalizada cuando corresponde al evento y equipo del perfil. Define los campos ausentes como no disponibles; nunca los sustituyas por cero ni arrastres lecturas antiguas. Valida identificadores de fase, duplicados, campos numéricos, signos y coherencia del conjunto recibido.

Si necesitas combinar eventos, especifica cómo se asocian al equipo y cuánto tiempo siguen siendo válidos sus campos. La llegada de comentarios o estados auxiliares no prueba que haya una nueva muestra de potencia. Los eventos inválidos y los datos de otro equipo no deben renovar el watchdog ni alimentar energía.

Los acumuladores comunes consumen estas potencias normalizadas en W:

| Campo | Significado |
|---|---|
| `pv_total_power` | Producción FV total observada |
| `total_load_power` | Consumo de vivienda con su frontera de medida documentada |
| `grid_import_power` / `grid_export_power` | Flujos direccionales no negativos de la red pública |
| `battery_charge_power` / `battery_discharge_power` | Flujos direccionales no negativos de batería |

No cambies las integrales, temporizadores o persistencia para hacer coincidir un modelo. Justifica las fórmulas con sus capturas y la topología; un puerto AC Loads no representa necesariamente toda la vivienda. No extrapoles huecos ni combines Phase 4 con fases individuales. Toda regla específica de agregación debe permanecer en el nuevo perfil.

## 5. Pruebas del perfil y regresión del TL M

El PR debe incluir fixtures anonimizados y pruebas reproducibles, independientes de Internet y del inversor físico. Conserva intactas las pruebas del perfil existente. Ejecuta desde la raíz:

```sh
python -m pip install -r requirements-test.txt
ruff check custom_components tests scripts
python -m pytest -q
```

La matriz soportada incluye Home Assistant Core 2026.3.0 y 2026.9.3 con Python 3.14. Una nueva versión debe mostrar sus propios resultados, sin reutilizar los números históricos de 0.5.3.

Comprueba alta/reconfiguración, identificadores, controles disponibles y deshabilitados, ausencia de escrituras durante setup, lectura y reproducción de capturas, payloads, bits compartidos, rechazos y confirmaciones. Incluye muestras parciales, duplicadas, inválidas, batería no disponible, datos auxiliares caducados, desconexión/reconexión y descarga de tareas.

Para energía, compara incrementos con series simultáneas y relojes alineados en los cuatro escenarios citados. Marca reinicios y huecos; no atribuyas discrepancias a ellos sin evidencia temporal. Verifica también cierre horario, día/mes, ambos cambios de horario de Madrid, persistencia y la hora estadística de Recorder. Para cambios comunes, compara las mismas secuencias contra la referencia v0.5.3, además de los resultados del nuevo perfil.

## 6. Prueba física y entrega del colaborador

Distribuye la rama de pruebas de forma explícita como experimental, identificando commit y versión. Haz una copia de seguridad de Home Assistant, conserva la entrada existente y no selecciones fuentes duplicadas en Energía. No publiques datos de acceso al equipo para facilitar pruebas remotas.

El registro de validación debe separar observaciones físicas, resultados del simulador e hipótesis. Incluye modelo exacto, firmware, revisión del mapa, versiones de HA/Python, escenarios, intervalo y método de comparación, resultado de cada ajuste y límites pendientes. No anuncies soporte trifásico, multiinversor o de variantes no probadas a partir de una instalación monofásica.

Entrega un PR nuevo que añada el perfil, sus pruebas, traducciones y documentación. Enlaza la evidencia previa del issue #7/PR #8 y detalla cualquier cambio común por separado. La aportación del tester no sustituye la revisión del mantenedor ni las regresiones del TL M. Solo después de estas comprobaciones se puede valorar su incorporación y publicación.
