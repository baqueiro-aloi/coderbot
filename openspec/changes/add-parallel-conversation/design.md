## Context

Ver `proposal.md` para motivación y `specs/parallel-conversation/spec.md` para el contrato. `main.py` ya recibe feedback durante turnos activos desde el supervisor y lo aplica después desde el controlador. Sin embargo, `WAIT_REPLY` usa un clasificador con respuesta por defecto y `WAIT_STUCK` devuelve instrucciones de recuperación cuando no entiende el mensaje. El runner mantiene un único `_turn` global y la cancelación registra procesos sin rol. La cola existente de feedback y las entregas durables son los puntos de integración, no deben duplicarse con una segunda máquina de implementación.

## Goals / Non-Goals

**Goals:**
- Un único dueño del estado del flujo; workers conversacionales producen resultados persistidos, nunca transiciones directas.
- Respuestas laterales concurrentes con aislamiento efectivo y contexto acotado, sin editar el árbol de trabajo.
- Reutilizar feedback, checkpoints y entregas con identidad de mensaje y estados explícitos.

**Non-Goals:**
- Dos agentes editando el mismo repositorio, inyección durante un turno activo o autorización por conversación lateral.
- Responder sobre otra tarea o crear una tarea nueva desde mensajes sin hilo de tarea. “En cualquier momento” abarca el hilo autorizado de una tarea, esté trabajando o esperando.
- Inferir resultados de herramientas todavía en ejecución o compartir secretos/transcripciones completas indiscriminadamente.

## Decisions

### 1. Recepción común y clasificación sin efectos

Crear una ruta común para mensajes del hilo tanto desde waits como desde el supervisor. Registrar primero el mensaje original con identidad de tarea/hilo. Prioridad: `/btw` fuerza conversación; comandos operativos existentes fuera de `/btw` conservan dueño; selecciones exactas se validan determinísticamente; el resto pasa por clasificación semántica estructurada. La clasificación incluye intención, si resuelve la decisión, acción candidata, aportes de contexto/cambio y dependencias entre ellos. Validar enumeraciones y campos; salida inválida no autoriza acciones.

El clasificador usa pregunta y opciones exactas, requisitos de detalles, fase e historial acotado. No usar un umbral numérico de confianza como autorización: comprobaciones del controlador y autorización explícita son necesarias. Frente a ambigüedad material se pide aclaración. Mensajes mixtos preservan todas las partes; la dependencia bloquea únicamente la acción condicionada. Un error técnico de un handler no dispara fallback conversacional.

### 2. Sesión conversacional y workers independientes

Mantener una sesión lateral por tarea, con cola serial por conversación y un worker independiente del supervisor de comandos. El worker puede clasificar y responder durante un turno principal; el supervisor sigue atendiendo STATUS/KICK y recepción. Registrar sesiones y procesos por rol e identidad de invocación. El estado público de trabajo y KICK siguen apuntando al rol de trabajo; errores o finalización lateral no limpian operaciones ni actividad principales. Presupuestos, cancelación y contexto deben ser locales a la invocación.

Añadir una API explícita de conversación al runner y adaptar los harnesses soportados. No reutilizar `contract=False` como supuesto aislamiento: hoy también inicia/finaliza el turno global. Usar permisos efectivos: prohibir escritura, shell y herramientas mutantes/delegación; permitir solo lecturas necesarias o operar únicamente sobre contexto suministrado si el adaptador no puede garantizar herramientas de solo lectura. Nunca degradar a un agente con permisos de build. Esto evita confiar en un prompt como barrera de seguridad.

Alternativa descartada: esperar al turno principal para todas las consultas, porque incumple la respuesta concurrente. También se descarta resumir la sesión principal desde el worker.

### 3. Contexto versionado, sin estado compartido mutable

El controlador publica snapshots consistentes: identidad de tarea, fase, decisión y versión, bloqueo, progreso confirmado, requisitos, referencias a propuesta/diseño/checks y conversación reciente. Basarse en `handoff_context` y hechos persistidos; ampliar con pregunta/opciones y progreso. Filtrar secretos y acotar tamaño. Si se leen archivos mientras el agente escribe, no presentarlos como evidencia verificada; preferir artefactos/checkpoints confirmados.

