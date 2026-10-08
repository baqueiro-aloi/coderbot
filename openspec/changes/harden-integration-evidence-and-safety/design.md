## Context

Ver `proposal.md` para motivación y las ocho delta specs para contrato. El proyecto usa módulos Python planos, FSM en `src/main.py`, ejecución determinista y SQLite versionado en `execution_store`, dos runners y canales independientes. Ya existen procedencia, backups, transporte durable y manifest de evidencia; se extenderán en lugar de crear otro supervisor. El sweep encontró además políticas contradictorias entre prompts y código, funciones de cobertura sin wiring y cache insuficiente para entorno mutable.

## Goals / Non-Goals

**Goals:** contratos pequeños y tipados; decisiones del usuario aplicadas por controlador; defensa antes de persistencia; resultados conservadores; recuperación compatible; tests reales del wiring y no solo helpers.

**Non-Goals:** desplegar esta rama, gastar inferencia o modificar IAM sin autorización específica; instalar infraestructura PrivateBin remotamente; eliminar o reescribir historial Git previo; afirmar aislamiento absoluto de un agente con acceso al daemon Docker. Endurecer permisos de infraestructura no equivale a una sandbox completa.

## Decisions

### 1. Inventario de integración y evidencia separado de instrucciones

Añadir contratos versionados para integración, fuentes/versiones, incertidumbres y requisitos. El agente propone datos y checks; controlador valida schemas, existencia de referencias y ejecución. Una URL registrada no demuestra que se consultó documentación ni que esta aplica: registrar extracción/fuente y contraste con versión efectiva. Reutilizar los artifacts OpenSpec aprobados y guardar recibos privados en `execution_store`, sin planes paralelos del target. Alternativa descartada: checklist textual solo en prompts, porque deja decisiones a autoafirmaciones del modelo.

### 2. Excepciones semánticas, específicas y persistentes

Eliminar detección por substring. Clasificación de mensaje completo produce propuesta de excepción; controlador exige mensaje autorizado, resolución inequívoca y selección explícita de checks/capacidades ya inventariados. Mensajes ambiguos piden aclaración. Una negativa explícita a proporcionar key junto con continuación concede omisión dependiente, no cierre de tarea. Registrar id de decisión, razón, scope semántico e ids exactos; nueva versión del alcance revisa aplicabilidad sin volver a pedir credencial por cambios administrativos. Gates calculan aceptación sobre resultados y excepciones separadas. Alternativa descartada: bandera global skip-live/skip-e2e, que amplía consentimiento.

### 3. Frontera privada para secretos

Introducir un receptor confiable previo a Slack inbox, feedback y conversation persistidos; usa un backend para referencia provisionada o enlace de proveedor configurado, nunca navegación genérica del agente. Permitir solo instancias HTTPS explícitas, evitar unfurls, validar DNS/IP y cada redirect, limitar bytes/tiempo y separar ciphertext/URL privada del historial. PrivateBin requiere descifrado local compatible con versión real del protocolo: verificar documentación oficial y cliente mantenido antes de elegir dependencia, pin y vectores de compatibilidad. Si instancia/protocolo no está soportado, informar y ofrecer referencia provisionada u override, sin fallback inseguro.

Guardar secretos temporalmente fuera de repo/outbox en directorio 0700, archivo 0600 y TTL; historial guarda solo handle opaco. Inyectar al subprocess indicado sin argv ni echo. Registrar valores sensibles dinámicamente para sanitización de todo output. No es posible hacer atómico consumir remoto y persistir local: ante crash en esa ventana pedir nuevo enlace, conservando trabajo. Un enlace completo enviado por usuario permanece bajo retención del proveedor de chat; documentar ese límite y preferir credenciales temporales.

Unificar sanitización de inbox/model context, logs, check outputs, checkpoints, reportes y attachments textuales; rechazar publicación si scan detecta secretos. Imágenes/videos no admiten redacción textual fiable: usar cuentas/datos sintéticos y gate de publicación seguro. Retirar copia de transcript crudo a Git; opcional resumen con campos permitidos. Boot desactiva xtrace y clone usa helper de credenciales sin URL autenticada.

### 4. Proveniencia de checks y review

Versionar `Check` y adapters: tipo, requisitos/scenarios, dependencias externas, configuración relevante, política de vigencia y recursos. Reporters conocidos validan counts/resultados/skips; build/lint no requieren test count pero sí salida reconocida y ejecución real. Reporters desconocidos no certifican pruebas por exit cero. Coverage enlaza receipts controller-run, no strings libres. Fixtures prueban contratos negativos y SDK/proxy reales; live smoke requiere acción/budget concretos o excepción. Review independiente registra recibo de sesión/resultado, snapshot y findings; comprobar wiring en ambos runners.

