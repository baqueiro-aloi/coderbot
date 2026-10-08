## 1. Seguridad transversal y preservación inmediata

- [x] 1.1 Añadir regresiones de token enviado a hostname ajeno, redirects cross-host, destinos privados y descargas excesivas; implementar helper de descarga segura y conectar clientes GitHub/Jira/Google.
- [x] 1.2 Implementar registro dinámico y sanitización compartida de secretos/enlaces; probar texto de output, excepciones y valores adquiridos durante tarea.
- [ ] 1.3 Conectar sanitización antes de logs, check outputs, checkpoints, feedback, conversation, inbox y reportes; comprobar todos sinks con secretos sintéticos.
- [ ] 1.4 Proteger preparación/publicación de attachments textuales y media; impedir que contenido sensible se declare seguro únicamente por archivo válido.
- [x] 1.5 Retirar transcript crudo de commit de archivado y generar solo resumen permitido si corresponde; preservar historial previo sin reescribir Git.
- [x] 1.6 Desactivar tracing sensible AWS/Azure y reemplazar clone con token en URL por autenticación privada; probar scripts con credenciales sintéticas sin filtración.
- [x] 1.7 Sustituir limpieza destructiva de planning por atribución comprobable, backup y aislamiento; probar ediciones humanas concurrentes y branch ajena.
- [x] 1.8 Rehacer HOLD para guardar solo paths atribuibles, preservar untracked/secretos ajenos y reportar commit fallido sin «todo committed».

## 2. Contratos de evidencia y overrides

- [x] 2.1 Versionar contrato Check y resultados con tipo, requisitos/scenarios, dependencias externas, configuración y vigencia; añadir lectura conservadora de v1.
- [x] 2.2 Corregir adapters unittest/Node/JUnit/Playwright/JSON para detectar cero tests, skips y payloads contradictorios; distinguir build/lint de ejecución de tests.
- [x] 2.3 Añadir modelo de excepción con mensaje/autor original, alcance semántico, ids exactos, razón y estado de aplicabilidad.
- [ ] 2.4 Eliminar waiver por substring y clasificar mensaje completo en canales normal/lateral/legacy; probar negaciones, preguntas y decisiones condicionadas.
- [x] 2.5 Conectar opción «continuar sin key» al controlador: omitir solo checks dependientes, ejecutar alternativas y avanzar sin ampliar consentimiento.
- [ ] 2.6 Persistir excepción durante reinicios, HOLD/CONTINUE y cambio de sesión; revisar solo cambios materiales sin repetir solicitud de key para mismo alcance.
- [ ] 2.7 Aplicar excepciones exactas en gates/reportes y migrar waivers antiguos sin prefijos amplios o consentimiento inventado.
- [ ] 2.8 Publicar resultados y omisiones explícitas en conversación y sección bot-owned de PR, preservando edición humana.

## 3. Investigación obligatoria y recepción privada

- [x] 3.1 Implementar inventario versionado de integraciones, contratos, fuentes consultadas, versiones efectivas e incertidumbres materiales.
- [ ] 3.2 Conectar investigación a exploración/propuesta/aprobación: comprobar referencias y resolver información indispensable antes de acreditar compatibilidad.
- [x] 3.3 Actualizar prompts/skill/resumes para documentación por versión, contratos internos reales y contradicciones; eliminar equivalencia entre permisos locales, IAM y gasto.
- [x] 3.4 Detectar requisitos de credenciales/budget temprano y generar opciones completas de compartir, continuar sin key o pausar.
- [x] 3.5 Implementar almacén privado de handles con permisos, TTL, inyección a proceso autorizado, limpieza y recuperación; mantener plaintext fuera de contexto del modelo.
- [x] 3.6 Investigar documentación oficial actual y protocolo de PrivateBin, seleccionar cliente/dependencia mantenida compatible, fijar versión y añadir vectores de descifrado; rechazar protocolos/instancias no soportadas explícitamente.
- [x] 3.7 Conectar recepción de enlace seguro/referencia provisionada antes de persistencia de canales; validar host/DNS/redirect/tamaño/timeout y evitar unfurls automáticos.
- [x] 3.8 Probar expiración, enlace consumido, crash antes/después de persistencia privada y reenvío seguro sin perder tarea ni repetir resolución ciegamente.

## 4. Pruebas de contratos, cobertura y revisión

