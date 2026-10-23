# Incidencias y hotfixes: PICA · LiteLLM · Bedrock Mantle

**Fecha:** 8 de octubre de 2026. **Alcance:** integración y diagnóstico realizados en esta conversación.

Este resumen distingue cambios de código, verificaciones remotas y pendientes de operación. Que una prueba local pase no significa que se haya desplegado ni validado inferencia real en producción.

## Resumen de cambios

| PR | Cambio | Estado al redactar |
| --- | --- | --- |
| [#115](https://github.com/aloi-tech/processing-interface-claude-analytics/pull/115) | 13 modelos Mantle, proyecto ZDR obligatorio, catálogo y auditoría | Integrado |
| [#119](https://github.com/aloi-tech/processing-interface-claude-analytics/pull/119) | Hotfix de autenticación duplicada; correcciones de reintentos del catálogo | Integrado |
| [#120](https://github.com/aloi-tech/processing-interface-claude-analytics/pull/120) | Hotfix de APIs, prefijos y workspace por modelo; aislamiento del bridge | Integrado |
| [#121](https://github.com/aloi-tech/processing-interface-claude-analytics/pull/121) | Variable `USE_ONLY_ZDR` para filtrar por metadata | Abierto |

## 1. Integración inicial y políticas ZDR

### Catálogo y credenciales

- El archivo fuente era `~/repos/bedrock-mantle-test/result.txt`, no `results.txt`; contenía 13 modelos.
- Se agregaron aliases separados `bedrock-mantle/<id>-zdr` para conservar las rutas directas Azure/Anthropic.
- Las credenciales compatibles con OpenAI se copiaron a `.env` locales con nombres `BEDROCK_MANTLE_*`; no se incorporaron a Git ni a documentación.
- El renderer originalmente solo reconocía Azure/Anthropic. Se agregó Mantle como proveedor configurado, con validación de variables incompletas y exclusión de rutas sin credenciales.

### El nombre no demuestra ZDR

**Problema:** un sufijo `-zdr` no impone retención ni sirve como fuente confiable de política.

**Corrección:** metadata explícita en `model_info`: `zdr`, `data_retention`, `upstream_provider`, `model_vendor`, `project_id`, `display_name` y posteriormente `upstream_api`. Nombre técnico `-zdr`; nombre descriptivo `(ZDR)`.

Se hizo obligatorio el proyecto `proj_fgujjafpmoflsnxplnko`. El arranque rechaza otro proyecto o uno ausente. Consultas remotas confirmaron que está activo y configurado con `data_retention.mode=none`.

### Proveedor y política no eran equivalentes al adaptador

**Problema:** `custom_llm_provider=openai` identifica el adaptador de LiteLLM, no necesariamente el servicio que aloja el modelo. Los campos custom de `model_info` tampoco se copian automáticamente al spendlog.

**Corrección:** el hook toma metadata del deployment y guarda una copia por llamada en:

```text
LiteLLM_SpendLogs.metadata.spend_logs_metadata.pica_model_policy
```

La copia incluye proveedor, fabricante, proyecto, API y retención. Los campos nativos `model_group`, `model`, `model_id`, `api_base` y `custom_llm_provider` permanecen disponibles. No se requirió migración del schema.

### Metadata y headers manipulables por el caller

**Problema:** la solicitud podía intentar sobrescribir proyecto, autenticación o afirmaciones ZDR.

**Corrección:** el hook elimina esas afirmaciones y fija proyecto/auth a partir de configuración y deployment confiables. Se agregaron pruebas de headers con distintas capitalizaciones, metadata malformada y credenciales ausentes.

## 2. Hotfix: HTTP 401 presentado como «Please run /login»

**Síntoma:** Claude Code mostraba `Not logged in · Please run /login` aunque la key funcionaba en una prueba local.

**Causa confirmada:** el cliente OpenAI enviaba `Authorization: Bearer …`, y configuración/hook agregaban también `x-api-key`. Mantle rechaza ambos headers juntos:

```text
request must not include both 'authorization' and 'x-api-key' headers
```

**Verificación remota, sin generación:**

| Headers | Resultado |
| --- | --- |
| Solo `x-api-key` | HTTP 200 |
| Solo Bearer | HTTP 200 |
| Bearer + proyecto autorizado | HTTP 200 |
| Bearer + `x-api-key` | HTTP 401 |

**Hotfix:** [#119](https://github.com/aloi-tech/processing-interface-claude-analytics/pull/119), commit original `40fa022`: usar autenticación única y bloquear sobrescrituras. Después, #120 ajustó el tipo de autenticación por API: Bearer para OpenAI, `x-api-key` para Messages nativo.

**Falla de nuestras pruebas:** el upstream sintético aceptaba doble autenticación. Se cambió para rechazarla y se verificó el alias Mantle con Claude Code real en Docker.

**Límite:** otro HTTP 401 con `Invalid bearer token` no prueba esta misma causa. Revisar la key efectiva del proceso proxy, expiración, comillas literales y headers; verificarla solo en el backend no basta.

## 3. Hotfix: APIs incompatibles y prefijos incorrectos

**Síntoma:** HTTP 400 en Claude y GLM:

```text
The model '…' does not support the '/v1/responses' API
```

**Causa:** se asumió que todos los modelos eran compatibles con OpenAI/Responses. LiteLLM 1.96.2 dirige el bridge Messages→OpenAI hacia Responses por defecto. Además, usar `/v1` para todos ignoraba prefijos específicos.

**Hotfix:** [#120](https://github.com/aloi-tech/processing-interface-claude-analytics/pull/120), commit original `76dd3dd`, según fichas oficiales de AWS:

| Modelos configurados | Adaptador | Ruta upstream | Auth | Header de aislamiento |
| --- | --- | --- | --- | --- |
| Claude Opus 5/4.8/4.7/5.5, Sonnet 5, Haiku 4.5 | Anthropic | `/anthropic/v1/messages` | `x-api-key` | `anthropic-workspace-id` |
| GLM 5/4.7, Kimi K2.5/K2 Thinking, Devstral 2, DeepSeek V3.2 | OpenAI | `/v1/chat/completions` | Bearer | `OpenAI-Project` |
| Grok 4.3 | OpenAI | `/openai/v1/responses`; Chat Completions en `/openai/v1/chat/completions` | Bearer | `OpenAI-Project` |

- Se conservaron los IDs upstream con prefijo de fabricante.
- `mantle_api_routing.py` limita la selección del bridge por solicitud mediante `ContextVar`, sin cambiar el flag global de Azure/otros proveedores.
- Projects y Workspaces son el mismo recurso. Messages necesita el header de workspace; mandar únicamente `OpenAI-Project` no es equivalente.
- Aliases con deployments que mezclan APIs o proveedores se rechazan antes de invocar: evita que balanceo elija un backend incompatible.

**Falla de nuestras pruebas:** el fixture simulaba Responses para modelos que no lo soportan. Se sustituyó por validación de rutas específicas; ahora cubre los 13 modelos, streaming, tools y thinking, y rechaza APIs incorrectas.

## 4. Esfuerzo, thinking y retención

### LiteLLM descartaba esfuerzo de modelos desconocidos

**Síntoma detectado en pruebas:**

```text
LiteLLM descarto el esfuerzo solicitado antes del upstream; revisar ruta y drop_params
```

**Corrección:** declarar capacidades para IDs Claude con prefijo Mantle y extender `allowed_openai_params` con `reasoning_effort` en modelos chat-only. Se preservan parámetros existentes y se eliminan duplicados. El backend puede aceptar o rechazar esfuerzo explícitamente, sin descartarlo silenciosamente.

**Limitación por modelo:** Haiku 4.5 usa thinking con presupuesto; no asumir adaptive thinking ni `output_config.effort`. Las pruebas distinguen ese caso.

### Campos no soportados o incompatibles con ZDR

- Mantle Messages no soporta `output_config.format`: se rechaza explícitamente.
- Responses puede almacenar estado por defecto. En las rutas ZDR se fija `store=false` y se rechazan `store=true`/`background=true`.
- `store=false` por sí solo no garantiza ZDR: se mantiene obligatorio el proyecto con política `none`.
- No se relajó retención ni se cambió al proyecto default para evitar errores.

## 5. HTTP 403: permisos IAM insuficientes

**Verificación remota:** una consulta nativa `messages/count_tokens` llegó al workspace correcto pero devolvió HTTP 403 porque la key no tiene permiso:

```text
bedrock-mantle:CountTokens
```

**Estado:** identificado; no corregido en IAM. Poder listar/consultar modelos no demuestra autorización para `CountTokens` ni `CreateInference`.

No se modificaron políticas IAM. Validar con el operador permisos sobre el proyecto autorizado antes de declarar la integración lista para producción.

## 6. Catálogo: validación, privacidad y reintentos

### Respuestas malformadas y logs insuficientes

**Problemas de review:** catálogo sin tipado estricto, entradas malformadas que podían devolver 500, ausencia de logs útiles y riesgo de exponer secretos upstream.

**Correcciones:**

- Modelos Pydantic estrictos y firmas tipadas; campos permitidos explícitamente.
- Payload inválido devuelve 502 sanitizado; eliminación de duplicados y fallback de nombre.
- Logs estructurados distinguen timeout, transporte, status HTTP y payload inválido.
- No se registra cuerpo upstream, texto de excepción, URL con credenciales, keys ni headers.
- `GET /api/models` expone metadata segura; `/api/llm/models` es el catálogo usado por selección/autorización en PICA.

### Backoff ilimitado y reloj de pared

**Problemas:** reintento exponencial sin tope podía alcanzar décadas; `Date.now()` podía retrasarlo ante cambios de reloj. Timers falsos aceptaban rangos imposibles y fixtures usaban rutas absolutas.

**Hotfix dentro de #119:** commit `3a97dc0`:

- Tope **3600 segundos**, solicitado por el usuario.
- Jitter descendente, efectivo también al llegar al tope.
- Tiempo monotónico `performance.now()` y constantes nombradas.
- Timer falso valida rango real; pruebas de 40 fallos, reset tras éxito, cambios de scope, desmontaje y correcciones del reloj.
- Rutas relativas en fixtures E2E.

Validación registrada: 172 tests frontend, build TypeScript/Vite, ESLint y E2E de recuperación del catálogo pasaron.

## 7. Solo modelos registrados como ZDR

**Problema:** no existía una variable para mantener credenciales de todos los proveedores y publicar únicamente modelos con metadata ZDR.

**Implementación:** [#121](https://github.com/aloi-tech/processing-interface-claude-analytics/pull/121), commit `79999fa`:

```dotenv
USE_ONLY_ZDR=true
# También admite 1; sin variable/false/0 conserva comportamiento anterior.
```

- Configurar en backend y proxy.
- Filtra exclusivamente por booleano `model_info.zdr: true`; no por sufijo ni proveedor.
- Filtra renderer LiteLLM y ambos catálogos PICA.
- La UI cruza IDs autorizados de `/v1/models` con metadata `/model/info`.
- Modelos excluidos no quedan publicados en el proxy; llamadas directas fallan.
- Arranque falla si no quedan modelos o si defaults explícitos apuntan a modelos excluidos.
- No elimina credenciales ni cambia retención local.

37 tests pasaron, incluido proxy real y rechazo de modelos excluidos. Al redactar, el PR seguía abierto: no asumir despliegue.

## 8. Endurecimiento adicional y problemas del entorno de pruebas

- Configuración Mantle duplicada: se centralizó mediante anchor YAML `mantle_connection`.
- `api_base` en spendlog se compara con URLs exactas permitidas, no con `startswith`.
- Conteo de filas PostgreSQL se deriva del catálogo; ya no usa un `39` fijo.
- Fixtures comprueban ambos IDs de llamadas registradas, no solo el primero.
- Se verificó orden de arranque: instalar routing antes de importar `run_server`.
- Tests aíslan variables del entorno, validan missing/blank keys y limpian estado ante excepciones/concurrencia.
- El venv local tenía LiteLLM 1.96.0: se creó entorno temporal con la versión requerida 1.96.2, sin cambiar dependencias del proyecto.
- Prisma falló por autenticación de npm: se usó registry público y configuración temporal aislada.
- Prisma autoleía `.env` locales y reportó conflictos: sus comandos de test se ejecutan desde directorio temporal, sin modificar secretos locales.
- Se ajustaron expectativas de `api_base` porque LiteLLM normaliza slash final o registra la URL `/responses` completa.

## 9. Estado de validación y pendientes

### Verificado

- Consulta remota de proyecto activo y retención `none`.
- Matriz remota de autenticación, sin generación.
- Lookup de modelo con SDK OpenAI real y Bearer + proyecto.
- Alias Mantle con Claude Code real en Docker contra upstream local.
- Proxy LiteLLM real con validación por modelo, streaming/tools/thinking.
- PostgreSQL temporal con metadata histórica, incluyendo 39 llamadas Mantle y regresiones Anthropic.
- Aislamiento de routing concurrente y limpieza ante excepciones.

### Pendiente / no realizado

1. **Desplegar/reconstruir la imagen backend/proxy**: hooks y launcher cambiaron. Cambiar solo YAML no basta.
2. Recrear contenedores al cambiar `.env`: un simple restart no actualiza variables.
3. Revisar permisos IAM `CountTokens`/`CreateInference` sobre el proyecto.
4. Validar inferencia real, herramientas y reanudación en producción. No se hizo generación pagada.
5. Rotar credenciales visibles en capturas compartidas. No se realizó rotación.
6. Mantener pin de LiteLLM y regresiones al actualizar: el shim utiliza internals privados y debe sustituirse cuando exista extensión upstream soportada.
7. No confundir ZDR upstream con retención de archivos, conversaciones o logs locales de PICA.

## Fuentes oficiales

- [APIs y compatibilidad por modelo](https://docs.aws.amazon.com/bedrock/latest/userguide/models-api-compatibility.html)
- [Messages API](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-messages-api.html)
- [Chat Completions](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-chat-completions-mantle.html)
- [Responses API](https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-mantle.html)
- [Workspaces](https://docs.aws.amazon.com/bedrock/latest/userguide/workspaces.html)
- [Projects](https://docs.aws.amazon.com/bedrock/latest/userguide/projects.html)
- [Data retention](https://docs.aws.amazon.com/bedrock/latest/userguide/data-retention.html)
- [Claude Opus 4.8](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-4-8.md)
- [GLM 5](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-zai-glm-5.md)

Las fichas específicas del endpoint prevalecen sobre inferencias a partir del fabricante o tablas agregadas. Durante la auditoría, la ficha Mantle de Kimi K2 Thinking indicaba Chat Completions aunque la tabla agregada no lo marcaba.
