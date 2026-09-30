# Harness contract v1

El archivo opcional `e2e/codebot-harness.json` declara `version: 1`, `checks`
(mismo contrato que `.codebot/checks.json`) y `preparation` con `inputs`,
`commands`, `probes`, `timeout`. Cada check declara suites/proveedores en argv,
cwd, recursos exclusivos, reporter y entradas relevantes. Nunca agregar flags
que el run.sh existente no soporte. Sin contrato se usa `./run.sh`.

Los outputs se declaran mediante `CODEBOT_ARTIFACT_MANIFEST`, un JSON por ejecución:
`version`, `run_id`, `snapshot`, `status`, `artifacts` (kind, path, test_id, hash).
Preparación separada verifica dependencias y browsers por fingerprint; los probes
deben fallar si una instalación está incompleta.

Los harnesses compartidos mantienen workers=1. Para incrementarlos primero
aislar propietarios de sesión, bases/workspaces, puertos, containers e imágenes.
Compartir nombres de proyecto Compose o carpetas de output no constituye aislamiento.

## Fixture PICA

`pica_harness.grouped` conserva un lock `pica:harness` entre los dos proveedores:
los puertos 8111/5177 y el workspace compartido requieren ejecución serial. La
prueba del scheduler abre procesos reales y comprueba que una segunda operación
con el mismo recurso espera a la primera. Una prueba de cleanup abre un puerto
en un nieto y verifica que puede reutilizarse después de cancelar el grupo.

Para habilitar workers de Playwright, cada worker debe recibir un workspace y
OUTPUT_PATH propios y metadata de owner escrita antes de hacer visible la sesión.
Para ejecutar proveedores simultáneamente deben recibir puertos y nombres de
imagen/containers propios. Hasta completar esos cambios, mantener `workers: 1`.
