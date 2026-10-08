## Purpose

Mantener credenciales y enlaces secretos fuera del contexto del modelo, historial público, reportes y repositorios durante su recepción y uso autorizado.

## ADDED Requirements

### Requirement: Recepción privada y ciclo de vida
El bot SHALL admitir referencias provisionadas y enlaces HTTPS de un solo uso en el canal existente mediante recepción confiable antes de persistir texto o enviarlo al modelo. SHALL tratar la URL completa como secreto, validar proveedor/host, redirects y destinos, y limitar tiempo/tamaño. SHALL inyectar valores solo al proceso autorizado con almacenamiento privado, expiración y limpieza definidos. SHALL preservar recuperación segura tras consumo del enlace sin prometer atomicidad entre servicios.

#### Scenario: Enlace consumido y crash
- **WHEN** ocurre un crash tras consumir un enlace
- **THEN** el bot recupera la referencia privada ya guardada o informa necesidad de reenvío sin repetir ciegamente ni registrar plaintext

#### Scenario: Destino inseguro
- **WHEN** un enlace apunta o redirige a destino no autorizado o red privada
- **THEN** no se resuelve ni se envía autenticación y se comunica rechazo sanitizado

### Requirement: Sanitización antes de persistencia y publicación
Keys, URLs secretas completas y plaintext SHALL quedar fuera de prompts, logs, SQLite general, transcripts, attachments, tickets, PRs y Git. Los scripts de boot no SHALL trazar tokens, secretos o URLs de clone autenticadas. El historial crudo del agente no SHALL incorporarse al commit de archivado. La sanitización SHALL operar antes de persistir/transportar y no depender solo de valores conocidos al inicio del proceso.

#### Scenario: Secreto en output
- **WHEN** output del agente o de una prueba incluye un secreto sintético registrado
- **THEN** las copias persistidas y publicadas no incluyen ese valor ni su enlace de acceso

### Requirement: Descargas autenticadas limitadas
Descargas SHALL usar destinos explícitamente permitidos para autenticación, HTTPS, límites de tamaño/tiempo y validación de redirects. La presencia de «github» dentro de una URL no SHALL autorizar enviar token GitHub. Adjuntos requeridos no descargados SHALL quedar visibles como contexto faltante.

#### Scenario: Dominio ajeno con github en path
- **WHEN** una imagen usa `https://attacker.example/github.png`
- **THEN** ningún token GitHub se envía al destino
