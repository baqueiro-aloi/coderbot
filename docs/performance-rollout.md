# Rollout de Coderbot

## Alcance

Se despliega exclusivamente Coderbot. La tarea de modificar el harness PICA se
retiró por decisión del usuario. Se utilizan las capacidades existentes del destino;
no se cambiaron sus scripts, configuración, tests ni código durante el rollout.

## Release activado

- Código: release `performance-f2f9008`, separado del checkout original de app.
- Imagen validada: `codebot-performance-staging:dfb1375`.
- Backup privado: `/home/azureuser/codebot/rollout-backups/20260930T234904Z`.
- Se conservaron el directorio de datos original y todos los mounts resueltos,
  incluyendo seeds Claude/npm del usuario azureuser y el socket Docker.
- Estado anterior y después del arranque: `E2E`, rama
  `codebot-rd8s-configuracion-modelo-esfuerzo-pica`, sesión
  `ses_f11b3f84bffePj1lh65w7JRQAC`.
- Coderbot arrancó saludable y comenzó checks deterministas. El store conservó
  los resultados terminados y distinguió los checks interrumpidos por recreación.
- El checkout original de Coderbot conserva todos sus cambios previos sin commit.

## Recuperación

`scripts/rollout_performance.py` captura metadata privada del contenedor, hace
backup SQLite consistente tras detener el intento y reemplaza solo el mount /app.
La imagen anterior queda etiquetada para rollback. La configuración de rollback
debe conservar los mounts del contenedor inspeccionado; no expandir `~` bajo sudo,
que resolvería seeds como /root en vez de /home/azureuser.

No restaurar un backup de estado viejo sobre una tarea que ya avanzó. Primero
detener y limpiar el intento, conservar el cursor/store actual y elegir una imagen
compatible con esos datos aditivos. Trust-total se mantiene durante rollback;
una imagen antigua sin ese comportamiento solo se utiliza con el plugin gestionado
de confianza total correspondiente.
