# 0.6.0 — Base de perfiles de inversor

Estado: **en desarrollo, sin publicación estable**. La comprobación física de esta reorganización en el inversor de referencia sigue pendiente. Los resultados históricos de 0.5.3 no se presentan como validación física de 0.6.0.

## Objetivo y alcance

La integración mantiene un único perfil de producción: **INGECON SUN STORAGE 1Play TL M — 2 MPPT**, identificador `tl_m`, probado históricamente en un **6TL M** con firmware de portal **ABH1007AE** (tarjeta ABH0101, API 102). ABH1006AC es una referencia interna del mapa y no sustituye esa referencia de portal.

Esta versión separa las definiciones de registros, entidades, telemetría y estados del TL M de la infraestructura compartida. El objetivo es permitir que una contribución futura añada un modelo en su propio directorio sin editar el perfil del 6TL M. No ofrece aislamiento absoluto: cambios en comunicaciones, plataformas o energía siguen necesitando regresiones de los perfiles existentes.

El **1Play TL sin M — 1 MPPT** no se incorpora en esta versión. El [PR #8](https://github.com/solideus/Ingeteam-iss-homeassistant/pull/8) se ha cerrado sin fusionar para separar la reorganización de la ampliación de compatibilidad; se conserva como investigación. Su soporte se abordará en un PR posterior, con el colaborador como tester y siguiendo [PROFILES.md](PROFILES.md).

## Compatibilidad de instalaciones existentes

Las entradas antiguas sin un identificador de perfil siguen utilizando `tl_m`. No hay que borrar ni recrear la integración. Se conservan dominio, identidad de tarjeta, unique IDs, grupos, nombres personalizados, opciones y clave del almacén de energía.

El alta solo ofrece ese perfil. Reconfigurar conserva el perfil existente y no introduce un selector de cambio de modelo. La ausencia de mapa conserva el fallback histórico del TL M; un mapa identificado como TL sin M se rechaza antes del primer sondeo.

No se reinician los acumulados ni se importan históricos. Los algoritmos de energía y calendario, el cierre a HH:59:55, la regla izquierda, el máximo de cinco segundos y la publicación ordinaria de unos treinta segundos mantienen su contrato. No se hacen cambios en dashboards, YAML, Recorder ni SQL.

Un identificador de perfil desconocido no debe resolver silenciosamente al TL M ni importar un módulo arbitrario. Una incompatibilidad demostrada con otro mapa no debe habilitar controles del 6TL M. La verificación usa capacidades; no se bloquea un firmware únicamente por ordenar o comparar una cadena de versión.

## Validación requerida

La base de comparación es el contenido publicado de **v0.5.3**, commit `c3b95dfbb7f7e1661f232c35ff719d7934ecc38d`. La extracción debe mantener resultados equivalentes para capturas, definición de entidades, payloads de lectura/escritura y secuencias temporales relevantes.

- Ejecutar Ruff, pruebas en ambas versiones Core de la matriz, compilación y comprobación de paquete, además de HACS/Hassfest.
- Comparar entidades, unidades, rangos, selectores y disponibilidad con la referencia.
- Verificar escrituras, relecturas, bits compartidos y ausencia de escrituras durante instalación/lectura.
- Comprobar energía, cierre horario y asignación estadística con Recorder real; día/mes, DST Madrid, reinicio y restauración.
- Confirmar físicamente el comportamiento ordinario del TL M, sus controles conocidos, horarios y conservación al recargar/reiniciar antes de la publicación estable.

Las pruebas automatizadas no demuestran estabilidad física prolongada ni precisión fiscal. Validación local de esta base: **278 pruebas superadas** tanto en Core **2026.3.0** como en **2026.9.3**, con Python **3.14.9**. Ruff, formato de los módulos y pruebas nuevos, compilación y construcción/comprobación del ZIP correctos. La suite incluye la referencia congelada de v0.5.3 (definiciones, peticiones HTTP, capturas, estados y secuencias energéticas), preservación de personalizaciones/acumulados y perfiles sintéticos de extensión que no se registran en producción. La CI HACS/Hassfest se comprobará en el PR; la validación física sigue pendiente.

## Actualización y reversión

Cuando exista una versión publicada, actualizar desde HACS conservando la entrada y tras una copia de seguridad completa. Para probar una rama, identificar el commit y tratarla como experimental.

Si hay que revertir una prueba, restaurar una copia coherente de código y datos cuando corresponda. No borrar entidades ni editar el almacén energético para cambiar de versión. Las guías históricas de sustitución de carpetas de 0.3/0.4 no son un procedimiento universal de reversión desde versiones posteriores.

## Fuera de esta reorganización

No se amplían entidades ni funciones del TL M, no se habilita multiinversor y no se cambia la elección del periodo horario. La migración del parámetro obsoleto `via_device` permanece como corrección independiente pendiente; no debe mezclarse con la comparación de equivalencia de perfiles.
