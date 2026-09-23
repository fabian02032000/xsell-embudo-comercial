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

## Email Marketing (`email-marketing.html`)

Página aparte (con inicio de sesión) para el equipo comercial, con 3 pestañas:

- **📇 Correos Insight**: datos reales de HubSpot sobre los correos de prospección en frío que Ingrid envía uno por uno (enviados, tasa de apertura, clics, respuestas, y el detalle de cada correo). Nadie tiene que tipificar nada a mano.
- **📣 Email Marketing (Pauta)**: la "audiencia tibia" — contactos que llegaron por formulario/pauta y están en Estadio del Lead = Consolidado (el único estadio incluido; los demás, como Alto Nivel/Semilla/En Crecimiento, quedan afuera). Se muestran ordenados de más a menos urgente: la Urgencia no filtra a quién se le envía, pero sí decide la estrategia de envío (qué tan pronto y con qué contenido).
- **🔄 Email MKT (clientes antiguos)**: negocios "Descartados" en HubSpot, para reenganche manual (esto sigue funcionando igual que antes, con Firebase).

Las primeras dos pestañas se llenan solas cada 10 minutos, junto con el resto del embudo (mismo `data/funnel.json`, mismo robot).

**Importante:** para que la pestaña "Correos Insight" funcione, el token de HubSpot de este repositorio (secreto `HUBSPOT_TOKEN`) necesita además uno de estos permisos: `crm.objects.emails.read`, `crm.schemas.emails.read` o `sales-email-read` (en HubSpot: Configuración → Cuenta y facturación → Aplicaciones anteriores → **`MCP-HUBSPOT`** → pestaña "Autenticación" → "Agregar permiso nuevo" → buscar "email" → elegir uno de esos tres → Actualizar). **Ojo:** la app que usa este repositorio es específicamente **`MCP-HUBSPOT`**, no `mcp_claude` ni `xsell-linkedin-github-actions` (hay 3 apps parecidas en esa cuenta de HubSpot; se confirmó cuál es la correcta con una prueba directa contra la API, no solo mirando el nombre). Si falta el permiso, la pestaña muestra "Aún no se ha ejecutado la primera actualización de este dato" pero el resto del dashboard sigue funcionando normal.

## Si algo se ve mal

- **Las metas mensuales, a qué grupo (Comercial/MKT Pauta) pertenece cada "Canal" de HubSpot, el correo desde el que Ingrid manda sus correos insight, o qué Estadios entran en la audiencia tibia**: se edita en `config/mapping.json`. No hace falta tocar código, solo pídele a Claude que lo ajuste.
- **El robot dejó de actualizar**: revisa la pestaña "Actions" en GitHub, ahí se ve si hubo un error (por ejemplo, si la llave de HubSpot venció).
- **La llave de HubSpot venció o se borró**: hay que crear una nueva "Clave de servicio" en HubSpot (Configuración → Desarrollo → Claves → Claves de servicio) con permisos de lectura sobre Contacts, Deals y Emails, y actualizar el secreto `HUBSPOT_TOKEN` en este repositorio (Settings → Secrets and variables → Actions).

## Archivos

- `index.html` — el dashboard del embudo.
- `email-marketing.html` — Correos Insight, Email Marketing (Pauta) y Email MKT (clientes antiguos).
- `scripts/fetch_data.py` — el script que trae y junta todos los datos (embudo, correos insight, audiencia tibia, clientes antiguos).
- `config/mapping.json` — reglas de mapeo (canal → fuente, etapa → nivel del embudo, metas, correo insight, audiencia tibia).
- `data/funnel.json` — los datos ya procesados (se genera solo).
- `.github/workflows/update.yml` — la automatización que corre cada 10 minutos.
