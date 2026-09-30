## ADDED Requirements

### Requirement: Observable operational status
STATUS y check-ins SHALL indicar fase, operación actual observable, tiempo transcurrido, último progreso, deadline y motivo de espera conocido, incluyendo tests del orquestador y subagentes. SHALL distinguir proceso vivo de progreso útil, informar bloqueos detectados y evitar atribuir silencios a pensamiento o tests sin evidencia. SHALL responder sin iniciar un turno de programación ni alterar el turno activo.

#### Scenario: Subagente bloqueado por runtime
- **WHEN** se detecta una solicitud de permiso residual o una operación hija bloqueada
- **THEN** STATUS identifica la condición y la recuperación automática en lugar de afirmar que el agente está pensando

#### Scenario: E2E ejecutado por Python
- **WHEN** el orquestador ejecuta la suite final y el usuario pide STATUS
- **THEN** recibe suite actual, duración y presupuesto observables sin interrumpirla

### Requirement: Reusable localized delivery
Las notificaciones FSM estáticas SHALL utilizar plantillas del idioma de la tarea y el contenido localizado dinámico SHALL reutilizarse para conversación e historial. Una falla de entrega SHALL reanudar desde el mensaje y artifacts persistidos sin repetir implementación, tests o revisión; el handoff SHALL señalar checks omitidos, preexistentes e indeterminados correctamente.

#### Scenario: Notificación estática en español
- **WHEN** cambia la fase de una tarea en español
- **THEN** se envía la plantilla correspondiente sin ejecutar una traducción LLM

#### Scenario: Retry de envío
- **WHEN** la entrega falla después de persistir resultados y artifacts
- **THEN** se reintenta la entrega reutilizando esos resultados y se conservan las decisiones de aprobación pendientes
