"""Prueba rápida de la lógica de agregación con datos falsos (sin llamar a internet)."""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_data as fd  # noqa: E402

MES = "2026-09"
D1 = f"{MES}-01"
D2 = f"{MES}-02"
D3 = f"{MES}-03"
D4 = f"{MES}-04"

fake_contacts = [
    {"id": "1", "properties": {"canal": "Whatsapp", "createdate": f"{D1}T00:00:00Z", "firstname": "Ana", "lastname": "Ruiz"}},
    {"id": "2", "properties": {"canal": "Facebook", "createdate": f"{D2}T00:00:00Z", "firstname": "Luis", "lastname": "Perez"}},
    {"id": "3", "properties": {"canal": "Facebook", "createdate": f"{D3}T00:00:00Z", "firstname": "Rosa", "lastname": "Diaz", "email": "rosa@descartada.pe"}},
    # Sin "canal" (lo típico de un lead que llegó solo por el formulario pagado de
    # Meta): debe detectarse igual como MKT Pauta gracias al fallback por
    # hs_analytics_source / hs_analytics_source_data_1.
    {"id": "4", "properties": {"createdate": f"{D4}T00:00:00Z", "firstname": "Jorge", "lastname": "Barco", "email": "jorge@empresa.pe", "hs_analytics_source": "PAID_SOCIAL", "hs_analytics_source_data_1": "Facebook"}},
]

fake_deals = [
    {
        "id": "d1",
        "properties": {"dealname": "Deal Ana", "dealstage": "appointmentscheduled", "createdate": f"{D1}T00:00:00Z"},
        "associations": {"contacts": {"results": [{"id": "1"}]}},
    },
    {
        "id": "d2",
        "properties": {
            "dealname": "Deal Luis", "dealstage": "closedwon", "createdate": f"{D2}T00:00:00Z",
            # MKT Pauta + Estadio "Consolidado" (no excluido) -> debe entrar en audiencia tibia.
            "etapa_final": "Consolidado", "hs_priority": "medium",
        },
        "associations": {"contacts": {"results": [{"id": "2"}]}},
    },
    {
        "id": "d3",
        "properties": {"dealname": "Deal Rosa", "dealstage": "closedlost", "createdate": f"{D3}T00:00:00Z"},
        "associations": {"contacts": {"results": [{"id": "3"}]}},
    },
    {
        "id": "d4",
        "properties": {
            "dealname": "Deal Jorge (Meta sin canal)", "dealstage": "appointmentscheduled", "createdate": f"{D4}T00:00:00Z",
            # MKT Pauta pero Estadio "Semilla" (excluido) -> NO debe entrar en audiencia tibia.
            "etapa_final": "Semilla", "hs_priority": "high",
        },
        "associations": {"contacts": {"results": [{"id": "4"}]}},
    },
]

fake_pacs = [
    {"nombre": "Prospecto X", "etapa": "Identificado", "actualizado": f"{MES}-05"},
]

fd.fetch_hubspot_contacts = lambda: fake_contacts
fd.fetch_hubspot_deals = lambda: fake_deals
fd.fetch_pacs_prospectos = lambda: fake_pacs

dataset = fd.build_dataset()
dias = dataset["dias"]
print(json.dumps({k: v for k, v in dias.items() if k in (D1, D2, D3, D4)}, ensure_ascii=False, indent=2))

# --- aserciones por día ---
assert dias[D1]["fuentes"]["Comercial"]["contactos"] == 1, "Ana (Whatsapp) debe contar como Comercial el día 1"
assert dias[D1]["fuentes"]["Comercial"]["reuniones"] == 1, "Deal de Ana llegó a Reunión Agendada"

assert dias[D2]["fuentes"]["MKT Pauta"]["contactos"] == 1, "Luis (Facebook) debe contar como MKT Pauta el día 2"
assert dias[D2]["fuentes"]["MKT Pauta"]["ventas"] == 1, "Deal de Luis (closedwon) debe contar como venta"
assert dias[D2]["fuentes"]["MKT Pauta"]["reuniones"] == 1 and dias[D2]["fuentes"]["MKT Pauta"]["propuestas"] == 1, \
    "closedwon debe pasar también por reuniones/propuestas (nivel 3)"