Guardar junto a la clasificación la identidad/version de decisión. Antes de ejecutar una respuesta, el controlador comprueba vigencia y reevalúa si cambió. Al cambiar de tarea, un resultado lateral viejo solo pertenece a su hilo original: no puede mutar la nueva tarea. Las aclaraciones laterales usan referencias al mensaje que aclaran y no reemplazan `pending_question`, `return_state` ni `question_rounds` del flujo.

### 4. Persistencia y transferencia al flujo

Extender registros existentes o añadir un tipo de registro de conversación compatible con `ExecutionStore`: mensaje original, texto normalizado, ruta, snapshot/version, sesión lateral, clasificación, aclaración relacionada, aporte vigente, estado de generación y entrega. Registrar resultados antes de entregar; usar recibos existentes para reintentar solo transporte. Deduplicar por tarea y mensaje. Una invocación interrumpida queda recuperable; una respuesta completada nunca se regenera por fallo de entrega.

Los aportes se enlazan con feedback durable y estados de recibido, aclaración pendiente, listo, incorporado, esperando aprobación, aplicado o reemplazado. El controlador procesa aportes listos al terminar cada turno antes del siguiente paso, incluyendo publicación y merge. Contexto se adjunta al próximo prompt y se marca incorporado tras checkpoint exitoso; no equivale a “código aplicado”. Correcciones y cambio de alcance usan las rutas existentes de investigación, reparación y replanificación/aprobación. En exploración/propuesta se actualiza la definición inicial sin exigir contrato aprobado inexistente.

Una sustitución requiere referencia inequívoca a una solicitud pendiente; si no existe, pedir aclaración. Conversación informativa no bloquea publicación. Cambios materiales o ambiguos sobre entrega se resuelven antes de publicar/fusionar; mensajes posteriores a un merge confirmado no deshacen ese merge. Un cambio invalidante propone pausa/reorientación, sin cancelar por iniciativa lateral.

### 5. Compatibilidad

Mantener parsing y autoridad de comandos existentes en Slack/email, ámbito de instancia y autorización del transporte. `/btw` es prefijo de texto en el hilo, no requiere registrar un slash command en Slack. Mantener idioma y deduplicación existentes. Centralizar recepción evita que supervisor y waits consuman o apliquen el mismo mensaje dos veces; las transiciones siguen siendo del controlador principal.

## Risks / Trade-offs

- [Estado concurrente y cancelación cruzada] → roles, snapshots inmutables, pruebas con barreras y un solo dueño del flujo.
- [Contexto incompleto o en cambio] → snapshots versionados, referencias confirmadas y lenguaje explícito sobre trabajo en curso.
- [Clasificación incorrecta] → comandos/selecciones deterministas, validación del controlador, ambigüedad segura y pruebas de negaciones/mensajes mixtos.
- [Permisos diferentes por harness] → capacidades explícitas y fallback text-only seguro, nunca herramientas mutantes.
- [Latencia/coste adicional] → contexto acotado y cola lateral serial independiente; respuesta concurrente no significa ausencia de latencia del proveedor.
- [Cambio registrado pero no aplicado] → estados visibles, transferencia con checkpoint y barreras previas a entrega.

## Migration Plan

1. Añadir registros/campos compatibles y tratar registros antiguos de feedback mediante el comportamiento existente hasta clasificarlos.
2. Implementar runner aislado y verificar adaptadores antes de habilitar el worker.
3. Integrar recepción común y transferencia en puntos seguros sin modificar las autorizaciones existentes.
4. Ejecutar pruebas de regresión y flujos concurrentes en ambos canales; documentar `/btw` y estados de solicitudes.
5. La conversación paralela forma parte del comportamiento predeterminado, sin bandera ni variable de entorno. Un rollback de versión debe preservar registros pendientes, feedback y recibos para recuperación. No ejecutar como respuestas del flujo mensajes marcados explícitamente `/btw`.
