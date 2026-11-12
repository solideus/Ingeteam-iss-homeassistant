# Registro de cambios

## Sin publicar — Selector de modelo y perfil STORAGE 1Play

- Añade un paso de modelo al alta, con el modelo detectado en el mapa del
  inversor, y lo permite cambiar al reconfigurar. Las entradas existentes
  conservan el perfil ISS sin cambios.
- Nuevo perfil experimental de solo lectura para INGECON SUN STORAGE 1Play
  (mapa ABH1002AL, tarjeta AAX0077, firmware AAX1055DC): decodifica
  `/ems/sse/phases` sin fase 4 sumando las fases 1–3 y toma los estados de
  `/ems/sse/stream`.
- Expone todos los registros online del mapa 1Play con su escala (tensiones,
  corrientes, frecuencias, temperaturas, aislamiento, SOH, estados) y decodifica
  sus alarmas en sus propias direcciones; «conectado a red» usa el bit 0 del
  estado del inversor (Modbus 30013).
- El perfil 1Play no carga plataformas de control, no lee registros holding,
  rechaza escrituras y elimina al arrancar los controles y las cadenas FV que
  hubiera dejado una entrada ISS.
- Pruebas con capturas reales del 1Play y documentación en
  `docs/STORAGE_1PLAY.md`.

## 0.5.3 — Correcciones de balance horario y robustez

- Cierra el balance neto a HH:59:55 y publica inmediatamente los acumulados,
  antes del límite de la hora estadística. Mantiene periodos de 60 minutos y
  conserva en el siguiente balance la energía observada después del cierre.
- Añade un temporizador horario independiente de SSE, cancelado al descargar.
  Cierres repetidos no vuelven a contabilizar el periodo.
- Restaura y publica los subtotales antes de procesar cierres y reinicios de
  calendario, conservando los incrementos pendientes en los históricos.
- Conserva alarmas conocidas cuando falta su categoría; expone cobertura y
  categorías pendientes de confirmar. Una lectura parcial sin códigos no se
  presenta como ausencia confirmada de alarmas.
- Rechaza números, modos, bits y horas inválidos sin truncarlos ni mantener
  valores antiguos disponibles. Un campo defectuoso no interrumpe los restantes.
- Valida estructuras HTTP y mapas incompletos para aislar los errores de
  telemetría y conservar los controles con lectura válida.
- Captura los errores de credenciales durante el alta, según la observación de
  la revisión HACS, y amplía el mensaje de configuración en ocho idiomas.
- Añade cuatro capturas SSE originales y regresiones de los casos anteriores,
  incluidas estadísticas horarias reales de Recorder con SQLite.
- Conserva identidades, unidades, acumulados, límite ordinario de publicación de
  energía de 30 s y resolución asíncrona de zona horaria.
- No modifica las estadísticas históricas ya generadas ni estima energía durante
  huecos sin datos. Los cierres recuperados tras una parada tienen la fecha de
  su publicación al reiniciar, sin reconstruir la hora de apagado.

## 0.5.2 — Optimización de sensores de energía

- Los nueve sensores de calendario y balance neto heredan el límite de publicación
  de energía de 30 s. Se sigue integrando cada muestra SSE válida, con la misma
  precisión interna, persistencia e identificadores.
- Los cierres de hora y reinicios de día/mes publican inmediatamente el subtotal
  final y el cero correspondiente, incluso sin nuevas muestras SSE. Esto evita
  ocultar energía o reinicios a las estadísticas `total_increasing`.
- Se conservan el balance horario con signo y `state_class: measurement`, la
  frecuencia de los sensores de potencia y sus automatizaciones.
- Menos registros nuevos en Recorder; esta actualización no elimina ni compacta
  los registros históricos existentes.
- Se mantiene la resolución asíncrona de zona horaria de 0.5.1 requerida por HACS.
- Pruebas con reloj simulado para las cuatro frecuencias SSE, cierres de período,
  ambos cambios de horario de Madrid, desconexión, restauración y estadísticas.

## 0.5.1

- Resuelve la zona horaria mediante `dt_util.async_get_time_zone` durante el
  arranque y pasa el objeto `tzinfo` a los coordinadores y contadores energéticos.
  Evita la lectura bloqueante de archivos de zona horaria en el bucle de eventos.
- Conserva los cálculos de energía, los periodos locales y los cambios de horario.
- Añade pruebas de regresión para la resolución asíncrona y el uso de `tzinfo`.

## 0.5.0

