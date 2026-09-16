#!/usr/bin/env python3
"""
Trae los datos del embudo comercial de Xsell:
  - Contactos y Negocios (deals) desde HubSpot
  - Prospectos de LinkedIn (método PACS) desde el repo xsell-linkedin en GitHub

Junta todo y lo agrupa por DÍA y por fuente (Comercial / MKT Pauta / LinkedIn PACS).
El dashboard arma los totales por mes o por cualquier rango de fechas sumando esos
días, así que aquí no hace falta pensar en meses: solo en días.

También arma la lista de "clientes antiguos" (negocios Descartados en HubSpot) que
usa la pestaña de Email Marketing para las campañas de reenganche (Email MKT).

Este script lo corre automáticamente un GitHub Action cada 10 minutos.
No hace falta tocarlo para cambiar metas o reglas de mapeo: eso vive en config/mapping.json.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime, timezone

HUBSPOT_TOKEN = os.environ.get("HUBSPOT_TOKEN", "").strip()
HUBSPOT_BASE = "https://api.hubapi.com"
PACS_URL = "https://raw.githubusercontent.com/fabian02032000/xsell-linkedin/main/data/prospectos.json"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config", "mapping.json")
OUTPUT_PATH = os.path.join(ROOT, "data", "funnel.json")

STAGE_NAMES = {
    "1275439753": "Prospectos Contactados",
    "appointmentscheduled": "Reunión Agendadas",
    "qualifiedtobuy": "Propuesta en elaboración",
    "decisionmakerboughtin": "Propuesta Enviada/en revisión",
    "contractsent": "Propuesta aceptada",
    "closedwon": "En implementación",
    "44cdeaeb-93ef-4f46-a125-d47bfb1a7694": "Implementada",
    "closedlost": "Descartada",
    "73fb3ceb-7619-4436-8e1a-7ed0d2d4e65a": "Stand By",
    "1194313252": "Requerimientos Adicionales",
}

FUENTES = ["Comercial", "MKT Pauta", "LinkedIn PACS"]
NIVELES = ["contactos", "reuniones", "propuestas", "ventas"]
NIVEL_LABELS = ["Contactos", "Reuniones Agendadas", "Propuestas Enviadas", "Ventas Cerradas"]
FUERA_DEL_EMBUDO = "Fuera del embudo"
NIVEL_ORDEN = {etiqueta: i for i, etiqueta in enumerate(NIVEL_LABELS)}
NIVEL_ORDEN[FUERA_DEL_EMBUDO] = len(NIVEL_LABELS)


def log(msg):
    print(f"[fetch_data] {msg}", file=sys.stderr)


def http_get_json(url, headers=None, retries=3):
    headers = headers or {}
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            last_err = f"HTTP {e.code} on {url}: {body[:300]}"
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__} on {url}: {e}"
        log(f"intento {attempt}/{retries} falló -> {last_err}")
        time.sleep(2 * attempt)
    raise RuntimeError(last_err)


def hubspot_paginate(path, properties, extra_params=""):
    """Pagina un endpoint de HubSpot v3 y devuelve la lista completa de 'results'."""
    if not HUBSPOT_TOKEN:
        raise RuntimeError("Falta la variable de entorno HUBSPOT_TOKEN")
    headers = {"Authorization": f"Bearer {HUBSPOT_TOKEN}"}
    props = ",".join(properties)
    url = f"{HUBSPOT_BASE}{path}?limit=100&properties={props}{extra_params}"
    results = []
    while url:
        data = http_get_json(url, headers=headers)
        results.extend(data.get("results", []))
        paging = data.get("paging", {}).get("next", {}).get("link")
        url = paging
    return results


def dia_key(iso_date_str):
    """'2026-09-05T12:00:00Z' -> '2026-09-05'. Devuelve None si no se puede leer."""
    if not iso_date_str:
        return None
    try:
        return iso_date_str[:10]
    except Exception:  # noqa: BLE001
        return None


def canal_de_contacto(cprops):
    """
    De qué canal vino el contacto, para clasificarlo en Comercial / MKT Pauta / etc.

    Normalmente viene del campo "canal" (lo llena el equipo a mano). Pero los leads
    que entran solos por el formulario pagado de Facebook/Meta muchas veces no
    tienen ese campo lleno, así que si HubSpot registró que llegaron por publicidad
    paga de Facebook (hs_analytics_source = PAID_SOCIAL + Facebook), los tratamos
    igual que si dijeran canal="Facebook" (que ya mapea a "MKT Pauta").
    """
    canal = cprops.get("canal")
    if canal:
        return canal
    origen_pagado_facebook = (
        cprops.get("hs_analytics_source") == "PAID_SOCIAL"
        and cprops.get("hs_analytics_source_data_1") == "Facebook"
    )
    if origen_pagado_facebook:
        return "Facebook"
    return None


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_hubspot_contacts():
    log("descargando contactos de HubSpot...")
    contacts = hubspot_paginate(
        "/crm/v3/objects/contacts",
        [
            "canal", "createdate", "firstname", "lastname", "email",
            "hs_analytics_source", "hs_analytics_source_data_1",
        ],
    )
    log(f"  {len(contacts)} contactos descargados")
    return contacts


def fetch_hubspot_deals():
    log("descargando negocios (deals) de HubSpot...")
    deals = hubspot_paginate(
        "/crm/v3/objects/deals",
        ["dealname", "dealstage", "pipeline", "createdate", "closedate", "amount"],
        extra_params="&associations=contacts",
    )
    log(f"  {len(deals)} negocios descargados")
    return deals


def fetch_pacs_prospectos():
    log("descargando prospectos de LinkedIn PACS...")
    try:
        data = http_get_json(PACS_URL)
        prospectos = data.get("prospectos", [])
        log(f"  {len(prospectos)} prospectos PACS descargados")
        return prospectos
    except Exception as e:  # noqa: BLE001
        log(f"  no se pudo leer el repo de LinkedIn PACS ({e}); sigo sin esos datos")
        return []


def build_dataset():
    config = load_config()
    canal_a_fuente = config["canal_a_fuente"]
    fuente_default = config["fuente_por_defecto"]
    etapa_hs_a_nivel = config["etapa_hubspot_a_nivel"]
    etapa_pacs_a_nivel = config["etapa_pacs_a_nivel"]
    metas_default = config["metas_mensuales_default"]

    contacts = fetch_hubspot_contacts()
    deals = fetch_hubspot_deals()
    pacs = fetch_pacs_prospectos()

    contact_by_id = {c["id"]: c for c in contacts}

    # día -> fuente -> nivel -> contador
    counts = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    # día -> lista de filas de detalle (para la tabla de abajo)
    detalle = defaultdict(list)
    # todos los días que aparecen en los datos
    dias_vistos = set()
    # negocios "Descartados" (closedlost) -> insumo para Email MKT (clientes antiguos)
    clientes_antiguos = []

    # --- Contactos / Leads: uno por contacto, según su día de creación ---
    for c in contacts:
        props = c.get("properties", {})
        canal = canal_de_contacto(props)
        fuente = canal_a_fuente.get(canal, fuente_default)
        dia = dia_key(props.get("createdate"))
        if not dia:
            continue
        dias_vistos.add(dia)
        counts[dia][fuente]["contactos"] += 1

    # --- Reuniones / Propuestas / Ventas: según el negocio y su etapa actual ---
    for d in deals:
        props = d.get("properties", {})
        dealstage = props.get("dealstage")
        dia = dia_key(props.get("createdate"))
        if not dia:
            continue
        dias_vistos.add(dia)

        assoc = d.get("associations", {}).get("contacts", {}).get("results", [])
        canal = None
        contacto_nombre = None
        contacto_email = None
        if assoc:
            contact = contact_by_id.get(assoc[0].get("id"))
            if contact:
                cprops = contact.get("properties", {})
                canal = canal_de_contacto(cprops)
                contacto_nombre = " ".join(
                    filter(None, [cprops.get("firstname"), cprops.get("lastname")])
                ) or cprops.get("email")
                contacto_email = cprops.get("email")
        fuente = canal_a_fuente.get(canal, fuente_default)

        nivel = etapa_hs_a_nivel.get(dealstage)
        if nivel is not None:
            for i in range(1, nivel + 1):  # 1=reuniones,2=propuestas,3=ventas
                counts[dia][fuente][NIVELES[i]] += 1

        detalle[dia].append(
            {
                "fecha": dia,
                "fuente": fuente,
                "contacto": contacto_nombre or "(sin contacto)",
                "negocio": props.get("dealname") or "(sin nombre de negocio)",
                "etapa": STAGE_NAMES.get(dealstage, dealstage or "Sin etapa"),
                "nivel": NIVEL_LABELS[nivel] if nivel is not None else FUERA_DEL_EMBUDO,
                "origen": "HubSpot",
            }
        )

        # "Descartada" = negocio que no siguió adelante; insumo para reenganche
        # por email marketing (no son clientes activos, por eso "clientes antiguos").
        if dealstage == "closedlost":
            clientes_antiguos.append(
                {
                    "deal_id": d.get("id"),
                    "negocio": props.get("dealname") or "(sin nombre de negocio)",
                    "contacto": contacto_nombre or "(sin contacto)",
                    "email": contacto_email or "",
                }
            )

    # --- LinkedIn PACS: cada prospecto cuenta como Contacto, y avanza según su etapa ---
    for p in pacs:
        etapa = p.get("etapa", "Identificado")
        dia = dia_key(p.get("actualizado")) or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dias_vistos.add(dia)
        fuente = "LinkedIn PACS"
        nivel = etapa_pacs_a_nivel.get(etapa, 0)
        counts[dia][fuente]["contactos"] += 1
        for i in range(1, nivel + 1):
            counts[dia][fuente][NIVELES[i]] += 1
        detalle[dia].append(
            {
                "fecha": dia,
                "fuente": fuente,
                "contacto": p.get("nombre", "(sin nombre)"),
                "negocio": None,
                "etapa": etapa,
                "nivel": NIVEL_LABELS[nivel] if nivel < len(NIVEL_LABELS) else FUERA_DEL_EMBUDO,
                "origen": "LinkedIn PACS",
            }
        )

    # Asegura que el día de hoy siempre aparezca aunque no tenga datos todavía
    dias_vistos.add(datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    dias_out = {}
    for dia in sorted(dias_vistos):
        fuentes_out = {}
        total = {"contactos": 0, "reuniones": 0, "propuestas": 0, "ventas": 0}
        for fuente in FUENTES:
            vals = counts.get(dia, {}).get(fuente, {})
            fila = {n: vals.get(n, 0) for n in NIVELES}
            fuentes_out[fuente] = fila
            for n in NIVELES:
                total[n] += fila[n]
        dias_out[dia] = {
            "fuentes": fuentes_out,
            "total": total,
            "detalle": sorted(detalle.get(dia, []), key=lambda r: (NIVEL_ORDEN[r["nivel"]], r["fuente"])),
        }

    return {
        "generado": datetime.now(timezone.utc).isoformat(),
        "dias": dias_out,
        "metas_mensuales_default": metas_default,
        "clientes_antiguos": clientes_antiguos,
    }


def main():
    dataset = build_dataset()
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
    log(f"listo -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
