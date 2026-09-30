## Purpose

Conservar resultados, contexto y efectos de ejecución verificables para reanudar tareas después de interrupciones sin perder trabajo válido ni repetir comprobaciones o entregas completadas.

## ADDED Requirements

### Requirement: Verification identity and reuse
Cada check SHALL registrar contenido relevante, comando, cwd, entorno/dependencias, tiempos, resultado y artifacts. Coderbot SHALL reutilizar resultados completos únicamente cuando esas entradas sigan válidas; cambios de entradas, cobertura desconocida o resultados interrumpidos SHALL invalidar la reutilización.

#### Scenario: Cambio documental
- **WHEN** solo cambian documentos no utilizados por un check de aplicación válido
- **THEN** ese check conserva su validez y no se repite únicamente por cambiar HEAD

#### Scenario: Edición sobre archivo ya modificado
- **WHEN** cambian las entradas de un check aunque git status mantenga los mismos nombres de archivos
- **THEN** el check queda invalidado por contenido y se vuelve a ejecutar

#### Scenario: Entorno distinto
- **WHEN** cambian lockfiles, runtime, configuración relevante o variables declaradas del check
- **THEN** el resultado anterior no se reutiliza como evidencia válida

### Requirement: Durable phase outcomes and recovery
Coderbot SHALL persistir resultados del agente, checks, hallazgos, tareas completadas y siguiente acción antes de efectos externos. Una interrupción SHALL recuperar el checkout real y continuar únicamente trabajo pendiente, preservando evidencia RED/GREEN válida. Los snapshots HOLD SHALL conservar capacidades y contexto de ejecución; su restauración SHALL ser durable antes de retirar el snapshot.

#### Scenario: Caída antes de notificación
- **WHEN** un turno termina y el servicio cae antes de enviar el mensaje
- **THEN** recupera el resultado persistido y entrega el mensaje sin volver a ejecutar el turno

#### Scenario: Recuperación de implementación parcial
- **WHEN** KICK interrumpe trabajo con checks y evidencia TDD persistidos
- **THEN** se conserva lo válido y se completa lo pendiente sin eliminar código únicamente por pertenecer al intento anterior

#### Scenario: CONTINUE después de cambio de capacidades
- **WHEN** una tarea pausada se reanuda y el contexto de otras tareas tiene distintas capacidades
- **THEN** se restauran las capacidades de la tarea pausada y se persiste esa restauración antes de eliminar su snapshot

### Requirement: Recoverable artifact delivery
Coderbot SHALL registrar por separado grabación, conversión, subida y notificación con identidad estable por tarea, snapshot y artifact. Un retry SHALL reconciliar efectos externos ya efectuados cuando el canal lo permita y SHALL repetir únicamente pasos incompletos, sin volver a ejecutar tests por fallos de conversión o entrega.

#### Scenario: Falla la subida
- **WHEN** existe evidencia válida pero falla su subida
- **THEN** el retry reutiliza el artifact y no vuelve a arrancar el harness

#### Scenario: Caída tras creación de PR o mensaje
- **WHEN** un efecto externo se completa pero se pierde su confirmación local
- **THEN** Coderbot intenta reconciliarlo mediante identidad estable antes de producir un duplicado y registra cualquier limitación del canal
