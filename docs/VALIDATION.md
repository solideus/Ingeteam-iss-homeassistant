# Validación y prueba de instalación — 0.4.0

## Comprobación automatizada

La prueba no contacta con el inversor físico. Levanta un simulador HTTP/SSE
en localhost y carga el componente en Home Assistant Core real.

| Entorno | Resultado |
|---|---|
| Python 3.14.7 + Home Assistant Core 2026.3.0 | 65 pruebas superadas |
| Python 3.14.7 + Home Assistant Core 2026.9.3 | 65 pruebas superadas |
| Ruff: análisis y formato | Correcto |
| Compilación de los módulos Python | Correcta |

Queda un aviso de obsolescencia de la clase HTTP interna de Home Assistant.
Se han eliminado los avisos originados por el uso anterior de BasicAuth en el
cliente del componente.

Cobertura:

- Registro de 53 entidades en seis grupos/dispositivos.
- Conservación de los 40 identificadores de 0.3.0.
- Deslizantes BMS 0–66 A, paso 1; rechazo de fracciones y límites inválidos.
- Escrituras y relecturas, bits compartidos, horarios, cambios concurrentes.
- Ausencia de escrituras durante instalación, sondeo y reproducción de escenarios.
- Ocho traducciones cargadas mediante Home Assistant.
- Eventos fragmentados, UTF-8, BOM, varios finales de línea, comentarios,
  JSON inválido, tamaños excesivos y selección inequívoca de Phase 4.
- Las cinco capturas reales de operación aportadas por el usuario.
- Cierre SSE, reconexión, errores HTTP/autenticación SSE y silencio con
  heartbeats que no cuentan como datos.
- SSE y HTTP con disponibilidad independiente; el SSE no reinicia el sondeo HTTP.
- Campos ausentes, batería desconectada y ceros válidos.
- Integración de potencia constante durante una hora para cada escenario.
- Regla izquierda, cambio de signo, huecos, datos inválidos y reinicios.
- Precisión interna, guardado no pospuesto por cada evento y carga de totales
  al recargar la entrada.
- Publicación de energía limitada a 30 s sin reducir las muestras de cálculo.
- Cancelación de tareas y cierre de socket al descargar la integración.

Los tests fijan las relaciones que demuestran las capturas; no asumen igualdad
entre todos los campos de potencia del EMS.

## Antes de actualizar

1. Haz una copia de seguridad de Home Assistant.
2. Guarda la carpeta de 0.3.0 fuera de `custom_components` para evitar que
   Home Assistant intente cargar una segunda copia.
3. Anota qué sensores MQTT/Integral tienes en el panel de Energía. Conserva
   sus nombres, totales e historial para la comparación.
4. Confirma firmware de referencia ABH1007AE y permisos de Instalador para
   el usuario específico de Home Assistant.
5. No cambies los límites eléctricos de la instalación solo para probar
   la integración. Utiliza estados operativos normales y seguros.

## Actualización

Sustituye `/config/custom_components/ingeteam_iss` por la carpeta del mismo
nombre incluida en el ZIP y reinicia Home Assistant. Mantén la entrada ya
configurada: no es necesario borrar la integración.

Deben conservarse las entidades anteriores, agrupaciones e icono. Aparecen
las cuatro potencias direccionales, los seis contadores y la conectividad SSE.
Los dos sensores de fecha se pueden habilitar de forma opcional.

## Lista de pruebas en tu instalación

| Prueba | Resultado esperado |
|---|---|
| Arranque | SSE conectado tras recibir el primer evento válido; sin cambio de ajustes |
| BMS | Ambos controles se muestran como deslizantes de 0 a 66, paso 1 |
| Configuración | Un cambio pequeño dentro de un límite previamente seguro se refleja en HA y portal |
| Horarios | Se conservan valores, modos y correspondencia con el reloj del inversor |
| FV | Total sigue `pv` del SSE; strings individuales siguen por HTTP |
| Red | Importación positiva y exportación negativa en potencia neta; fuentes separadas no negativas |
| Carga desde red | Importación incluye batería; consumo de casa usa `cons` |
| Descarga a red | Energía exportada incluye la parte procedente de la batería |
| Autoconsumo | Descarga de batería y consumo de vivienda se representan sin sumar duplicados |
| Sin FV | Se muestra 0 W válido, no «No disponible» |
| Batería ausente, si ocurre normalmente | Solo sus medidas quedan no disponibles; red/FV/vivienda continúan |
| Recarga de integración | Totales de energía conservados; no se suma el tiempo intermedio |
| Reinicio normal de HA | Mismos identificadores y totales; reconexión sin intervención |
| Pérdida de SSE | Conectividad apagada, potencias SSE no disponibles, energías detenidas |
| Recuperación | Vuelven los datos y el cálculo sin salto de energía durante el hueco |
| Idioma | Los nombres nuevos y formularios tienen traducción; nombres personalizados intactos |

No hace falta cortar alimentación del inversor, la batería o la vivienda.
Las interrupciones ya se simulan en las pruebas automatizadas. Si haces una
prueba de red, limita el bloqueo al tráfico entre HA y la API local y retíralo
después; no alteres los sistemas de protección del inversor.

## Comparación de energía

Compara **incrementos durante el mismo intervalo**, no el total absoluto
nuevo con tus acumuladores históricos. Los contadores nuevos empiezan en cero,
se publican cada 30 s mientras hay datos y conservan su total al reiniciar.

En el sistema anterior, la energía de red utilizaba `_grid_cons` y
`_pv_grid`. En esta versión procede de `W`. Por ello, no se espera que los
totales coincidan cuando se carga desde red o se exporta desde batería:
el sistema nuevo contabiliza rutas que esos dos campos aislados no cubren.

Deja pasar un intervalo representativo en los modos que utilices habitualmente.
Comprueba que no hay aumentos anómalos después de una interrupción y revisa
la comparación con el portal/contador. No se compensa automáticamente ninguna
discrepancia ni se recuperan intervalos sin muestras fiables.

En el panel de Energía selecciona una única fuente por magnitud: FV, red entrada,
red salida y batería entrada/salida. Mantener MQTT en paralelo para comparar
no duplica energía por sí mismo; lo que debe evitarse es seleccionar ambas
fuentes equivalentes en el panel.

## Si hay un problema

Conserva la 0.3.0 para poder restaurar su carpeta y reiniciar. No borres la
entrada de configuración ni edites los datos internos de almacenamiento.
Las nuevas entidades dejarán de actualizar hasta reinstalar 0.4.0.

Para informar, indica versión de HA, modelo, firmware, escenario y hora de la
incidencia. Adjunta estados relevantes y un fragmento SSE sin datos sensibles.
No compartas contraseñas, cabeceras Authorization, HAR sin anonimizar, ni
capturas que expongan datos personales.

## Límites de la validación

Que los tests pasen no demuestra estabilidad prolongada sobre el inversor,
precisión fiscal de las energías ni ejecución física de una calibración BMS.
Tampoco demuestra compatibilidad con otros modelos/mapas.

La publicación en GitHub, validación externa HACS/Hassfest y prueba de
instalación desde HACS siguen pendientes. No se ha creado ni publicado un
repositorio en esta entrega.