- Frecuencia de publicación: Tiempo real — SSE (predeterminada), 5, 10 o 30 s.
  La recepción, el watchdog y la integración energética procesan cada muestra.
- Reconfiguración de host, puerto, usuario, contraseña, ID y frecuencia;
  reautenticación, validación previa y migración conservando entidades e históricos.
- Consumo diario y mensual, con periodos de la zona horaria de Home Assistant.
- Balance neto por hora: importación/exportación netas acumulativas, balance de
  la hora en curso y medidores netos diarios/mensuales. Implementación propia
  basada en el comportamiento documentado de ha-balance-neto.
- Persistencia del saldo pendiente; separación de intervalos al cruzar horas;
  protección frente a reinicios, huecos, saltos de reloj y cambios de horario.
- Estados de red y batería, FV activa, conexión a red, alarma y reducción de potencia.
- Alarmas interpretadas mediante el mapa del equipo, categoría y hexadecimal
  conservados; evento `ingeteam_iss_alarm` al activar/desactivar cada código.
  Los bits sin descripción BMS permanecen explícitamente no documentados.
- Diagnóstico SSE ampliado y descarga de diagnóstico sin credenciales ni identidad.
- Detección de capacidades mediante el mapa; filtro de controles y protección de
  escrituras. ABH1007AE es referencia comprobada, sin bloquear otros firmwares.
- Conservación de los 53 identificadores de la 0.4.0; hasta 70 entidades en los
  mismos seis grupos, según capacidades del equipo.

## 0.4.0

- Telemetría local SSE mediante un coordinador independiente de los controles HTTP.
- Parser de eventos completos, recepción válida supervisada y reconexión automática.
- Watchdog configurable (30 s por defecto), diagnóstico de conexión y fechas opcionales.
- Migración de los sensores existentes disponibles en SSE, preservando sus unique_id.
- FV total usa ahora `pv` del EMS; FV1, FV2 y corriente de batería siguen por HTTP.
- Cuatro potencias direccionales: red importada/exportada y batería carga/descarga.
- Seis acumuladores de kWh con regla izquierda, persistencia y grupo Energía.
- No se integran huecos mayores de 5 s, datos inválidos ni tiempo de reinicios.
- Red desde el signo de `W` para incluir carga de batería y exportación desde batería.
- Vivienda desde `cons`, sin confundirlo con `total_cons`.
- Batería no disponible (`StatusBat = 7`): disponibilidad selectiva de sus medidas.
- Deslizantes BMS de 0–66 A y paso 1, conservando los registros y protecciones previos.
- Ocho idiomas ampliados, icono conservado e ID numérico predeterminado 1.
- README: usuario exclusivo con permisos de Instalador y firmware requerido ABH1007AE.
- Cinco escenarios sintéticos basados en los modos observados; regresión sobre Core y simulador HTTP/SSE.
- Guías de actualización, panel de Energía, limitaciones y publicación mediante HACS.
- Publicación inicial del código fuente; sin migración automática del historial MQTT.

## 0.3.0

- Dos límites de corriente BMS (HR86 y HR142) y permiso de calibración SOC (HR132 bit 0).
- Sensor FV total, con disponibilidad dependiente de las dos lecturas.
- Ocho idiomas completos para entidades, formularios, selectores y grupos.
- ID de inversor como campo numérico, valor inicial 1 y conversión explícita a entero.
- Confirmación inmediata de cada escritura, con relectura y comparación, sin espera del sondeo.
- Operaciones serializadas y registro del inversor principal antes de sus grupos.
- Coordinador con config_entry explícita para compatibilidad con Core reciente.
- Sensores no disponibles ante fallos de telemetría, conservando los controles válidos.
- Pruebas con Home Assistant Core 2026.3.0 y simulador HTTP; documentación de publicación HACS.


## 0.2.0

- Agrupación funcional mediante dispositivos subordinados, manteniendo los
  identificadores únicos de todas las entidades existentes.
- Cuatro selectores de modo para los programas de carga desde red 1/2 y
  descarga de batería 1/2.
- Ocho entidades de hora para el inicio y fin de los cuatro programas.
- Escritura conjunta de hora y minuto en una única petición HTTP.
- Lectura ampliada de HR58–65, HR100 y HR117–133.
- Icono y logotipo locales de Ingeteam para Home Assistant 2026.3 o posterior.
- Manifest actualizado a `0.2.0`.

## 0.1.0

- Primera versión funcional con telemetría y parámetros EMS seleccionados.
