## MODIFIED Requirements

### Requirement: Conditional E2E gate
Codebot SHALL ejecutar E2E cuando existe harness y exigir ejecución relevante exitosa o excepción explícita aplicable para avanzar a PR. Sin harness SHALL omitir ese gate sin acreditar E2E ni omitir otras validaciones aplicables. Cero tests o todos skipped no SHALL contar como pass. Excepciones SHALL identificar checks/capacidades exactos, nunca eliminar todos checks por prefijo de nombre.

#### Scenario: E2E harness present
- **WHEN** implementación termina y existe harness
- **THEN** bot ejecuta E2E y avanza únicamente con resultados aplicables exitosos o excepción explícita del usuario

#### Scenario: E2E harness absent
- **WHEN** no existe harness
- **THEN** bot omite E2E, conserva otros gates y declara E2E no realizado por ausencia de harness

#### Scenario: Suite omitida
- **WHEN** runner devuelve exit cero pero ningún test relevante ejecutado
- **THEN** bot registra skipped o not_run y no acredita pass

#### Scenario: Excepción sin key
- **WHEN** usuario autoriza omitir pruebas upstream concretas
- **THEN** bot continúa con alternativas y conserva todos checks fuera de excepción

### Requirement: Kind-aware evidence collection
Al entregar PR, codebot SHALL recoger evidencia adecuada al harness: video validado Playwright o reporte validado Newman. Evidencia SHALL corresponder a ejecución y contenido verificados, con resultado y selección trazables. Reporte nuevo no vacío tras fallo no SHALL presentarse como evidencia exitosa. Si no existe evidencia aprobada SHALL informar ausencia/pendientes y entregar diagnósticos etiquetados, sin fabricar prueba ni bloquear por ausencia de un attachment opcional.

#### Scenario: Playwright evidence
- **WHEN** se genera video para feature
- **THEN** se entrega únicamente como evidencia exitosa si ejecución, selección y contenido están verificados

#### Scenario: Newman evidence
- **WHEN** se genera reporte Newman
- **THEN** resultado estructurado y ejecución verifican si evidencia es exitosa o diagnóstico de fallo

#### Scenario: Newman failed run
- **WHEN** ejecución falla pero produce HTML nuevo
- **THEN** HTML se etiqueta como diagnóstico y no acredita validación