- [ ] 4.1 Definir contrato de validación del target con matriz de capacidades/rutas/auth/parámetros y trazabilidad de fixtures a fuente real.
- [ ] 4.2 Añadir regresiones estrictas de auth duplicada, API incompatible, payload interno distinto y parámetros descartados; probar SDK/proxy efectivos y aislamiento concurrente donde aplique.
- [ ] 4.3 Implementar ejecución controlada de smoke upstream con datos sintéticos, timeout/recursos y autorización de gasto; no confundir auth/listado con inferencia/tools/streaming.
- [ ] 4.4 Conectar inventario de requisitos/scenarios y coverage al controlador, enlazando receipts reales o excepciones aplicables; bloquear afirmaciones sin evidencia.
- [ ] 4.5 Registrar revisión independiente con sesión, snapshot, findings y resoluciones verificables en ambos runners; rechazar autoafirmación sin recibo.
- [x] 4.6 Corregir Newman para runner común, resultado estructurado contrastado con exit y reporte fallido etiquetado diagnóstico; probar timeout y reporte sobreescrito.
- [x] 4.7 Fortalecer manifests/reutilización de media con run, selección y paths exactos; impedir aceptación por basename o archivo no vacío sin procedencia.

## 5. Cache y checkpoints

- [x] 5.1 Incorporar configuración efectiva relevante del proceso/harness, env/secret por HMAC y versiones instaladas a identidad de checks, sin persistir valores.
- [x] 5.2 Añadir vigencia de evidencia remota y revalidación antes de promoción; probar upstream mutable con código intacto.
- [ ] 5.3 Invalidar resultados/bloqueos dependientes al provisionar key, corregir permiso o cambiar endpoint/SDK; preservar resultados no afectados.
- [ ] 5.4 Extender identidad/replay de checkpoints y handoffs con revisiones externas, incertidumbres y excepciones; probar recuperación sin repetir bloqueo resuelto.
- [ ] 5.5 Migrar receipts históricos sin procedencia a evidencia no verificada preservando historial y tareas, con tests de compatibilidad.

## 6. Clientes API y ownership remoto

- [ ] 6.1 Validar payload mínimo GitHub/Jira/Docs/Slack/Drive y distinguir invalid/unknown de vacío; probar colecciones ausentes y tipos malformados.
- [ ] 6.2 Paginar comentarios y recursos anidados; detectar cursores repetidos/ausentes y limitar ciclos sin afirmar lectura completa.
- [ ] 6.3 Verificar claim/ownership y mutaciones pertinentes mediante lectura fresca; eliminar fallback de snapshot viejo como confirmación.
- [x] 6.4 Clasificar HTTP 400 Docs por causa real; probar revisión obsoleta frente a request inválido.
- [ ] 6.5 Reconciliar creación/comentarios mutantes antes de retry ambiguo, con marcadores/receipts y límites; probar efecto aplicado con respuesta perdida.
- [ ] 6.6 Exponer adjuntos requeridos no descargados y errores sanitizados por categoría, sin asumir contexto irrelevante.

## 7. Merge, operación y release

- [x] 7.1 Registrar SHA remoto presentado para revisión, invalidar aprobación ante push externo y aplicar merge con --match-head-commit; cubrir race y force de threads sin bypass de SHA.
- [ ] 7.2 Separar estados implementado/local/upstream/desplegado/postdespliegue en reportes y documentación, incluidas excepciones.
- [ ] 7.3 Extender rollout local/AWS/Azure con imagen digest/SHA, versiones/configuración seguras y probes de readiness/smoke; no acreditar función por systemctl/heartbeat.
- [ ] 7.4 Verificar reconstrucción/recreación por cambios de imagen/env, recuperación de estado y rollback preservando target; pruebas aisladas sin despliegue real.
- [ ] 7.5 Corregir contradicciones restantes de autonomía/review/repair: permisos remotos, procesos ajenos y alcance requieren autorización concreta.

## 8. Regresiones, documentación y validación final

- [ ] 8.1 Añadir escenarios de presión de ISSUES.md y sweep para ambos runners/canales, incluidos override sin key, negación, fuga, contrato asumido, cache viejo y readiness falsa.
- [ ] 8.2 Añadir tests de integración FSM que ejerciten gates y wiring reales, no solamente funciones aisladas o respuestas sintéticas permisivas.
- [ ] 8.3 Documentar schemas/migración, configuración del receptor privado, presupuesto, TTL, excepciones, limitaciones del chat y operación/rollback.
- [ ] 8.4 Ejecutar suite Python completa, tests JavaScript/runtime y validación OpenSpec strict; registrar resultados reales y corregir regresiones sin reducir alcance.
- [ ] 8.5 Obtener revisión independiente del cambio completo y revalidar fixes con evidencia trazable.
- [ ] 8.6 Entregar implementación y checklist de piloto autorizado con integración real y override sin key; declarar pendientes externos honestamente sin desplegar ni gastar automáticamente.
