# Hoja de ruta

Esta hoja distingue trabajo acordado y capacidades disponibles. No autoriza por sí sola cambios, publicaciones o fusiones. La referencia publicada al iniciar la reorganización es v0.5.3.

## Prioridad inmediata — Base 0.6.0

1. Extraer el comportamiento del **INGECON SUN STORAGE 1Play 6TL M — 2 MPPT** a un perfil propio, conservando la compatibilidad documentada con ABH1007AE.
2. Definir un contrato de perfiles y plataformas genéricas. Una extensión normal añade su directorio, registro explícito, pruebas, traducciones y documentación; los cambios comunes se revisan por separado.
3. Comparar contra v0.5.3 y conservar entidades, ajustes, automatizaciones, energía y estadísticas.
4. Completar la prueba física del TL M y la validación de la revisión candidata antes de publicar 0.6.0 estable.
5. Entregar la [guía de aportación de perfiles](PROFILES.md).

El [PR #8](https://github.com/solideus/Ingeteam-iss-homeassistant/pull/8) se ha cerrado sin fusionar y se conserva como referencia. El [issue #7](https://github.com/solideus/Ingeteam-iss-homeassistant/issues/7) continúa el seguimiento del 1Play anterior.

## Después — Perfil 1Play TL sin M

Preparar un PR separado para **INGECON SUN STORAGE 1Play TL — 1 MPPT, sin M**, con evidencia aportada por un colaborador para un 6TL, tarjeta AAX0077, portal AAX1055DC y mapa ABH1002AL. La versión instalada del controlador no queda demostrada únicamente por la compatibilidad declarada en el mapa.

Empezar con monitorización experimental. Antes de aceptar energía, contrastar series simultáneas en producción solar, descarga nocturna, carga desde red y exportación, marcando huecos y reinicios. Documentar la frontera de consumo según el cableado. Los controles requieren correspondencias propias, validación antes de HTTP, pruebas y evidencia física con su alcance explícito.

No se asigna todavía un número de versión ni una fecha a ese soporte. La contribución no debe modificar el perfil TL M ni trasladar a él las reglas del equipo anterior.

## Mantenimiento independiente

- Sustituir el uso obsoleto de `via_device` por la API correspondiente de `via_device_id`, conservando Core 2026.3.0 y verificando los enlaces y las identidades de los grupos.
- Resolver regresiones demostradas y mantener la documentación vigente separada de los resultados históricos.

## Objetivos posteriores, sin versión asignada

- Prioridad media: investigar múltiples inversores por tarjeta (identidad, agregado SSE, nodos y energía), auditoría de escrituras y blueprints configurables.
- Menor prioridad: coherencia energética, demanda máxima, ratios de autoconsumo/autonomía y métricas avanzadas de batería solo cuando sus datos y significados estén documentados.
- Madurez 1.0: estabilidad demostrada, documentación y mantenimiento. La posible propuesta a Home Assistant Core exige revisar sus requisitos y un proceso independiente; no se obtiene automáticamente al alcanzar 1.0.
