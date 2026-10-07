## Purpose

Permitir preguntas, comentarios y cambios en el chat de una tarea sin bloquear al usuario durante el trabajo ni confundir conversación con autorización del flujo.

## ADDED Requirements

### Requirement: Enrutamiento antes de actuar
El bot SHALL distinguir comandos operativos explícitos, respuestas válidas a la decisión activa, conversación, solicitudes de cambio y mensajes ambiguos antes de ejecutar acciones. SHALL interpretar el mensaje completo con la pregunta, alternativas, detalles requeridos y contexto reciente. Sin pregunta activa, un mensaje no operativo SHALL tratarse como conversación o aporte de contexto/cambio. Un error técnico SHALL NOT provocar reinterpretación como conversación de una acción ya iniciada.

#### Scenario: Pregunta explicativa durante un bloqueo
- **WHEN** el usuario escribe “No entiendo, ¿qué tenemos que hacer?” con una decisión de recuperación pendiente
- **THEN** el bot explica el bloqueo y las alternativas sin reintentar, cancelar ni consumir la decisión

#### Scenario: Respuesta incompleta
- **WHEN** el usuario elige una opción válida que requiere detalles sin proporcionarlos
- **THEN** el bot solicita los detalles y conserva la decisión, sin ejecutar la acción ni tratar la selección como conversación genérica

#### Scenario: Ambigüedad con consecuencias
- **WHEN** “vamos a continuar” no identifica inequívocamente una acción válida
- **THEN** el bot pide aclaración y no asume aprobación, reintento, merge ni finalización

#### Scenario: Mensaje sin pregunta activa
- **WHEN** el usuario pregunta por la tarea o aporta contexto sin una decisión activa
- **THEN** el bot procesa el mensaje conversacionalmente sin requerir una respuesta de opciones

### Requirement: Conversación explícita mediante btw
El bot SHALL aceptar `/btw <texto>` en el hilo autorizado como conversación explícita. Su contenido SHALL NOT ejecutar comandos operativos ni resolver la decisión activa, aunque contenga palabras como retry o approve. Las solicitudes de cambio dentro de `/btw` SHALL registrarse y evaluarse sin aprobarlas implícitamente.

#### Scenario: Explicación explícita
- **WHEN** el usuario escribe `/btw ¿qué significa retry?`
- **THEN** el bot explica el término y conserva la decisión pendiente

#### Scenario: Cambio explícito lateral
- **WHEN** el usuario escribe `/btw también necesitamos filtrar por proveedor`
- **THEN** el bot registra la solicitud para evaluación y no modifica código ni autoriza alcance nuevo

### Requirement: Respuesta concurrente aislada
La conversación paralela SHALL estar siempre habilitada como comportamiento predeterminado, sin requerir una bandera o variable de entorno.
El bot SHALL poder responder conversación mediante una sesión independiente mientras continúa un turno de trabajo. Esa sesión SHALL tener restricciones efectivas que impidan editar código, ejecutar operaciones mutantes y controlar el flujo. SHALL usar contexto de la tarea y estado confirmado, distinguir trabajo en curso de resultados verificados y conservar historial lateral relevante. Seguimiento, fallos y cancelación conversacionales SHALL NOT alterar el turno de trabajo. La recepción de comandos operativos SHALL seguir disponible durante una respuesta lateral.

#### Scenario: Consulta durante implementación
- **WHEN** el usuario pregunta qué se está implementando mientras el agente trabaja
- **THEN** una sesión independiente responde antes de que sea necesario terminar el turno de trabajo, sin interrumpirlo ni sustituir su sesión

#### Scenario: Fallo de la sesión lateral
- **WHEN** la sesión conversacional falla o se cancela
- **THEN** el turno de trabajo conserva su seguimiento y continúa; el mensaje lateral queda registrado con un resultado recuperable o un fallo explícito

### Requirement: Decisiones pendientes y respuestas vinculadas
La conversación SHALL preservar la pregunta, opciones, continuación y contador de respuestas pendientes. Toda respuesta candidata SHALL revalidarse contra la tarea y versión de decisión actuales antes de ejecutar su acción. Una respuesta desactualizada SHALL NOT autorizar otra decisión por coincidencia de número o texto.

