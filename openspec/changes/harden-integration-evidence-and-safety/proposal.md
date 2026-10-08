## Why

Las incidencias de `ISSUES.md` y la auditoría del bot muestran contratos asumidos, pruebas sintéticas confundidas con validación real, excepciones imprecisas y exposición potencial de secretos o trabajo ajeno. Debemos convertir la investigación, la evidencia y las decisiones del usuario en contratos verificables del controlador, sin bloquear indefinidamente cuando el usuario decide no proporcionar credenciales.

## What Changes

- Exigir investigación de versiones efectivas, documentación oficial, implementación interna y supuestos materiales antes de aprobar un diseño dependiente.
- Solicitar credenciales y presupuesto temprano, permitiendo omisión explícita, precisa y durable de pruebas dependientes; continuar con alternativas locales sin afirmar validación remota.
- Proteger recepción de enlaces de un solo uso, ejecución, persistencia, logs, attachments, transcripts, Git y scripts de boot; restringir descargas autenticadas.
- Añadir contratos versionados de evidencia, cobertura de requisitos, revisión independiente trazable, resultados de pruebas realmente ejecutadas y excepciones separadas de los resultados.
- Invalidar cache/checkpoints por configuración efectiva, dependencias, acceso externo y caducidad de evidencia remota.
- Preservar trabajo ambiguo mediante procedencia, backup y aislamiento; eliminar limpieza destructiva basada únicamente en la fase y staging indiscriminado en HOLD.
- Validar payloads/paginación y reconciliar operaciones API mutantes antes de reintentarlas.
- Ligar aprobación/merge al SHA remoto y distinguir liveness, readiness, despliegue y smoke funcional.
- Migrar datos existentes conservadoramente, con regresiones y rollout gradual para email/Slack y Claude/OpenCode.
- **BREAKING**: cero tests, skips sin autorización, evidencia histórica sin procedencia y contratos textuales sin recibos dejan de acreditar verificación. Se mantiene lectura compatible de registros existentes, sin inventar resultados.

## Capabilities

### New Capabilities

- `integration-investigation`: contratos investigados, documentación por versión y registro de incertidumbres.
- `scoped-validation-overrides`: decisiones explícitas de omitir checks dependientes y continuar sin credenciales.
- `secret-safe-execution`: recepción y ciclo de vida de secretos, descargas seguras y sanitización transversal.
- `verification-provenance`: evidencia estructurada, cobertura, revisión y cache/checkpoints válidos.
- `work-preservation`: atribución de cambios, aislamiento, recuperación y HOLD seguros.
- `resilient-api-contracts`: schemas, paginación, ownership remoto e idempotencia de clientes.
- `release-verification`: aprobación por SHA remoto y validación operacional de despliegues.

### Modified Capabilities

- `quality-gates`: excepciones específicas, ejecución relevante, cobertura y evidencia E2E validada.

## Impact

Bot Python (`src/`), runners y plugin JavaScript (`agent-plugin/`), contratos del target, tests/evals, scripts de setup/rollout y despliegues AWS/Azure. Se agregarán módulos pequeños para contratos de investigación/evidencia, políticas de excepción y recepción de secretos, reutilizando `execution_store`, procedencia y transporte existentes. Las operaciones externas, gastos, permisos IAM y despliegues siguen sujetos a autorización específica; implementar esta mejora no autoriza desplegar ni modificar políticas remotas. No se incorporarán secretos reales a pruebas o documentación.