Manifests incluyen run, selección, tipo y resultado, sin aceptar media no vacía como prueba. Newman usa runner común y JSON/JUnit contrastado con exit status; fallos conservan diagnósticos. Selección por nombres base no prueba identidad: mantener paths relativos y evitar colisiones. Reconciliación de entrega no equivale a validar contenido funcional.

### 5. Cache por configuración efectiva y tiempo

Identidad privada mediante HMAC para valores de env/secret; inventariar settings consumidos y resolver configuración efectiva de proceso/harness, además de versiones de paquetes instalados y runtime. No hashear solo manifest para demostrar instalación. Reuse remota requiere TTL y contexto de destino/acceso; cambio de credencial/permisos invalida bloqueos y resultados dependientes. Checkpoints incorporan revisión de requisitos externos y políticas, manteniendo replays seguros ante fallos de transporte. Alternativa descartada: desactivar todos caches, porque pierde recuperación válida y encarece tarea.

### 6. Propiedad y límites operacionales

Usar `repo_provenance` y recovery para atribución verificable; no atribuir por fase, branch ni decisión del modelo sin referencia comprobable. Preservar ambiguos con backup/worktree y no ejecutar resets destructivos. HOLD guarda paths exclusivos de tarea y reporta fallos. Reparación de entorno local no autoriza IAM, datos remotos, gasto o matar procesos ajenos por colisión de puerto. Revisar reglas en prompts/skills/resumes para no contradecir controlador. Autonomía se mantiene para decisiones locales menores.

### 7. Clientes y merge

Validar payloads mínimos y paginar colecciones anidadas; distinguir unknown de vacío. Tras mutación verificar efecto cuando aplique; no usar snapshot anterior como confirmación de claim. Reads y writes idempotentes tienen retries limitados; creación/comentarios ambiguos usan marcador/recibo/reconciliación o se pausan sin duplicar. HTTP 400 de Docs solo se considera revisión obsoleta con evidencia específica. Helpers de descargas eliminan auth cross-host y controlan tamaño/tiempo.

Registrar SHA remoto al presentar PR y volver a verificar con `gh pr view`; merge usa `--match-head-commit` del SHA autorizado, sin bypass por waiver o force de threads. Excepciones visibles en sección bot-owned de PR, preservando edición humana. Historial de revisión y políticas de publicación liga contenido exacto, no snapshot local únicamente.

### 8. Release y migración

Separar señal liveness de probes readiness/smoke configurados. Rollout registra imagen digest, SHA, versiones y configuración segura, verifica recuperación del estado y evidencia funcional; comando systemd active no basta. Sin probe pertinente, reporte dice readiness no verificada; no inventa smoke por conveniencia. Rollback conserva state/target y valida restauración, no garantiza reversión automática de schema incompatible.

Migración aditiva de SQLite/JSON: leer registros antiguos, preservar historial; recibos incompletos quedan no verificados. Excepciones antiguas ambiguas no se amplían ni se aceptan por substring; pedir alcance una vez cuando no exista consentimiento demostrable. Pruebas de integración cubren FSM normal, legacy, lateral y recovery para ambos canales/runners. No archive ni push automático de este cambio.

## Risks / Trade-offs

- Sanitización nunca garantiza detectar cualquier secreto arbitrario → reducir acceso, registrar valores dinámicos, schemas de salida permitidos y tests de todos sinks; documentar límites.
- Consumo de enlace no transaccional → estado privado durable y recuperación explícita/reenvío.
- Gates conservadores pueden requerir configuración de targets antiguos → adapters compatibles, errores accionables y excepción acotada.
- Usuario puede aceptar menor evidencia → reporte visible, sin alterar seguridad ni fingir validación.
- API de proveedor/SDK puede variar → documentación de versión, fixtures protocolarios y prueba viva autorizada.
- Shell/daemon Docker amplían superficie de privilegios → límites verificables donde existan, sin afirmar sandbox completa.

## Migration Plan

1. Implementar primero protección de secretos/trabajo con regresiones; conservar `ISSUES.md` ajeno sin incorporarlo automáticamente.
2. Introducir contratos/adapters/migración y excepciones, después wiring de investigación y recepción privada.
3. Conectar coverage/review/cache y clientes, luego merge/release.
4. Ejecutar suites Python, tests JavaScript del runtime y OpenSpec strict; escenarios de presión sobre ambos runners/canales.
5. Con autorización separada, piloto aislado con integración real y otro sin key con override; registrar readiness y rollback. No declarar producción lista ni ejecutar gasto sin autorización.
