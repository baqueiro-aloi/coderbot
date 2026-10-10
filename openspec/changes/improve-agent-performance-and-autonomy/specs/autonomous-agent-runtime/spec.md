## Purpose

Permitir ejecución headless autónoma en un entorno de confianza total, con operaciones supervisadas y recuperaciones acotadas que nunca dependan de autorizaciones operativas humanas.

## ADDED Requirements

### Requirement: Unrestricted trusted execution
Coderbot SHALL permitir todas las herramientas y operaciones de entorno del agente principal y de todos sus subagentes, sin permisos interactivos ni restricciones heredadas que bloqueen operaciones necesarias. La política SHALL aplicarse en sesiones nuevas, reanudadas y tras reinicio para Claude y OpenCode. Las aprobaciones de producto y merge SHALL conservarse como decisiones funcionales independientes.

#### Scenario: Subagente usa directorios externos
- **WHEN** un subagente lee, escribe o ejecuta comandos fuera del checkout en el entorno confiable
- **THEN** la operación continúa sin aprobación ni intervención del usuario del bot

#### Scenario: Configuración heredada restrictiva
- **WHEN** una configuración global, de proyecto, de agente o de sesión contiene reglas operativas ask o deny
- **THEN** la política gestionada efectiva permite las operaciones del runtime confiable también al reanudar la sesión

#### Scenario: Permiso residual de sesión hija
- **WHEN** el runtime emite una solicitud de permiso de cualquier descendiente del turno activo
- **THEN** Coderbot la resuelve automáticamente y nunca deja la operación esperando autorización

### Requirement: Bounded operation supervision
Coderbot SHALL supervisar deadlines por operación y un presupuesto agregado por intento, incluyendo reintentos internos. SHALL distinguir espera de proveedor, herramienta activa, subagente, permiso y proceso muerto mediante señales observables. Un proceso con deadline explícito SHALL poder continuar sin stdout mientras no agote dicho deadline; la recuperación SHALL estar acotada y conservar trabajo válido.

#### Scenario: Lectura bloqueada
- **WHEN** una herramienta local no termina dentro de su presupuesto
- **THEN** Coderbot detecta el bloqueo, cancela la operación y registra causa y siguiente acción sin esperar el timeout global de dos horas

#### Scenario: Test silencioso legítimo
- **WHEN** un test sigue vivo sin producir stdout y conserva presupuesto de ejecución
- **THEN** la ausencia de stdout por sí sola no dispara un reinicio

#### Scenario: Reintentos de proveedor
- **WHEN** el proveedor falla y se aplican reintentos o fallback
- **THEN** todos consumen un mismo presupuesto agregado y el agotamiento termina con un resultado explícito

### Requirement: Complete cancellation and cleanup
Coderbot SHALL cancelar y recolectar los procesos administrados y recursos del intento ante KICK, timeout o shutdown, incluidos tests ejecutados por el orquestador y grabación. SHALL registrar cleanup fallido y evitar lanzar un nuevo intento sobre recursos exclusivos aún ocupados.

#### Scenario: KICK durante E2E
- **WHEN** el usuario envía KICK mientras el orquestador ejecuta E2E
- **THEN** se cancela ese intento y sus hijos, se conservan tarea y checkpoints y la siguiente ejecución comienza sin procesos o puertos residuales

#### Scenario: Shutdown durante grabación
- **WHEN** el servicio recibe shutdown mientras graba o convierte evidencia
- **THEN** limpia los recursos propios y persiste una continuación recuperable
