# Ingeteam ISS para Home Assistant — 0.4.0

[English](README.md) · [Instalación y pruebas](docs/VALIDATION.md) · [Telemetría y energía](docs/TELEMETRY_ENERGY.md) · [Publicación](docs/PUBLISHING.md)

Integración local **no oficial** para el Ingeteam INGECON SUN STORAGE ISS 6TL.
Esta versión conserva los controles, horarios, grupos, identificadores e icono de
la 0.3.0 y añade telemetría SSE y contadores de energía. No necesita Node-RED,
MQTT ni servicios en la nube. No escribe parámetros durante la instalación.

## Requisitos y acceso

- Home Assistant Core **2026.3.0 o posterior**.
- Firmware de referencia requerido: **ABH1007AE**, en el equipo probado
  (API 102, web 6.1.0, tarjeta ABH0101). No se presupone compatibilidad con otros
  modelos o versiones.
- Acceso local HTTP al inversor, normalmente puerto 80.
- **Crear un usuario específico para Home Assistant en la página de
  configuración del inversor. El nivel de permisos debe ser Instalador.**
  Esto permite distinguir los cambios realizados por Home Assistant de los
  realizados por otros usuarios en el portal. Los niveles inferiores no
  permiten escribir determinados parámetros.

La respuesta de propiedades aportada identifica además `ABH1006AC`. No se
compara ese campo automáticamente con `ABH1007AE`: no está demostrado que ambos
identifiquen el mismo componente o la misma capa de firmware. El requisito es
documental; esta versión no instala, actualiza ni bloquea firmware.

HTTP Basic no cifra las credenciales. Utiliza únicamente una red local de
confianza; no expongas el puerto HTTP del inversor a Internet. No incluyas
contraseñas en incidencias, capturas ni automatizaciones.

## Novedades

- SSE directo en `/system/events/sse/stream`, seleccionando
  `/ems/sse/phases` y el agregado `Phase = 4`.
- Solo se exponen los sensores ya existentes, cuatro potencias direccionales
  necesarias para energía y los diagnósticos de conexión.
- Controles por HTTP, con escritura serializada, relectura inmediata y
  comparación. FV1, FV2 y corriente de batería mantienen el sondeo HTTP.
- Los límites BMS de carga y descarga On-Grid son **deslizantes de 0–66 A,
  paso 1 A**. La calibración sigue siendo un permiso para atender al BMS,
  no una orden de calibración forzada.
- Seis acumuladores en un grupo nuevo **Energía**: FV, vivienda, importación,
  exportación, carga y descarga de batería.
- Supervisión de recepción válida, reconexión automática y disponibilidad
  selectiva ante batería desconectada.
- Nuevas etiquetas traducidas en español, inglés, francés, alemán, italiano,
  portugués, neerlandés y polaco.

Se registran **53 entidades** en **6 dispositivos/grupos**: los 40 identificadores
anteriores, 4 potencias direccionales, 6 energías, 1 diagnóstico de conexión y
2 fechas de diagnóstico deshabilitadas por defecto. Los nombres personalizados
y las automatizaciones existentes se conservan.

## Fuentes de datos

| Magnitud | Origen |
|---|---|
| Potencia FV total | SSE `pv` |
| Consumo de vivienda | SSE `cons`, no `total_cons` |
| Potencia neta de red | SSE `W`: positiva al importar, negativa al exportar |
| Potencia importada / exportada | `max(W, 0)` / `max(-W, 0)` |
| SOC y tensión de batería | SSE `soc` y `vbat`, sin escalado adicional |
| Potencia neta de batería | `PacDischarge - PacCharge`: positiva al descargar |
| Potencia de carga / descarga | SSE `PacCharge` / `PacDischarge` |
| FV1, FV2 y corriente de batería | HTTP online 33, 36 y 18; corriente /100 |

**Cambio de origen de FV total:** antes sumaba los strings y ahora usa `pv`
del EMS, como tu monitorización MQTT. Ambos valores no son idénticos en todas
las capturas; la integración no fuerza que coincidan. Tampoco fuerza que la
descarga de batería coincida exactamente con los flujos calculados del EMS.

Los datos HTTP se localizan por dirección y bit, nunca por la posición
`Data[n]`. Se mantiene el endpoint online que ya funcionaba: los valores
decodificados de `/properties/read` no deben recibir otra vez su escala.

## Interrupciones y batería desconectada

En opciones se configuran independientemente el **sondeo HTTP** (15 s por
defecto, 5–300 s) y el **tiempo sin datos SSE** (30 s por defecto, 10–120 s).

Un cierre de conexión o error deja los sensores SSE no disponibles. Si la
conexión queda abierta pero deja de entregar eventos válidos, actúa el tiempo
de vigilancia. Los comentarios, mensajes de otro tipo y JSON inválidos no
renuevan ese tiempo. Los valores repetidos y los ceros válidos sí lo renuevan.
La reconexión usa esperas de 1, 2, 4… hasta 60 s; los rechazos de autenticación
SSE se reintentan cada 60 s.

