## Purpose

Permitir avanzar sin credenciales cuando el usuario lo decide explícitamente, manteniendo alternativas locales y límites honestos de validación.

## ADDED Requirements

### Requirement: Solicitud temprana con alternativa sin credenciales
El bot SHALL detectar credenciales faltantes durante exploración y comunicar servicio, entorno, permisos mínimos, pruebas, efectos y gasto previsto. SHALL ofrecer compartir un secreto seguro, continuar omitiendo validaciones dependientes o mantener pausa. No SHALL inferir presupuesto o permisos remotos de autorización de herramientas locales.

#### Scenario: Usuario no puede proporcionar key
- **WHEN** el usuario declara en lenguaje natural que no proporcionará la key y pide continuar
- **THEN** el bot omite validaciones dependientes autorizadas, ejecuta alternativas disponibles y continúa la tarea

### Requirement: Excepciones precisas y durables
Una excepción SHALL registrar decisión original, identidad del mensaje/autor, motivo, checks o capacidades exactas y alcance. SHALL sobrevivir reinicios, HOLD y recuperación de sesión sin repetir la misma solicitud. Cambios materiales SHALL revisar aplicabilidad; cambios administrativos no SHALL invalidarla. Ausencia de credencial no constituye autorización. La excepción no SHALL autorizar omitir otras validaciones, modificar seguridad/retención, ampliar alcance, merge o despliegue.

#### Scenario: Negación o pregunta
- **WHEN** el usuario escribe «NO omitir e2e» o pregunta qué significa omitir pruebas
- **THEN** no se registra autorización de omisión

#### Scenario: Recuperación y cambio de alcance
- **WHEN** una tarea con excepción se recupera y el alcance de pruebas permanece igual
- **THEN** se conserva excepción sin solicitar nuevamente la key

#### Scenario: Excepción específica
- **WHEN** el usuario omite inferencia remota de un proveedor
- **THEN** los checks locales y las validaciones de otros proveedores siguen aplicando

### Requirement: Reportes de omisión sin falsos pass
El bot SHALL separar resultados de ejecución de excepciones y mostrar omisiones y alternativas en conversación y PR. SHALL permitir promoción del trabajo con excepciones autorizadas aplicables, sin afirmar validación upstream ni preparación para producción sin evidencia.

#### Scenario: PR sin inferencia real
- **WHEN** alternativas locales pasan y el usuario autorizó omitir inferencia remota
- **THEN** la tarea puede avanzar y el PR indica pruebas locales exitosas y pruebas upstream omitidas por decisión del usuario
