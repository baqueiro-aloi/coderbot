# Resultados de aceptación inicial

Comandos reproducibles:

```sh
venv/bin/python scripts/benchmark_runtime.py
python3 scripts/test_trusted_runtime.py
venv/bin/python -m unittest discover -s tests -t .
```

- Replay sintético del incidente: 6590 s de espera antigua; política residual
  de permiso con presupuesto de 10 s. Reducción modelada: 99,85% de esa espera.
- Runner real: una ejecución completa y reutilización al recuperar el mismo
  contenido/entorno; una grabación aunque la entrega se reintente.
- Fallo idéntico en baseline: gate pass con preexisting, sin reparar código viejo.
- Integración headless con proveedor HTTP local: read/write/bash externos para
  build/general/explore con restricciones heredadas deny, reanudación y dos
  arranques. Aprobada en OpenCode 1.18.18 Linux y 1.18.30 macOS.
- Suite completa inicial: 655 tests en 28,28 s; aprobada con un skip GNU stat
  específico de macOS. Las pruebas de cancelación verifican reutilización de
  un puerto abierto por un proceso nieto y cleanup ante timeout/shutdown.

El porcentaje modelado no mide throughput real de Azure ni demuestra 80% de
mejora del ciclo productivo completo. Esa medición requiere tareas comparables
en staging/producción separando esperas humanas, outages y calidad del resultado.