El diagnóstico **Telemetría SSE conectada** permite automatizar avisos. Puedes
habilitar **Último evento SSE válido** y **Última interrupción SSE** desde las
entidades deshabilitadas del dispositivo. La última recepción se conserva
durante la caída; las fechas son del reloj de Home Assistant, no del inversor,
y se reinician con la sesión. Los controles HTTP no dependen de este estado.

Con el estado observado `StatusBat = 7`, SOC, tensión, corriente y potencias
de batería quedan no disponibles. FV, vivienda y red continúan actualizando.
Los ajustes almacenados de batería siguen accesibles si su lectura HTTP es
válida. Un SOC de 0 % por sí solo no significa batería desconectada.

## Energía

Los contadores integran potencia con la regla izquierda, como el
`method: left` de tu YAML, usando el tiempo real entre recepciones. El cálculo
está incorporado en la integración: **no necesitas crear ayudantes Integral**.

- kWh, `device_class: energy` y `state_class: total`, sin reinicios diarios.
- Acumulación a precisión interna completa; presentación con tres decimales.
- Se procesa cada evento, pero el estado de energía se publica cada 30 s
  mientras hay datos, y al interrumpirse el SSE, para limitar escrituras en Recorder.
- Solo se integran intervalos válidos de hasta **5 segundos**. Un hueco mayor,
  una desconexión o un dato inválido rompe el intervalo correspondiente.
- No se extrapola energía mientras falta SSE ni durante un reinicio. Los
  totales permanecen visibles y se reanuda desde una nueva pareja de muestras.
- Guardado periódico aproximadamente cada 60 s mientras aumentan los totales,
  y al detener o recargar de forma normal. Una pérdida abrupta de alimentación
  de Home Assistant puede perder lo acumulado desde el último guardado.

Son estimaciones, no contadores fiscales ni lecturas de un contador acumulado
del inversor. Durante huecos no medidos puede faltar energía; no se inventa.
Las diferencias observadas entre `pv`, los strings, `PacDischarge` y los flujos
internos pueden trasladarse al balance del panel.

### Panel de Energía

| Apartado | Sensor nuevo |
|---|---|
| Producción solar | Energía fotovoltaica |
| Red: consumo/importación | Energía importada de red |
| Red: devolución/exportación | Energía exportada a red |
| Batería: energía entrante | Energía de carga de batería |
| Batería: energía saliente | Energía de descarga de batería |

La energía consumida por la vivienda sirve para seguimiento y contraste.
No la añadas como un consumo individual adicional a toda la vivienda ya
representada por el balance de red/FV/batería.

Los nuevos acumuladores empiezan desde cero al instalarse por primera vez:
**no importan ni reemplazan el historial de tus entidades MQTT**. Conserva
estas para comparar, pero no registres ambos juegos a la vez como fuentes
equivalentes del panel. El cambio del panel es manual; esta integración no
modifica tus dashboards, YAML ni entidades antiguas.

## Instalación o actualización

1. Haz una copia de seguridad de Home Assistant y de
   `/config/custom_components/ingeteam_iss`.
2. Sustituye esa carpeta por `custom_components/ingeteam_iss` del ZIP,
   incluyendo `brand/` y `translations/`.
3. Reinicia Home Assistant. **No borres ni vuelvas a crear la integración.**
4. Comprueba las entidades nuevas y que el diagnóstico SSE pasa a conectado.
5. Realiza la [lista de pruebas](docs/VALIDATION.md) antes de cambiar el panel
   de Energía o retirar la monitorización anterior.

En una instalación nueva, añade Ingeteam ISS desde Dispositivos y servicios.
Introduce host sin `http://`, usuario Instalador y contraseña. El ID del inversor
es un campo de escritura numérica, **1 por defecto**, entero de 1 a 247.
Los horarios se interpretan con el reloj local del inversor.

Para volver a la 0.3.0, restaura únicamente la carpeta guardada y reinicia.
Las entidades añadidas en 0.4.0 dejarán de actualizar. No borres la integración
ni sus datos internos si deseas conservar los acumuladores para volver a 0.4.0.

## Alcance y publicación

Se conservan las funciones ya probadas en la 0.3.0. Las novedades de 0.4.0 están
verificadas con pruebas automatizadas, escenarios sintéticos anonimizados en un
simulador y una primera prueba prolongada en el inversor físico de referencia.

El SSE de fases representa el agregado de la instalación. Esta versión se
dirige a **un inversor ISS por tarjeta de comunicación**. No anuncia soporte
para múltiples nodos compartiendo una tarjeta ni para mapas arbitrarios.

El repositorio incluye licencia, pruebas, estructura HACS y validaciones
automáticas HACS/Hassfest. Hasta publicar una versión etiquetada, se puede añadir
este repositorio a HACS como repositorio personalizado de tipo **Integración**.
Llegar a 1.0 no garantiza la aceptación como integración oficial: será una
revisión independiente.

[Requisitos de sensores del panel de Energía](https://www.home-assistant.io/docs/energy/faq/)
· [Regla de integración izquierda](https://www.home-assistant.io/integrations/integration/)
