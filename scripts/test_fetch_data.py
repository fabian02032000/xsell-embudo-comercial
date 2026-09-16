"""Prueba rápida de la lógica de agregación con datos falsos (sin llamar a internet)."""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_data as fd  # noqa: E402

MES = "2026-09"

fake_contacts = [
    {"id": "1", "properties": {"canal": "Whatsapp", "createdate": f"{MES}-01T00:00:00Z", "firstname": "Ana", "lastname": "Ruiz"}},
    {"id": "2", "properties": {"canal": "Facebook", "createdate": f"{MES}-02T00:00:00Z", "firstname": "Luis", "lastname": "Perez"}},
    {"id": "3", "properties": {"canal": "Facebook", "createdate": f"{MES}-03T00:00:00Z", "firstname": "Rosa", "lastname": "Diaz"}},
]

fake_deals = [
    {
        "id": "d1",
        "properties": {"dealname": "Deal Ana", "dealstage": "appointmentscheduled", "createdate": f"{MES}-01T00:00:00Z"},
        "associations": {"contacts": {"results": [{"id": "1"}]}},
    },
    {
        "id": "d2",
        "properties": {"dealname": "Deal Luis", "dealstage": "closedwon", "createdate": f"{MES}-02T00:00:00Z"},
        "associations": {"contacts": {"results": [{"id": "2"}]}},
    },
    {
        "id": "d3",
        "properties": {"dealname": "Deal Rosa", "dealstage": "closedlost", "createdate": f"{MES}-03T00:00:00Z"},
        "associations": {"contacts": {"results": [{"id": "3"}]}},
    },
]

fake_pacs = [
    {"nombre": "Prospecto X", "etapa": "Identificado", "actualizado": f"{MES}-05"},
]

fd.fetch_hubspot_contacts = lambda: fake_contacts
fd.fetch_hubspot_deals = lambda: fake_deals
fd.fetch_pacs_prospectos = lambda: fake_pacs

dataset = fd.build_dataset()
mes = dataset["meses"][MES]
print(json.dumps(mes, ensure_ascii=False, indent=2))

# aserciones básicas
assert mes["fuentes"]["Comercial"]["contactos"] == 1, "Ana (Whatsapp) debe contar como Comercial"
assert mes["fuentes"]["MKT Pauta"]["contactos"] == 2, "Luis y Rosa (Facebook) deben contar como MKT Pauta"
assert mes["fuentes"]["Comercial"]["reuniones"] == 1, "Deal de Ana llegó a Reunión Agendada"
assert mes["fuentes"]["MKT Pauta"]["ventas"] == 1, "Deal de Luis (closedwon) debe contar como venta"
assert mes["fuentes"]["MKT Pauta"]["reuniones"] == 1 and mes["fuentes"]["MKT Pauta"]["propuestas"] == 1, "closedwon debe pasar también por reuniones/propuestas (nivel 3)"
assert mes["fuentes"]["LinkedIn PACS"]["contactos"] == 1
assert mes["fuentes"]["LinkedIn PACS"]["reuniones"] == 0
detalle_rosa = [r for r in mes["detalle"] if r["nombre"] == "Rosa Diaz"]
assert detalle_rosa and detalle_rosa[0]["etapa"] == "Descartada"

print("\nOK: todas las validaciones pasaron")
