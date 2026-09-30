"""Static task language copy avoids programming sessions for boilerplate."""
SPANISH = {
    "Exploration": "Exploración", "Proposal": "Propuesta", "Implementation": "Implementación",
    "Verification": "Verificación", "Archiving": "Archivado", "Approval": "Aprobación",
    "PR ready for review": "PR listo para revisión", "PR updated": "PR actualizado",
    "Exploration is complete; I'm preparing the OpenSpec proposal.": "La exploración terminó; estoy preparando la propuesta OpenSpec.",
    "Proposal approved; implementation is starting.": "Propuesta aprobada; comienza la implementación.",
    "Implementation is complete; I'm running checks and review.": "La implementación terminó; estoy ejecutando checks y revisión.",
    "Final checks passed; I'm archiving the change.": "Los checks finales pasaron; estoy archivando el cambio.",
    "Verification passed; running internal review": "La verificación pasó; ejecutando revisión interna",
}


def translate(message, language):
    if language.casefold() == "english":
        return message
    if language.casefold() == "spanish":
        return SPANISH.get(message)
    return None
