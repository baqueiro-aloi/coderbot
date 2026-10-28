"""Brief transition reasons derived from controller state, not inferred success."""
import json


REASONS = {
    "IDLE": ("This task has ended; I'm waiting for the next task.", "Esta tarea terminó; estoy esperando la siguiente."),
    "EXPLORING": ("This task is selected; I'm checking the affected code.", "Esta tarea está seleccionada; estoy revisando el código afectado."),
    "PROPOSING": ("Exploration is complete; I'm preparing the proposal.", "La exploración terminó; estoy preparando la propuesta."),
    "REPLANNING": ("The requested changes affect the plan; I'm revising the proposal.", "Los cambios solicitados afectan el plan; estoy revisando la propuesta."),
    "WAIT_APPROVAL": ("I need your approval of the proposal before implementation.", "Necesito tu aprobación de la propuesta antes de implementar."),
    "IMPLEMENTING": ("Approved work remains to be completed; I'm implementing it.", "Queda trabajo aprobado por completar; estoy implementándolo."),
    "APPLY_FEEDBACK": ("Requested corrections remain; I'm applying them.", "Quedan correcciones solicitadas; estoy aplicándolas."),
    "VERIFYING": ("The work is ready for verification; I'm checking it.", "El trabajo está listo para verificación; estoy comprobándolo."),
    "INTERNAL_REVIEW": ("The implementation needs an independent review before proceeding.", "La implementación necesita una revisión independiente antes de continuar."),
    "E2E": ("The selected end-to-end checks are next; I'm running them.", "Siguen las pruebas de extremo a extremo seleccionadas; estoy ejecutándolas."),
    "REPAIR_CHECKS": ("Verification is unresolved; I'm diagnosing and repairing the checks.", "La verificación sigue pendiente; estoy diagnosticando y corrigiendo los checks."),
    "EVIDENCE_REVIEW": ("The recovered evidence needs review before delivery.", "La evidencia recuperada necesita revisión antes de entregarse."),
    "ARCHIVING": ("The next step is to archive the approved change.", "El siguiente paso es archivar el cambio aprobado."),
    "OPEN_PR": ("The next step is publication; I'm preparing the pull request.", "El siguiente paso es publicar; estoy preparando el pull request."),
    "PUSHING": ("New commits need publication; I'm updating the pull request.", "Los nuevos commits necesitan publicación; estoy actualizando el pull request."),
    "WAIT_REVIEW": ("Review is pending; I'm waiting for its result.", "La revisión está pendiente; estoy esperando su resultado."),
    "WAIT_MERGE": ("I need explicit merge approval before continuing.", "Necesito aprobación explícita del merge antes de continuar."),
    "ADDRESS_REVIEW": ("Review feedback needs changes; I'm addressing it.", "La revisión solicita cambios; estoy atendiéndolos."),
    "ADDRESS_PR_THREADS": ("Pull-request comments need attention; I'm addressing them.", "Los comentarios del pull request necesitan atención; estoy atendiéndolos."),
    "RESOLVE_CONFLICTS": ("The branches have merge conflicts; I'm resolving them.", "Las ramas tienen conflictos de merge; estoy resolviéndolos."),
    "WAIT_REPLY": ("I need your answer to continue this step.", "Necesito tu respuesta para continuar este paso."),
    "WAIT_STUCK": ("This step could not complete; I need recovery guidance.", "Este paso no pudo completarse; necesito indicaciones de recuperación."),
    "WAIT_CLEAN": ("Existing checkout changes must be preserved before proceeding.", "Los cambios existentes del repositorio deben preservarse antes de continuar."),
    "RECOVERING": ("An execution or repository condition needs repair before continuing.", "Una condición de ejecución o del repositorio necesita reparación antes de continuar."),
}


def _count(value):
    return len(value) if isinstance(value, list) else value if type(value) is int and value >= 0 else 0


def reason(state):
    language = 1 if (state.get("task_language") or "English").casefold() == "spanish" else 0
    phase = state["state"]
    if phase == "APPLY_FEEDBACK" and (state.get("pending_feedback") or "").startswith("Fix internal review findings:"):
        review = {}
        for line in state["pending_feedback"].splitlines():
            if line.startswith("INTERNAL_REVIEW:"):
                try:
                    value = json.loads(line.partition(":")[2])
                    review = value if isinstance(value, dict) else {}
                except ValueError:
                    review = {}
        count = _count(review.get("critical")) + _count(review.get("important"))
        if count:
            return (f"Review reported {count} issue{'s' if count != 1 else ''}; I'm fixing them.",
                    f"La revisión reportó {count} problema{'s' if count != 1 else ''}; estoy corrigiéndolos.")[language]
        return ("I couldn't validate the review report; it needs correction before proceeding.",
                "No pude validar el informe de revisión; necesita corrección antes de continuar.")[language]
    if phase == "VERIFYING" and state.get("reported_check_plan_error"):
        return ("The check plan has an invalid format; I'm correcting it before verification.",
                "El plan de checks tiene un formato inválido; estoy corrigiéndolo antes de verificar.")[language]
    if phase == "VERIFYING" and state.get("banner_state") in ("APPLY_FEEDBACK", "REPAIR_CHECKS", "RECOVERING"):
        return ("The repair turn finished; I'm checking the changes.",
                "El turno de reparación terminó; estoy comprobando los cambios.")[language]
    if phase == "REPAIR_CHECKS":
        count = sum(c.get("gate", {}).get("status", c.get("status")) != "pass"
                    for c in (state.get("final_check_report") or {}).get("checks", []))
        if count:
            return (f"Verification reported {count} unresolved check{'s' if count != 1 else ''}; I'm diagnosing them.",
                    f"La verificación reportó {count} checks pendientes; estoy diagnosticándolos.")[language]
    return REASONS.get(phase, ("I'm continuing this step; existing work is preserved.",
                              "Estoy continuando este paso; el trabajo existente se conserva."))[language]
