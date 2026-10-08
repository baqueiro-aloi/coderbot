## Purpose

Proteger trabajo humano, secretos locales y cambios ambiguos durante planificación, recuperación y pausa de tareas autónomas.

## ADDED Requirements

### Requirement: Procedencia antes de limpieza o commit
El bot SHALL atribuir cambios mediante evidencia de procedencia; fase, branch o presencia de archivos no demuestran propiedad. Cambios ambiguos SHALL preservarse mediante backup/aislamiento antes de recuperación. Limpieza de planning no SHALL descartar trabajo desconocido ni resetear branches ajenas. HOLD SHALL guardar únicamente trabajo atribuible, sin staging global o inclusión automática de untracked.

#### Scenario: Edición humana durante planning
- **WHEN** un humano modifica archivo mientras bot explora
- **THEN** limpieza preserva edición y no la considera premature work por fase

#### Scenario: HOLD con archivo secreto untracked
- **WHEN** usuario pausa tarea con archivo secreto no atribuible
- **THEN** archivo permanece fuera del commit del bot y no se elimina

### Requirement: Estado de recuperación honesto
El bot SHALL informar fallos de guardado o aislamiento sin afirmar que todo trabajo está committed. SHALL conservar aprobaciones y excepciones, impedir ampliación autónoma de privilegios remotos y evaluar requests de review contra alcance/seguridad aprobados.

#### Scenario: Commit de pausa falla
- **WHEN** no se puede guardar todo trabajo atribuible
- **THEN** reporte identifica pendiente y recuperación conserva la copia existente
