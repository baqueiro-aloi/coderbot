## MODIFIED Requirements

### Requirement: Conditional E2E gate
Codebot SHALL ejecutar una suite E2E completa final después de implementación y revisión interna cuando se detectó harness para la tarea. SHALL exigir ausencia de regresiones frente al baseline fijado al SHA base, reutilizar resultados válidos del mismo snapshot y aplicar la misma política a todos los gates. Los fallos idénticos confirmados en baseline SHALL reportarse como preexistentes; regresiones, errores de infraestructura o comparaciones ambiguas SHALL bloquear sin declararse aprobados. Sin harness, SHALL mantener los demás checks y revisión aplicables y continuar hacia el PR sin invocar E2E ni tratar su ausencia como fallo.

#### Scenario: E2E harness present
- **WHEN** implementación y revisión interna terminan y se detectó harness
- **THEN** se ejecuta la suite final una vez por snapshot válido y se reparan únicamente regresiones atribuibles al cambio

#### Scenario: E2E harness absent
- **WHEN** no se detectó harness
- **THEN** se completan checks y revisión aplicables y se continúa hacia el PR sin ejecución E2E ni mensaje de fallo por ausencia de harness

#### Scenario: Fallos preexistentes
- **WHEN** la suite final falla con los mismos tests y firmas de error confirmados sobre el SHA base bajo entorno comparable
- **THEN** el gate permite continuar con esos fallos explícitamente reportados y no inicia un ciclo de reparación por ellos

#### Scenario: Baseline ambiguo
- **WHEN** el baseline no puede ejecutarse o el entorno no permite una comparación fiable
- **THEN** el gate registra resultado indeterminado o fallo de infraestructura y no afirma que el check pasó

### Requirement: Kind-aware evidence collection
Al entregar un PR, codebot SHALL compartir evidencia apropiada al harness: vídeo Playwright o reporte Newman. SHALL utilizar artifacts de una ejecución válida vinculada al contenido entregado, con procedencia y resultado registrados, mediante manifest o detección compatible de archivos realmente nuevos/modificados. SHALL reutilizar evidencia fresca de checks finales; si falta, SHALL realizar como máximo una grabación focalizada por snapshot y parámetros. SHALL NOT entregar artifacts viejos, ajenos o fallidos como prueba aprobada. La ausencia o fallo de evidencia SHALL reportarse sin bloquear la entrega del PR.

#### Scenario: Playwright evidence
- **WHEN** el check final produce un vídeo demostrativo Playwright válido
- **THEN** codebot lo reutiliza, convierte si corresponde y comparte sin repetir el harness

#### Scenario: Newman evidence
- **WHEN** la ejecución relevante produce un reporte Newman válido
- **THEN** codebot comparte ese reporte en lugar de un vídeo

#### Scenario: Directorio externo de artifacts
- **WHEN** el harness publica resultados en una ruta externa declarada por manifest
- **THEN** codebot recoge artifacts de esa ejecución sin asumir e2e/test-results

#### Scenario: Evidencia ausente o fallida
- **WHEN** solo existen clips viejos o de ejecución fallida o la conversión agota su presupuesto
- **THEN** codebot informa evidencia no disponible y no reejecuta la suite completa ni presenta esos clips como verificación aprobada

## ADDED Requirements

### Requirement: Final snapshot verification
Todos los caminos que modifiquen contenido después de revisión, incluido feedback de PR, threads y conflictos, SHALL invalidar checks afectados y comprobar el snapshot entregado mediante la misma política. La revisión SHALL cubrir cambios relevantes, y una suite final válida SHALL conservarse si sus entradas no cambiaron.

#### Scenario: Feedback después de abrir PR
- **WHEN** se aplican y publican correcciones de feedback
- **THEN** el handoff identifica checks y revisión válidos para el contenido nuevo y no reutiliza un gate de contenido anterior sin invalidación

### Requirement: Bounded review wait
La espera de revisión externa SHALL terminar dentro de su deadline incluso si falla la consulta de threads. Tras conflictos, SHALL esperar review únicamente si se detectó workflow aplicable. Las continuaciones después de preguntas SHALL conservar respuestas y resoluciones de threads para no reprocesar trabajo completado.

#### Scenario: Consulta de threads persistentemente fallida
- **WHEN** las consultas fallan hasta agotar el presupuesto de review
- **THEN** Coderbot registra el fallo y toma la continuación acotada sin esperar indefinidamente

#### Scenario: Conflicto sin workflow
- **WHEN** se publica una resolución de conflicto y no existe workflow de review
- **THEN** se continúa a la entrega sin esperar un check inexistente

#### Scenario: Pregunta durante resolución de threads
- **WHEN** el agente termina correcciones tras recibir una respuesta del usuario
- **THEN** conserva sus líneas de resolución durante push y responde/resuelve los threads correspondientes
