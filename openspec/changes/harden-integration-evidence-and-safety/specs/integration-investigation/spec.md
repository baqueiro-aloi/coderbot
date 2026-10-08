## Purpose

Garantizar que decisiones de integración se basen en contratos investigados y versiones efectivas, no en inferencias del agente.

## ADDED Requirements

### Requirement: Investigación verificable antes del diseño
El bot SHALL identificar versiones declaradas, instaladas y previstas en despliegue, documentación oficial correspondiente con fecha y referencias, y contratos de APIs externas e internas afectadas antes de aprobar un diseño dependiente. SHALL registrar método, ruta, autenticación, aislamiento, payloads, errores y capacidades aplicables. Los contratos internos SHALL apoyarse en implementación/schema y consumidores reales.

#### Scenario: Documentación de otra versión
- **WHEN** la documentación consultada corresponde a una versión distinta del SDK efectivo
- **THEN** el bot identifica la discrepancia y obtiene evidencia correspondiente antes de acreditar compatibilidad

#### Scenario: Respuesta interna desconocida
- **WHEN** una decisión depende de la respuesta de una API interna
- **THEN** el bot inspecciona su implementación y valida el contrato en vez de deducirlo por nombre

### Requirement: Incertidumbres materiales explícitas
El bot SHALL distinguir hechos confirmados, supuestos pendientes y contradicciones; cada incertidumbre material SHALL indicar impacto y siguiente acción. SHALL pedir información indispensable sin exigir necesariamente una credencial. SHALL revalidar contratos afectados cuando cambien versiones, endpoint o alcance; las decisiones menores y reversibles permanecen autónomas.

#### Scenario: Fuentes contradictorias
- **WHEN** documentación, código y ejecución difieren sobre una capacidad requerida
- **THEN** el bot investiga la discrepancia y no selecciona silenciosamente la interpretación conveniente

#### Scenario: Cambio de SDK
- **WHEN** la versión objetivo cambia después de la investigación
- **THEN** el bot revalida evidencia dependiente antes de declarar compatibilidad
