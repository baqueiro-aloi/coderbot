## Purpose

Hacer atribuible el tiempo de ejecución completo de Coderbot mediante eventos y métricas observables, separando trabajo útil, espera humana, bloqueos técnicos y repeticiones.

## ADDED Requirements

### Requirement: Attributable execution timeline
Coderbot SHALL registrar una línea de tiempo durable por tarea, fase, intento y operación con inicio, fin, duración, causa de repetición y resultado. SHALL separar espera humana, proveedor, herramientas, checks, permisos, cleanup y entrega, evitar doble conteo de operaciones concurrentes y declarar intervalos no atribuibles. La telemetría SHALL excluir valores de secretos y razonamiento privado y no impedir el trabajo por un fallo de registro.

#### Scenario: Tests concurrentes
- **WHEN** dos suites se solapan
- **THEN** el reporte distingue duración acumulada de tiempo calendario y no suma ambas como tiempo exclusivo

#### Scenario: Reinicio sin eventos completos
- **WHEN** un servicio reinicia con operaciones incompletas
- **THEN** el reporte las identifica como interrumpidas y no las confunde con checks terminados ni asigna una causa no observada

### Requirement: Performance acceptance benchmark
Coderbot SHALL disponer de un benchmark repetible con latencias controladas y fallos inyectados que mida fin de tarea, número de checks, recuperaciones, contexto y entrega. Los objetivos iniciales SHALL incluir cero esperas de autorización, detección de bloqueos locales en menos de un minuto con el perfil de benchmark, una suite final por snapshot relevante y finalización normal sin KICK.

#### Scenario: Comparación reproducible
- **WHEN** se ejecuta el mismo escenario sobre baseline y versión nueva
- **THEN** se produce una comparación de tiempo improductivo y repetición con las mismas latencias, separando esperas humanas
