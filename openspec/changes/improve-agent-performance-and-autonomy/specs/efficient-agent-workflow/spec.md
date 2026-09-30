## Purpose

Mantener calidad de implementación con trabajo proporcional, contexto acotado, delegación controlada y preparación reutilizable de herramientas y dependencias.

## ADDED Requirements

### Requirement: Focused implementation and independent review
Coderbot SHALL guiar implementación y reparaciones mediante checks focalizados y evidencia de comportamiento significativo. SHALL obtener revisión interna independiente del contenido afectado y re-review de hallazgos corregidos, evitando repetir revisión completa por efectos administrativos o cambios documentales no relevantes. SHALL conservar las aprobaciones funcionales existentes.

#### Scenario: Corrección de hallazgo
- **WHEN** se corrige un hallazgo importante
- **THEN** se ejecutan checks afectados y una re-review de la corrección antes de la suite final

### Requirement: Bounded context and delegation
Coderbot SHALL transmitir a cada fase requisitos aprobados, decisiones, diff, checkpoints, checks y siguiente acción en un handoff acotado. SHALL rotar o compactar sesiones al agotar su presupuesto de contexto y limitar delegación concurrente según independencia y recursos exclusivos.

#### Scenario: Inicio de revisión
- **WHEN** comienza la revisión interna
- **THEN** el revisor recibe contexto fresco relevante sin necesitar toda la conversación histórica de implementación

#### Scenario: Suites con puertos compartidos
- **WHEN** dos trabajos solicitan recursos exclusivos coincidentes
- **THEN** se serializan o se aíslan antes de ejecutarse concurrentemente

### Requirement: Reusable dependency preparation
Coderbot SHALL preparar herramientas gestionadas y dependencias una vez por fingerprint de entradas y verificar su disponibilidad antes de reutilizarlas. SHALL proporcionar contratos de harness compatibles con agrupación de specs/proveedor y artifacts explícitos; los harnesses existentes SHALL conservar una ruta compatible sin cachés injustificadas.

#### Scenario: Segunda ejecución sin cambios
- **WHEN** el fingerprint y las dependencias verificadas permanecen iguales
- **THEN** no se repiten instalaciones de plugins, browsers o builds gestionados sin necesidad

#### Scenario: Cambio de lockfile
- **WHEN** cambian las entradas de preparación
- **THEN** se invalida el estado preparado y se actualizan dependencias antes de ejecutar checks

### Requirement: Lightweight administrative operations
Mensajes estáticos y comandos explícitos SHALL utilizar rutas deterministas. Las utilities que requieran LLM SHALL ejecutarse sin herramientas operativas, con modelo/esfuerzo y presupuesto propios, conservando texto ya localizado para conversación e historial.

#### Scenario: STATUS o KICK explícito
- **WHEN** llega un comando válido y explícito
- **THEN** su ejecución no requiere iniciar una sesión de programación ni clasificarlo mediante LLM

#### Scenario: Traducción de mensaje dinámico
- **WHEN** es necesaria una traducción de contenido dinámico
- **THEN** se realiza mediante una utility acotada y se reutiliza su resultado para los destinos del mensaje
