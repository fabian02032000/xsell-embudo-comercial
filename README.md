# Embudo Comercial · Xsell

Dashboard en tiempo real del embudo comercial de Xsell. Junta datos de:

- **HubSpot** (Comercial y MKT Pauta), según el campo "Canal" de cada contacto.
- **LinkedIn PACS**, leyendo directamente el repositorio [xsell-linkedin](https://github.com/fabian02032000/xsell-linkedin).

## Ver el dashboard

👉 https://fabian02032000.github.io/xsell-embudo-comercial/

Se actualiza solo, cada 10 minutos, sin que nadie tenga que hacer nada.

## ¿Cómo funciona?

1. Un robot (GitHub Action) corre cada 10 minutos.
2. Ese robot lee los contactos y negocios de HubSpot, y los prospectos del repo de LinkedIn.
3. Junta todo en un archivo (`data/funnel.json`).
4. La página web (`index.html`) lee ese archivo y lo muestra.

## Pestañas del dashboard (`index.html`)

- **📊 Embudo Comercial**: la vista de siempre — Comercial / MKT Pauta / LinkedIn PACS contra las metas mensuales, por mes o por rango de fechas.
- **🔺 Pipeline**: foto de ahora mismo (no por día) de todos los negocios: cuántos hay y cuánto valen en cada etapa, y el pipeline activo total (excluye los descartados).
- **🏷 Negocios**: la lista completa de negocios, con filtros por País y Tipo de Negocio. El País usa el campo real de HubSpot cuando está lleno; si no, se adivina del nombre del negocio (se marca con un `*`). El Tipo de Negocio (ATC, Perfilamiento de Leads, Agendamiento de Citas, Carritos Abandonados, Encuestas, Ventas, Otro) siempre se adivina del nombre — no hay ningún campo en HubSpot que ya traiga esa clasificación lista.
- **⚡ Actividades**: cuántos correos, notas y llamadas reales se registraron en HubSpot desde el 1 de enero de 2026. "Reuniones" y "WhatsApp" no se pueden mostrar todavía: Reuniones necesita que alguien vuelva a autorizar la conexión de HubSpot (permiso de lectura de Reuniones), y no existe ningún dato de WhatsApp disponible en esta cuenta de HubSpot.

### El caso especial de Canal="Whatsapp"

Antes de setiembre de 2026, que un contacto tuviera Canal="Whatsapp" siempre significaba que un vendedor le escribió por su cuenta (Comercial). Desde que empezó la campaña paga de WhatsApp por Meta (setiembre 2026), ese mismo valor de Canal también se usa — en el otro dashboard, el de la campaña — para marcar los leads que sí vienen de esa campaña. Para que ambos dashboards cuadren, aquí esos contactos (los creados desde `whatsapp_campana_meta.desde_fecha` en `config/mapping.json`) se cuentan como MKT Pauta en vez de Comercial, salvo que el nombre de su Negocio tenga alguna palabra de las de `excluir_dealname_keywords` (eso indica que en realidad es otra gestión de ventas, no un lead de la campaña).

## Email Marketing (`email-marketing.html`)

Página aparte (con inicio de sesión) para el equipo comercial, con 3 pestañas:

- **📇 Correos Insight**: datos reales de HubSpot sobre los correos de prospección en frío que Ingrid envía uno por uno (enviados, tasa de apertura, clics, respuestas, y el detalle de cada correo). Nadie tiene que tipificar nada a mano.
- **📣 Email Marketing (Pauta)**: la "audiencia tibia" — contactos que llegaron por formulario/pauta y están en Estadio del Lead = Consolidado (el único estadio incluido; los demás, como Alto Nivel/Semilla/En Crecimiento, quedan afuera). Se muestran ordenados de más a menos urgente: la Urgencia no filtra a quién se le envía, pero sí decide la estrategia de envío (qué tan pronto y con qué contenido).
- **🔄 Email MKT (clientes antiguos)**: negocios "Descartados" en HubSpot, para reenganche manual (esto sigue funcionando igual que antes, con Firebase).

Las primeras dos pestañas se llenan solas cada 10 minutos, junto con el resto del embudo (mismo `data/funnel.json`, mismo robot).

**Importante:** para que la pestaña "Correos Insight" funcione, el token de HubSpot de este repositorio (secreto `HUBSPOT_TOKEN`) necesita además uno de estos permisos: `crm.objects.emails.read`, `crm.schemas.emails.read` o `sales-email-read` (en HubSpot: Configuración → Cuenta y facturación → Aplicaciones anteriores → **`MCP-HUBSPOT`** → pestaña "Autenticación" → "Agregar permiso nuevo" → buscar "email" → elegir uno de esos tres → Actualizar). **Ojo:** la app que usa este repositorio es específicamente **`MCP-HUBSPOT`**, no `mcp_claude` ni `xsell-linkedin-github-actions` (hay 3 apps parecidas en esa cuenta de HubSpot; se confirmó cuál es la correcta con una prueba directa contra la API, no solo mirando el nombre). Si falta el permiso, la pestaña muestra "Aún no se ha ejecutado la primera actualización de este dato" pero el resto del dashboard sigue funcionando normal.

## Si algo se ve mal

- **Las metas mensuales, a qué grupo (Comercial/MKT Pauta) pertenece cada "Canal" de HubSpot, el correo desde el que Ingrid manda sus correos insight, qué Estadios entran en la audiencia tibia, desde cuándo cuenta la campaña de WhatsApp de Meta, o desde cuándo se cuentan las Actividades**: se edita en `config/mapping.json`. No hace falta tocar código, solo pídele a Claude que lo ajuste.
- **Quieres que "Reuniones" y "WhatsApp" también se muestren en Actividades**: para Reuniones, hay que volver a autorizar la conexión de HubSpot para que incluya el permiso de leer Reuniones. Para WhatsApp, esta cuenta de HubSpot no tiene ningún objeto que registre esas conversaciones, así que no hay de dónde traerlo todavía.
- **El robot dejó de actualizar**: revisa la pestaña "Actions" en GitHub, ahí se ve si hubo un error (por ejemplo, si la llave de HubSpot venció).
- **La llave de HubSpot venció o se borró**: hay que crear una nueva "Clave de servicio" en HubSpot (Configuración → Desarrollo → Claves → Claves de servicio) con permisos de lectura sobre Contacts, Deals y Emails, y actualizar el secreto `HUBSPOT_TOKEN` en este repositorio (Settings → Secrets and variables → Actions).

## Archivos

- `index.html` — el dashboard del embudo.
- `email-marketing.html` — Correos Insight, Email Marketing (Pauta) y Email MKT (clientes antiguos).
- `scripts/fetch_data.py` — el script que trae y junta todos los datos (embudo, correos insight, audiencia tibia, clientes antiguos).
- `config/mapping.json` — reglas de mapeo (canal → fuente, etapa → nivel del embudo, metas, correo insight, audiencia tibia).
- `data/funnel.json` — los datos ya procesados (se genera solo).
- `.github/workflows/update.yml` — la automatización que corre cada 10 minutos.
