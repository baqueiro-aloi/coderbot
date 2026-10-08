## Purpose

Vincular requisitos y afirmaciones de validación con ejecuciones y revisiones trazables, reutilizando únicamente evidencia vigente para contenido y entorno efectivos.

## ADDED Requirements

### Requirement: Evidencia estructurada y cobertura
Cada validación SHALL distinguir tipo unitario, contrato, integración local, upstream real o postdespliegue, y resultado pass, fail, blocked, skipped o not_run. SHALL registrar comando/ejecución, versiones, destino seguro, fecha, snapshot, identidad de configuración y requisitos/scenarios cubiertos. El controlador SHALL exigir cobertura aplicable mediante evidencia real o excepciones explícitas, no solo checkboxes o texto del agente.

#### Scenario: Requisito no cubierto
- **WHEN** suite pasa pero un requisito aprobado carece de evidencia y excepción
- **THEN** no se acredita verificación completa de ese requisito

### Requirement: Contratos y revisión independientes
Fixtures SHALL derivarse de contratos investigados y rechazar rutas/auth/parámetros inválidos. Pruebas SHALL comprobar request upstream y capacidades distintas, incluyendo concurrencia cuando aplique. Una revisión independiente SHALL tener recibo identificable, contenido revisado, findings y resoluciones; declaración del implementador no basta. Auth/listado no SHALL acreditar inferencia/tools/streaming.

#### Scenario: Doble autenticación
- **WHEN** una request contiene autenticación incompatible con contrato
- **THEN** fixture la rechaza y regresión falla antes de aprobar integración

#### Scenario: Revisión declarada sin recibo
- **WHEN** implementador reporta cero findings sin revisión independiente trazable
- **THEN** el controlador no acredita revisión realizada

### Requirement: Reutilización ligada a entorno y vigencia
Cache/checkpoints SHALL considerar configuración efectiva, versiones instaladas y cambios de acceso externo sin almacenar valores secretos. Evidencia remota SHALL caducar y revalidarse antes de promoción según política. Resolver credencial/permiso o cambiar endpoint SHALL invalidar diagnóstico dependiente; recuperación SHALL conservar excepciones y trabajo válidos.

#### Scenario: Cambio solo en env
- **WHEN** key o endpoint efectivo cambia sin modificación de código
- **THEN** checks dependientes no reutilizan resultados incompatibles

#### Scenario: Evidencia remota expirada
- **WHEN** evidencia supera vigencia permitida
- **THEN** se solicita ejecución actual o se aplica excepción autorizada, sin presentarla como actual

### Requirement: Migración conservadora
Registros históricos sin procedencia SHALL permanecer disponibles pero no acreditar validación verificable. Migración SHALL preservar decisiones explícitas demostrables sin ampliar excepciones ambiguas, y conservar compatibilidad de lectura y recuperación para ambos canales/runners.

#### Scenario: Registro antiguo
- **WHEN** una tarea recuperada contiene solo una afirmación textual de pass
- **THEN** se conserva historial y se obtiene evidencia actual sin fabricar recibos históricos
