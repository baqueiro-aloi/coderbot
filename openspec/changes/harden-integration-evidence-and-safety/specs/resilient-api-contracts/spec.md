## Purpose

Evitar falsos estados vacíos, duplicaciones y decisiones de ownership basadas en payloads incompletos o respuestas mutantes no reconciliadas.

## ADDED Requirements

### Requirement: Validación y paginación completas
Clientes SHALL validar estructura mínima/tipos y distinguir colección vacía de payload inválido. SHALL paginar recursos y comentarios necesarios, rechazar cursores repetidos/ausentes cuando se anuncian páginas adicionales y limitar ciclos. Respuestas perdidas o snapshots antiguos no SHALL demostrar ownership o ausencia de review.

#### Scenario: Payload sin items
- **WHEN** respuesta de backlog carece de colección requerida
- **THEN** se informa contrato inválido en lugar de backlog vacío

#### Scenario: Más de cien comentarios
- **WHEN** thread tiene más comentarios que primera página
- **THEN** decisiones usan todos comentarios pertinentes o declaran lectura incompleta

### Requirement: Retry según causa y efecto
Clientes SHALL categorizar errores de auth, permisos, rate limit, transporte, schema y conflictos reales. No SHALL clasificar todo HTTP 400 como conflicto de revisión. Operaciones mutantes no idempotentes SHALL reconciliar efecto remoto antes de repetir tras resultado ambiguo; si no puede determinarse, SHALL exponer incertidumbre sin duplicar operación.

#### Scenario: Issue creado pero respuesta perdida
- **WHEN** servicio aplica creación y respuesta no llega
- **THEN** bot reconcilia creación antes de considerar nuevo POST

#### Scenario: Request Docs inválido
- **WHEN** API rechaza request con HTTP 400 no relacionado con revisión
- **THEN** bot diagnostica request inválido y no afirma que documento cambió
