## Purpose

Vincular autorización de merge al contenido remoto revisado y distinguir despliegue operativo de simples señales de proceso vivo.

## ADDED Requirements

### Requirement: Merge ligado al SHA revisado
El bot SHALL registrar head SHA remoto presentado para revisión y validar ese SHA inmediatamente antes de merge con condición atómica del proveedor. Un push remoto posterior SHALL requerir revisión del contenido actualizado; snapshot local no sustituye head remoto. Excepción de pruebas no SHALL autorizar merge ni omitir este control.

#### Scenario: Push externo después de aprobación
- **WHEN** cambia head remoto entre revisión y merge
- **THEN** merge no aplica al nuevo contenido bajo aprobación anterior

### Requirement: Estados de release y smoke funcional
Bot y herramientas SHALL distinguir implementado, probado localmente, validado upstream, desplegado y validado postdespliegue. Despliegue autorizado SHALL comprobar imagen/SHA, versiones/configuración efectivas, recuperación de estado y smoke funcional; liveness no demuestra readiness. Cambios que requieran imagen o env SHALL reconstruir/recrear según corresponda. Rollback SHALL preservar estado y trabajo, y reportar limitaciones.

#### Scenario: Servicio active sin integración funcional
- **WHEN** proceso está active/healthy pero smoke requerido falla
- **THEN** no se declara release funcional y se ejecuta recuperación/rollback autorizado o se reporta pendiente

#### Scenario: Implementación sin autorización de despliegue
- **WHEN** código y pruebas están completos pero no existe autorización de despliegue
- **THEN** se informa despliegue pendiente y no se modifica entorno remoto
