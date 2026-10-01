"""Static task language copy avoids programming sessions for boilerplate."""
SPANISH = {
    "Exploration": "Exploración", "Proposal": "Propuesta", "Implementation": "Implementación",
    "I'm exploring the codebase.": "Estoy explorando el código del repositorio.",
    "Verification": "Verificación", "Archiving": "Archivado", "Approval": "Aprobación",
    "PR ready for review": "PR listo para revisión", "PR updated": "PR actualizado",
    "Awaiting approval": "Esperando aprobación", "PR merged": "PR fusionado",
    "Exploration is complete; I'm preparing the OpenSpec proposal.": "La exploración terminó; estoy preparando la propuesta OpenSpec.",
    "Proposal approved; implementation is starting.": "Propuesta aprobada; comienza la implementación.",
    "Implementation is complete; I'm running checks and review.": "La implementación terminó; estoy ejecutando checks y revisión.",
    "Final checks passed; I'm archiving the change.": "Los checks finales pasaron; estoy archivando el cambio.",
    "Verification passed; running internal review": "La verificación pasó; ejecutando revisión interna",
    "service unavailable": "servicio no disponible",
    "feedback received": "mensaje recibido",
    "feedback investigated": "feedback revisado",
    "proposal delivery pending": "entrega de propuesta pendiente",
    "The service is unavailable. Work is preserved; automatic attempts are paused. Reply 'retry' to resume.":
        "El servicio no está disponible. Conservé el trabajo y pausé los intentos automáticos. Responde 'retry' para retomar.",
}

OPERATIONAL = {
    "received": ("Received your message; I will review it before the next step.",
                 "Recibí tu mensaje; lo revisaré antes de continuar con el siguiente paso."),
    "working": ("Working; no action needed.", "Estoy trabajando; no necesito nada de ti."),
    "unavailable": ("The service is unavailable. Work is preserved; automatic attempts are paused. Reply 'retry' to resume.",
                    "El servicio no está disponible. Conservé el trabajo y pausé los intentos automáticos. Responde 'retry' para retomar."),
}


def operational(kind, language="English"):
    return OPERATIONAL[kind][1 if language.casefold() == "spanish" else 0]


def translate(message, language):
    if language.casefold() == "english":
        return message
    if language.casefold() == "spanish":
        if " · " in message:
            label, phase = message.split(" · ", 1)
            if label in SPANISH:
                return f"{SPANISH[label]} · {phase}"
        return SPANISH.get(message)
    return None
