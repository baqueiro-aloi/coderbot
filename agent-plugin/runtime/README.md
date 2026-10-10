# Runtime gestionado

El puente usa el contrato HTTP de OpenCode 1.18.18 y Node 22+, sin imports
de módulos internos. La imagen preinstala `@opencode-ai/plugin@1.18.18`
y `playwright@1.58.2` con Chromium en `/opt/coderbot/browsers`.

Los plugins configurados explícitamente continúan cargándose; se deshabilitan
plugins predeterminados externos. Harnesses con otra versión Playwright deben
preparar su browser compatible una vez por fingerprint; no asumir compatibilidad
del ejecutable de browser entre versiones.
