## Why

El chat actual interpreta casi todos los mensajes como respuestas al flujo o instrucciones de recuperación. El usuario necesita pedir explicaciones y aportar contexto en cualquier momento, incluso durante un turno de trabajo, sin resolver accidentalmente una decisión ni esperar a que termine ese turno.

## What Changes

- Enrutar mensajes antes de ejecutar acciones, distinguiendo respuestas válidas, conversación, solicitudes de cambio y ambigüedad.
- Admitir `/btw` como conversación explícita, conservando comandos operativos existentes y decisiones pendientes.
- Responder consultas mediante una sesión independiente de solo lectura mientras la sesión de trabajo continúa.
- Registrar contexto y solicitudes de cambio de forma durable; incorporarlos en puntos seguros mediante los mecanismos existentes de feedback, corrección y replanificación.
- Separar seguimiento, permisos y cancelación de sesiones conversacionales y de trabajo.
- Revalidar respuestas contra la versión de la decisión y distinguir cambios recibidos, aprobados y aplicados.

## Capabilities

### New Capabilities

- `parallel-conversation`: Enrutamiento seguro, conversación lateral concurrente y transferencia durable de contexto y cambios al flujo de trabajo.

### Modified Capabilities

Ninguna. Las nuevas reglas complementan la presentación de decisiones de `lifecycle-communication` sin cambiar sus requisitos.

## Impact

- `src/main.py`: recepción, despacho, supervisor y puntos seguros del controlador.
- `src/agent_runner.py`, `src/turn_control.py` y adaptadores del harness: aislamiento de sesiones, cancelación y permisos verificables.
- `src/feedback.py`, `src/execution_store.py`, `src/handoff_context.py`, `src/handoffs.py` y `src/command_text.py`: intención, contexto, versiones y persistencia.
- Slack y email mantienen el hilo y autorización existentes. Se añaden pruebas de concurrencia, recuperación, enrutamiento y documentación de `/btw`.
- No se introduce edición concurrente del repositorio, aprobación implícita ni una nueva dependencia externa obligatoria.
