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
    "content_filtered": (
        "The provider's content filter blocked this attempt. I stopped automatic retries and preserved the work. Please reformulate your text and send it again; I will not retry the blocked message.",
        "El filtro de contenido del proveedor bloqueó este intento. Detuve los reintentos automáticos y conservé el trabajo. Cambia el texto y envíalo de nuevo; no volveré a procesar el mensaje bloqueado."),
    "received": ("Received your message; I will review it before the next step.",
                 "Recibí tu mensaje; lo revisaré antes de continuar con el siguiente paso."),
    "working": ("Working; no action needed.", "Estoy trabajando; no necesito nada de ti."),
    "unavailable": ("The service is unavailable. Work is preserved; automatic attempts are paused. Reply 'retry' to resume.",
                    "El servicio no está disponible. Conservé el trabajo y pausé los intentos automáticos. Responde 'retry' para retomar."),
    "credential_ask": (
        "To test against {service} I need the credential {env} ({purpose}). How do you want to proceed?\n"
        "1. Send it through a secure one-time link (I open a temporary page and send you its address) (Recommended)\n"
        "2. Continue without it: checks that need it are reported as skipped, not passed\n"
        "3. Pause here until you decide\n"
        "Never paste the value itself in this thread. Reply with 1, 2 or 3.",
        "Para probar contra {service} necesito la credencial {env} ({purpose}). ¿Cómo quieres seguir?\n"
        "1. Enviarla por un enlace seguro de un solo uso (abro una página temporal y te mando su dirección) (Recomendado)\n"
        "2. Continuar sin ella: los checks que la necesiten se reportan como omitidos, no como aprobados\n"
        "3. Pausar aquí hasta que decidas\n"
        "Nunca pegues el valor en este hilo. Responde 1, 2 o 3."),
    "credential_link": (
        "Open {url} , paste only the value of {env}, keep 'Burn after reading' checked and press Create. "
        "Then reply here with the link it gives you (it includes the key after '#'). "
        "I read it once, the paste is destroyed, and I close the page. The page closes by itself in {minutes} minutes.",
        "Abre {url} , pega solo el valor de {env}, deja marcado 'Burn after reading' y pulsa Create. "
        "Luego responde aquí con el enlace que te da (incluye la clave después de '#'). "
        "Lo leo una sola vez, el paste se destruye y cierro la página. La página se cierra sola en {minutes} minutos."),
    "credential_received": (
        "Received {env}. It is stored privately for {hours} hours and never written to the repository, logs or this thread. Continuing.",
        "Recibí {env}. Queda guardada en privado por {hours} horas y nunca se escribe en el repositorio, los logs ni este hilo. Continúo."),
    "credential_skipped": (
        "Continuing without {env}. Checks that need it will be reported as skipped, not as passed.",
        "Continúo sin {env}. Los checks que la necesiten se reportarán como omitidos, no como aprobados."),
    "credential_paused": (
        "Paused. Reply 1 when you want the secure link, or 2 to continue without {env}.",
        "En pausa. Responde 1 cuando quieras el enlace seguro, o 2 para continuar sin {env}."),
    "credential_failed": (
        "I could not use that link: {problem} Reply 1 for a new secure page, 2 to continue without {env}, or 3 to pause.",
        "No pude usar ese enlace: {problem} Responde 1 para una página segura nueva, 2 para continuar sin {env}, o 3 para pausar."),
    "credential_unavailable": (
        "I could not open the secure page: {reason} You can send a link from an allowed PrivateBin instance{allowed}, "
        "reply 2 to continue without {env}, or 3 to pause.",
        "No pude abrir la página segura: {reason} Puedes mandar un enlace de una instancia PrivateBin permitida{allowed}, "
        "responder 2 para continuar sin {env}, o 3 para pausar."),
    "credential_page_closed": (
        "The secure page for {env} closed without receiving it. Reply 1 for a new one, 2 to continue without it, or 3 to pause.",
        "La página segura para {env} se cerró sin recibirla. Responde 1 para una nueva, 2 para continuar sin ella, o 3 para pausar."),
    "credential_unexpected": (
        "I received a secure link but I was not waiting for a credential, so I did not open it. Nothing was stored.",
        "Recibí un enlace seguro pero no estaba esperando una credencial, así que no lo abrí. No guardé nada."),
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