#### Scenario: Explicación y respuesta posterior
- **WHEN** el bot explica una opción y el usuario después responde válidamente a la decisión original
- **THEN** el controlador aplica la respuesta a esa decisión sin que la explicación haya consumido un intento de respuesta

#### Scenario: Decisión cambia durante clasificación
- **WHEN** la decisión cambia mientras se clasifica una respuesta
- **THEN** el controlador reevalúa o solicita aclaración antes de actuar y no aplica la clasificación anterior a la nueva decisión

### Requirement: Incorporación durable de contexto y cambios
El bot SHALL registrar mensajes originales, tarea, intención y estado de procesamiento de forma durable antes de confirmarlos. SHALL distinguir recibido, pendiente de aclaración/aprobación, incorporado y aplicado. Contexto aclaratorio SHALL entregarse al agente de trabajo en el siguiente punto seguro. Correcciones dentro del alcance aprobado SHALL pasar por reparación y verificación existentes; cambios de alcance SHALL pasar por revisión de propuesta y aprobación explícita. Una solicitud ambigua SHALL aclararse lateralmente sin bloquear el trabajo independiente. Una solicitud explícitamente reemplazada SHALL NOT aplicarse junto con su reemplazo.

#### Scenario: Nuevo alcance durante trabajo
- **WHEN** el usuario solicita una capacidad fuera del alcance aprobado durante implementación
- **THEN** el bot registra y confirma la solicitud sin afirmar que está aplicada, y solicita aprobación del alcance revisado antes de implementarla

#### Scenario: Contexto después de reinicio
- **WHEN** el proceso reinicia después de registrar una aclaración antes de incorporarla
- **THEN** el siguiente turno recibe la aclaración pendiente sin perderla ni aplicarla dos veces

#### Scenario: Solicitud corregida
- **WHEN** el usuario reemplaza explícitamente una solicitud pendiente por otra
- **THEN** el bot conserva el historial y procesa únicamente la solicitud vigente

### Requirement: Puntos seguros y mensajes mixtos
El controlador SHALL revisar aportes pendientes al terminar el turno actual y antes del siguiente paso, publicación de PR o merge. Una conversación informativa SHALL NOT bloquear esos pasos. Solicitudes pendientes que afecten entrega o alcance SHALL resolverse o requerir una decisión antes de publicar o fusionar. Un mensaje mixto SHALL conservar tanto la acción propuesta como el cambio; si la acción depende del cambio o es ambigua, SHALL pedir aclaración antes de ejecutarla. Un cambio que invalide trabajo actual SHALL ofrecer detener o reorientar, sin interrumpir automáticamente.

#### Scenario: Reintento condicionado
- **WHEN** el usuario escribe “antes de reintentar agrega X”
- **THEN** el bot registra el cambio y no reintenta como si la condición no existiera

#### Scenario: Cambio pendiente al publicar
- **WHEN** el controlador está por publicar un PR con una solicitud material pendiente
- **THEN** evalúa la solicitud y resuelve su efecto o pide una decisión antes de publicar

### Requirement: Compatibilidad y entrega recuperable
Las nuevas rutas SHALL mantener autorización, ámbito de instancia, idioma e hilo de Slack y email. Recepción, clasificación y entrega SHALL soportar reinicios y deduplicación por identidad de mensaje. Reintentar entrega de una respuesta ya generada SHALL NOT regenerarla ni volver a aplicar una acción del flujo.

#### Scenario: Fallo de entrega
- **WHEN** se genera una explicación y el transporte falla antes de confirmar su entrega
- **THEN** el bot reintenta entregar la respuesta guardada sin repetir la generación ni cambiar la decisión pendiente

#### Scenario: Mensaje para otra instancia
- **WHEN** llega un comando dirigido a otra instancia en el hilo
- **THEN** conserva el enrutamiento existente y no lo trata como autorización o contexto de esta tarea
