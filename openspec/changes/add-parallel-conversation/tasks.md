## 1. Contratos y persistencia

- [x] 1.1 Añadir registro durable de conversación con identidad de mensaje/tarea, snapshot, ruta, sesión, clasificación, resultado y estado de entrega; mantener compatibilidad con feedback existente.
- [x] 1.2 Implementar snapshots acotados y consistentes con pregunta/opciones, versión de decisión, bloqueo, progreso confirmado, requisitos e historial lateral filtrado.
- [x] 1.3 Añadir estados y referencias para aportes de contexto/cambio, aclaraciones y sustituciones explícitas; deduplicar recepción y enlaces con feedback.

## 2. Enrutamiento seguro

- [x] 2.1 Implementar parsing de `/btw` como prefijo de texto del hilo, sin interpretar su contenido como comandos ni alterar ámbito/autorización existentes.
- [x] 2.2 Añadir clasificación estructurada y validada de respuesta, conversación, cambio y ambigüedad usando mensaje completo y contexto; conservar partes/dependencias de mensajes mixtos.
- [x] 2.3 Validar selecciones exactas y detalles requeridos antes de ejecutar handlers; incorporar fallback semántico conversacional antes de efectos, nunca por fallos técnicos posteriores.
- [x] 2.4 Revalidar identidad/version de decisión antes de aplicar respuestas y preservar pregunta, opciones, continuación y contador durante conversación o aclaración lateral.

## 3. Runner conversacional aislado

- [x] 3.1 Separar actividad, procesos, presupuestos y cancelación por rol/invocación, manteniendo STATUS/KICK y checkpoints del turno de trabajo.
- [x] 3.2 Añadir API de sesión conversacional independiente y persistencia de su identidad/historial sin resumir ni reemplazar la sesión de trabajo.
- [x] 3.3 Implementar restricciones efectivas de herramientas en adaptadores soportados: lectura segura o text-only cuando no pueda garantizarse lectura; prohibir edición, shell mutante y delegación.
- [x] 3.4 Probar aislamiento del runner y cancelación, incluida finalización/fallo lateral mientras el turno de trabajo permanece activo.

## 4. Recepción y respuesta concurrentes

- [x] 4.1 Centralizar recepción durable desde waits y supervisor para evitar consumo doble, conservar comandos existentes y admitir conversación sin pregunta activa.
- [x] 4.2 Crear worker lateral con cola serial por tarea, independiente del supervisor de comandos y del turno de trabajo; manejar shutdown, reinicios y resultados de tareas anteriores.
- [x] 4.3 Generar explicaciones y aclaraciones con contexto confirmado y límites de autoridad, registrando resultado antes de entregar en el idioma/hilo correcto.
- [x] 4.4 Reutilizar recibos de entrega para reintentar solo transporte y recuperar generación interrumpida sin regenerar respuestas ya completadas.

## 5. Transferencia y cambios

- [x] 5.1 Entregar contexto listo al siguiente prompt de trabajo y marcar incorporación después del checkpoint exitoso, sin afirmar aplicación de código.
- [x] 5.2 Enlazar cambios con investigación/corrección/replanificación existentes y respetar definición inicial durante exploración/propuesta y aprobación explícita de alcance posterior.
- [x] 5.3 Resolver aclaraciones y reemplazos laterales sin consumir decisiones del flujo; reflejar estados recibido, pendiente, incorporado, aprobado y aplicado en respuestas pertinentes.
- [x] 5.4 Revisar aportes al terminar turnos y antes de siguiente fase/publicación/merge; no bloquear por consultas informativas y resolver solicitudes materiales pendientes antes de entrega.
- [x] 5.5 Gestionar mensajes mixtos y cambios invalidantes: no ejecutar acciones condicionadas sin resolver su dependencia, y ofrecer pausa/reorientación sin interrupción automática.

## 6. Validación y documentación

- [x] 6.1 Añadir regresiones del ejemplo “No entiendo, ¿qué tenemos que hacer?”, opciones incompletas, negaciones, respuestas válidas, `/btw`, ambigüedad y mensajes mixtos en los waits relevantes.
- [x] 6.2 Probar concurrentemente respuesta lateral antes de terminar trabajo, recepción de STATUS/KICK durante esa respuesta, decisiones desactualizadas y cambio de tarea.
- [x] 6.3 Probar persistencia/reinicio/deduplicación, sustituciones, fallos de generación/entrega y transferencia exactamente una vez mediante checkpoints.
- [x] 6.4 Probar Slack/email, adaptadores de harness y barreras de publicación/merge; ejecutar suite de regresión y validación OpenSpec estricta.
- [x] 6.5 Documentar `/btw`, clasificación automática, estados de cambios, alcance del hilo de tarea y recuperación/rollback seguro.
