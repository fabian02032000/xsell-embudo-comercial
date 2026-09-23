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

# --- Correos "insight" (prospección en frío de Ingrid, ver fetch_ingrid_emails_summary) ---
GENERIC_EMAIL_DOMAINS = {
    "gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "live.com",
    "icloud.com", "msn.com", "yahoo.es", "hotmail.es",
}
EMAIL_STATUS_LABELS = {
    "SENT": "Enviado",
    "BOUNCED": "Rebotado",
    "FAILED": "Fallido",
    "SCHEDULED": "Programado",
    "PROCESSING": "Procesando",
}
NIVEL_URGENCIA_LABELS = {"low": "Bajo", "medium": "Medio", "high": "Alto"}
EMAIL_PROPERTIES = [
    "hs_timestamp", "hs_email_subject", "hs_email_to_email", "hs_email_status",
    "hs_email_open_count", "hs_email_click_count", "hs_email_reply_count",
]


def log(msg):
    print(f"[fetch_data] {msg}", file=sys.stderr)


def chunked(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


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


def hubspot_post(path, body, retries=3):
    """POST autenticado a la API de HubSpot (para /search y /batch/read)."""
    if not HUBSPOT_TOKEN:
        raise RuntimeError("Falta la variable de entorno HUBSPOT_TOKEN")
    headers = {"Authorization": f"Bearer {HUBSPOT_TOKEN}", "Content-Type": "application/json"}
    data = json.dumps(body).encode("utf-8")
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(f"{HUBSPOT_BASE}{path}", data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            last_err = f"HTTP {e.code} on {path}: {err_body[:1200]}"
            if e.code in (401, 403):
                # Sin permiso: no tiene sentido reintentar, hay que avisar rápido.
                raise RuntimeError(last_err)
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__} on {path}: {e}"
        log(f"intento {attempt}/{retries} falló -> {last_err}")
        time.sleep(2 * attempt)
    raise RuntimeError(last_err)


def date_to_epoch_ms(date_str):
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def fetch_all_ingrid_emails(from_email, since_date_str):
    """Trae todos los correos (engagements de tipo Email) enviados desde
    from_email, desde since_date_str (paginado)."""
    emails = []
    after = None
    since_epoch = date_to_epoch_ms(since_date_str)
    while True:
        body = {
            "filterGroups": [
                {
                    "filters": [
                        {"propertyName": "hs_email_from_email", "operator": "EQ", "value": from_email},
                        {"propertyName": "hs_email_direction", "operator": "EQ", "value": "EMAIL"},
                        {"propertyName": "hs_timestamp", "operator": "GTE", "value": str(since_epoch)},
                    ]
                }
            ],
            "properties": EMAIL_PROPERTIES,
            "limit": 100,
            "sorts": [{"propertyName": "hs_timestamp", "direction": "DESCENDING"}],
        }
        if after:
            body["after"] = after
        data = hubspot_post("/crm/v3/objects/emails/search", body)
        emails.extend(data.get("results", []))
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return emails


def fetch_contact_by_email_map(email_ids):
    """Para cada correo (engagement), busca los contactos asociados y trae su
    nombre, empresa y rubro/industria. Un mismo correo puede tener más de un
    contacto asociado en HubSpot (por ejemplo, el remitente Ingrid además del
    destinatario real, sin un orden garantizado), así que se devuelve la
    LISTA completa de contactos por correo -- pick_matching_contact() es quien
    decide cuál es el destinatario real, comparando por su email. Best-effort:
    si algo falla, todos quedan sin contactos asociados en vez de romper el
    script completo."""
    contact_by_email_id = {eid: [] for eid in email_ids}
    if not email_ids:
        return contact_by_email_id

    email_to_contact_ids = {}
    for batch in chunked(email_ids, 100):
        body = {"inputs": [{"id": eid} for eid in batch]}
        resp = hubspot_post("/crm/v4/associations/emails/contacts/batch/read", body)
        for row in resp.get("results", []):
            from_id = row.get("from", {}).get("id")
            contact_ids = [t.get("toObjectId") for t in row.get("to", [])]
            if from_id and contact_ids:
                email_to_contact_ids[from_id] = contact_ids

    all_contact_ids = sorted({str(cid) for ids in email_to_contact_ids.values() for cid in ids})

    contact_info = {}
    contact_properties = ["firstname", "lastname", "email", "company", "rubro", "industry", "industria"]
    for batch in chunked(all_contact_ids, 100):
        body = {"inputs": [{"id": cid} for cid in batch], "properties": contact_properties}
        resp = hubspot_post("/crm/v3/objects/contacts/batch/read", body)
        for c in resp.get("results", []):
            contact_info[c["id"]] = c.get("properties", {})

    for eid, cids in email_to_contact_ids.items():
        contact_by_email_id[eid] = [contact_info[str(cid)] for cid in cids if str(cid) in contact_info]

    return contact_by_email_id


def pick_matching_contact(contact_props_list, to_email):
    """Entre los contactos asociados a un correo, elige el que de verdad es el
    destinatario (comparando el email). Sin esto, si HubSpot asocia también a
    Ingrid (la remitente) al mismo engagement, se corre el riesgo de mostrarla
    a ella como si fuera la destinataria."""
    if not contact_props_list:
        return None
    to_email_norm = (to_email or "").strip().lower()
    for props in contact_props_list:
        if to_email_norm and (props.get("email") or "").strip().lower() == to_email_norm:
            return props
    # Ninguno coincide por email (raro): se usa el primero, como antes.
    return contact_props_list[0]


def guess_company_from_domain(email_address):
    """Adivina un nombre de empresa a partir del dominio del correo, solo
    como referencia visual. Devuelve None si el dominio es de un proveedor
    genérico (Gmail, Hotmail, etc.)."""
    if not email_address or "@" not in email_address:
        return None
    domain = email_address.split("@", 1)[1].lower().strip()
    if domain in GENERIC_EMAIL_DOMAINS:
        return None
    base = domain.split(".")[0]
    return base.replace("-", " ").replace("_", " ").title()


def build_email_detail_row(email_obj, contact_props_list):
    props = email_obj.get("properties", {})
    contact_props = pick_matching_contact(contact_props_list, props.get("hs_email_to_email")) or {}

    full_name = " ".join(
        x for x in [contact_props.get("firstname"), contact_props.get("lastname")] if x
    ).strip()

    empresa = contact_props.get("company")
    empresa_adivinada = False
    if not empresa:
        empresa = guess_company_from_domain(props.get("hs_email_to_email"))
        empresa_adivinada = empresa is not None

    rubro = contact_props.get("rubro") or contact_props.get("industry") or contact_props.get("industria")

    timestamp = props.get("hs_timestamp")
    fecha, hora = None, None
    if timestamp:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        fecha = dt.date().isoformat()
        hora = dt.strftime("%H:%M")

    estado_raw = props.get("hs_email_status") or ""
    return {
        "id": email_obj.get("id"),
        "destinatario_email": props.get("hs_email_to_email") or "(sin correo)",
        "destinatario_nombre": full_name or None,
        "empresa": empresa,
        "empresa_adivinada": empresa_adivinada,
        "rubro": rubro,
        "asunto": props.get("hs_email_subject") or "(sin asunto)",
        "fecha": fecha,
        "hora": hora,
        "estado": EMAIL_STATUS_LABELS.get(estado_raw, estado_raw or "Sin dato"),
        "estado_raw": estado_raw,
        "aperturas": int(float(props.get("hs_email_open_count") or 0)),
        "clics": int(float(props.get("hs_email_click_count") or 0)),
        "respuestas": int(float(props.get("hs_email_reply_count") or 0)),
    }


def fetch_ingrid_emails_summary(email_cfg):
    """Arma el resumen + detalle de los correos 'insight' para la pestaña
    Correos Insight de email-marketing.html. Best-effort: si el token no
    tiene el permiso crm.objects.emails.read (o cualquier otra cosa falla),
    devuelve un resumen vacío con 'disponible': False en vez de romper todo
    el dashboard — así el resto de datos (embudo, clientes antiguos) se
    siguen actualizando igual."""
    from_email = email_cfg.get("remitente", "ingrid.mio@3eriza.com.pe")
    desde_fecha = email_cfg.get("desde_fecha", "2026-01-01")
    vacio = {
        "remitente": from_email,
        "desde_fecha": desde_fecha,
        "total_enviados": 0,
        "tasa_apertura": 0.0,
        "tasa_clics": 0.0,
        "tasa_respuestas": 0.0,
        "cobertura_rubro": 0.0,
        "detalle": [],
        "disponible": False,
    }
    if not HUBSPOT_TOKEN:
        return vacio
    try:
        log("descargando correos insight de Ingrid...")
        emails = fetch_all_ingrid_emails(from_email, desde_fecha)
        email_ids = [e["id"] for e in emails]
        contact_by_email_id = fetch_contact_by_email_map(email_ids)
        detalle = [build_email_detail_row(e, contact_by_email_id.get(e["id"], [])) for e in emails]
        detalle.sort(key=lambda r: (r["fecha"] or "", r["hora"] or ""), reverse=True)

        total = len(detalle)
        total_sent = sum(1 for r in detalle if r["estado_raw"] == "SENT")
        total_opened = sum(1 for r in detalle if r["aperturas"] > 0)
        total_clicked = sum(1 for r in detalle if r["clics"] > 0)
        total_replied = sum(1 for r in detalle if r["respuestas"] > 0)
        total_con_rubro = sum(1 for r in detalle if r["rubro"])

        def pct(n, d):
            return round(100 * n / d, 1) if d else 0.0

        log(f"  {total} correos de Ingrid, {total_sent} enviados, {total_opened} abiertos")
        return {
            "remitente": from_email,
            "desde_fecha": desde_fecha,
            "total_enviados": total_sent,
            "tasa_apertura": pct(total_opened, total_sent),
            "tasa_clics": pct(total_clicked, total_sent),
            "tasa_respuestas": pct(total_replied, total_sent),
            "cobertura_rubro": pct(total_con_rubro, total),
            "detalle": detalle,
            "disponible": True,
        }
    except Exception as e:  # noqa: BLE001
        log(f"AVISO: no se pudo traer los correos de Ingrid (¿falta el permiso crm.objects.emails.read del token?): {e}")
        vacio["error"] = str(e)[:500]
        return vacio


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
        [
            "dealname", "dealstage", "pipeline", "createdate", "closedate", "amount",
            # Campos que Ingrid tipifica a mano en el Negocio, usados para la
            # audiencia tibia de la pestaña Email Marketing (Pauta):
            "etapa_final", "hs_priority",
        ],
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
    # contact_id -> {deal_id, deal_name, createdate, estadio_lead, nivel_urgencia}
    # (del Negocio más reciente de cada contacto) -> insumo para audiencia tibia
    contact_lead_status = {}

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
            contact_id = assoc[0].get("id")
            contact = contact_by_id.get(contact_id)
            if contact:
                cprops = contact.get("properties", {})
                canal = canal_de_contacto(cprops)
                contacto_nombre = " ".join(
                    filter(None, [cprops.get("firstname"), cprops.get("lastname")])
                ) or cprops.get("email")
                contacto_email = cprops.get("email")

            # Guarda el Estadio del Lead / Nivel de Urgencia del negocio más
            # reciente de este contacto (insumo para la audiencia tibia).
            createdate = props.get("createdate") or ""
            previo = contact_lead_status.get(contact_id)
            if contact_id and (not previo or createdate > previo.get("createdate", "")):
                urgencia_raw = props.get("hs_priority")
                contact_lead_status[contact_id] = {
                    "deal_id": d.get("id"),
                    "deal_name": props.get("dealname"),
                    "createdate": createdate,
                    "estadio_lead": props.get("etapa_final") or None,
                    "nivel_urgencia": NIVEL_URGENCIA_LABELS.get((urgencia_raw or "").lower(), urgencia_raw) if urgencia_raw else None,
                }
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

    # --- Audiencia tibia: contactos de MKT Pauta que sí consideramos
    # potenciales para un reenvío por correo, según el Estadio del Lead
    # (ver comentario en config/mapping.json). El Nivel de Urgencia no se usa
    # para incluir/excluir, solo se muestra como referencia. ---
    audiencia_tibia_cfg = config.get("audiencia_tibia", {})
    excluir_estadios = set(audiencia_tibia_cfg.get("excluir_estadios", ["Semilla", "En Crecimiento"]))

    audiencia_tibia_detalle = []
    for c in contacts:
        props = c.get("properties", {})
        canal = canal_de_contacto(props)
        fuente = canal_a_fuente.get(canal, fuente_default)
        if fuente != "MKT Pauta":
            continue
        status = contact_lead_status.get(c["id"])
        estadio = status.get("estadio_lead") if status else None
        if not estadio or estadio in excluir_estadios:
            continue
        nombre = " ".join(
            filter(None, [props.get("firstname"), props.get("lastname")])
        ) or props.get("email") or "(sin nombre)"
        audiencia_tibia_detalle.append(
            {
                "nombre": nombre,
                "correo": props.get("email") or "",
                "empresa": status.get("deal_name") or "",
                "estadio_lead": estadio,
                "nivel_urgencia": status.get("nivel_urgencia"),
            }
        )
    audiencia_tibia_detalle.sort(key=lambda r: r["nombre"])

    # --- Correos insight (Ingrid) ---
    correos_insight = fetch_ingrid_emails_summary(config.get("email_insight", {}))

    return {
        "generado": datetime.now(timezone.utc).isoformat(),
        "dias": dias_out,
        "metas_mensuales_default": metas_default,
        "clientes_antiguos": clientes_antiguos,
        "correos_insight": correos_insight,
        "audiencia_tibia": {
            "excluir_estadios": sorted(excluir_estadios),
            "total": len(audiencia_tibia_detalle),
            "detalle": audiencia_tibia_detalle,
        },
    }


def main():
    dataset = build_dataset()
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
    log(f"listo -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