assert dias[D3]["fuentes"]["MKT Pauta"]["contactos"] == 1, "Rosa (Facebook) debe contar como MKT Pauta el día 3"
detalle_rosa = [r for r in dias[D3]["detalle"] if r["contacto"] == "Rosa Diaz"]
assert detalle_rosa and detalle_rosa[0]["etapa"] == "Descartada"
assert detalle_rosa[0]["nivel"] == "Fuera del embudo", "closedlost no debe clasificar dentro del embudo"
assert detalle_rosa[0]["negocio"] == "Deal Rosa"
assert detalle_rosa[0]["fecha"] == D3

# Jorge no tiene "canal", pero HubSpot registró que llegó por publicidad paga de
# Facebook -> debe clasificarse igual como MKT Pauta (el fix que pidió Fabián).
assert dias[D4]["fuentes"]["MKT Pauta"]["contactos"] == 1, \
    "Lead de Meta sin 'canal' pero con hs_analytics_source=PAID_SOCIAL/Facebook debe caer en MKT Pauta"
assert dias[D4]["fuentes"]["Comercial"]["contactos"] == 0, "No debe caer por defecto en Comercial"
detalle_jorge = [r for r in dias[D4]["detalle"] if r["contacto"] == "Jorge Barco"]
assert detalle_jorge and detalle_jorge[0]["fuente"] == "MKT Pauta"

# LinkedIn PACS sigue funcionando igual, ahora indexado por día
dia_pacs = f"{MES}-05"
assert dias[dia_pacs]["fuentes"]["LinkedIn PACS"]["contactos"] == 1
assert dias[dia_pacs]["fuentes"]["LinkedIn PACS"]["reuniones"] == 0
detalle_pacs = [r for r in dias[dia_pacs]["detalle"] if r["origen"] == "LinkedIn PACS"][0]
assert detalle_pacs["nivel"] == "Contactos"
assert detalle_pacs["negocio"] is None

# clientes_antiguos: solo los negocios Descartados (closedlost) entran aquí,
# con su contacto y correo, para las campañas de reenganche (Email MKT).
clientes_antiguos = dataset["clientes_antiguos"]
assert len(clientes_antiguos) == 1, "Solo el deal de Rosa (closedlost) debe salir como cliente antiguo"
assert clientes_antiguos[0]["negocio"] == "Deal Rosa"
assert clientes_antiguos[0]["contacto"] == "Rosa Diaz"
assert clientes_antiguos[0]["email"] == "rosa@descartada.pe"
assert clientes_antiguos[0]["deal_id"] == "d3"

# metas_mensuales_default ahora es un solo bloque global (ya no uno por mes)
assert "metas_mensuales_default" in dataset
assert dataset["metas_mensuales_default"]["reuniones"] == 8

# --- audiencia_tibia: solo MKT Pauta, con Estadio del Lead cargado y sin
# estar en la lista de exclusión (Semilla / En Crecimiento) ---
audiencia = dataset["audiencia_tibia"]
nombres = [r["nombre"] for r in audiencia["detalle"]]
assert "Luis Perez" in nombres, "Luis (MKT Pauta, Consolidado) debe entrar en la audiencia tibia"
assert "Jorge Barco" not in nombres, "Jorge (MKT Pauta, Semilla) debe excluirse"
assert "Ana Ruiz" not in nombres, "Ana es Comercial (Whatsapp), no MKT Pauta: no debe entrar"
assert "Rosa Diaz" not in nombres, "Rosa no tiene Estadio del Lead cargado: no debe entrar"
luis = next(r for r in audiencia["detalle"] if r["nombre"] == "Luis Perez")
assert luis["estadio_lead"] == "Consolidado"
assert luis["nivel_urgencia"] == "Medio", "hs_priority=medium debe traducirse a 'Medio'"

# --- correos_insight: sin HUBSPOT_TOKEN en el entorno de prueba, no debe
# intentar llamar a HubSpot; debe devolver el resumen vacío sin explotar ---
correos = dataset["correos_insight"]
assert correos["disponible"] is False
assert correos["detalle"] == []

print("\nOK: todas las validaciones pasaron")
