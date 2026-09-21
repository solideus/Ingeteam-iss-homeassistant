# Registro de cambios

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
