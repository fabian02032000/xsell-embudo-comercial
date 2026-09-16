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

## Si algo se ve mal

- **Las metas mensuales, o a qué grupo (Comercial/MKT Pauta) pertenece cada "Canal" de HubSpot**: se edita en `config/mapping.json`. No hace falta tocar código, solo pídele a Claude que lo ajuste.
- **El robot dejó de actualizar**: revisa la pestaña "Actions" en GitHub, ahí se ve si hubo un error (por ejemplo, si la llave de HubSpot venció).
- **La llave de HubSpot venció o se borró**: hay que crear una nueva "Clave de servicio" en HubSpot (Configuración → Desarrollo → Claves → Claves de servicio) con permisos de lectura sobre Contacts y Deals, y actualizar el secreto `HUBSPOT_TOKEN` en este repositorio (Settings → Secrets and variables → Actions).

## Archivos

- `index.html` — el dashboard.
- `scripts/fetch_data.py` — el script que trae y junta los datos.
- `config/mapping.json` — reglas de mapeo (canal → fuente, etapa → nivel del embudo, metas).
- `data/funnel.json` — los datos ya procesados (se genera solo).
- `.github/workflows/update.yml` — la automatización que corre cada 10 minutos.
