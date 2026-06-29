#!/usr/bin/env python3
"""Generate GovTech Platform Excalidraw diagrams."""
import json, os, random, time

random.seed(42)
TS = int(time.time() * 1000)
OUT = os.path.join(os.path.dirname(__file__), "docs")

def uid():
    return ''.join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=20))

def rect(x, y, w, h, stroke, bg, stroke_style="solid", roughness=1, sw=2):
    return {"id": uid(), "type": "rectangle", "x": x, "y": y, "width": w, "height": h,
            "angle": 0, "strokeColor": stroke, "backgroundColor": bg, "fillStyle": "solid",
            "strokeWidth": sw, "strokeStyle": stroke_style, "roughness": roughness, "opacity": 100,
            "groupIds": [], "frameId": None, "roundness": {"type": 3},
            "seed": random.randint(1,9999999), "version": 1, "versionNonce": random.randint(1,9999999),
            "isDeleted": False, "boundElements": [], "updated": TS, "link": None, "locked": False}

def txt(x, y, w, h, content, size=14, color="#1e1e1e", align="center"):
    return {"id": uid(), "type": "text", "x": x, "y": y, "width": w, "height": h,
            "angle": 0, "strokeColor": color, "backgroundColor": "transparent", "fillStyle": "solid",
            "strokeWidth": 1, "strokeStyle": "solid", "roughness": 1, "opacity": 100,
            "groupIds": [], "frameId": None, "roundness": None,
            "seed": random.randint(1,9999999), "version": 1, "versionNonce": random.randint(1,9999999),
            "isDeleted": False, "boundElements": [], "updated": TS, "link": None, "locked": False,
            "text": content, "fontSize": size, "fontFamily": 1,
            "textAlign": align, "verticalAlign": "middle",
            "containerId": None, "originalText": content, "lineHeight": 1.25, "autoResize": False}

def arrow(x1, y1, x2, y2, color="#495057"):
    dx, dy = x2-x1, y2-y1
    return {"id": uid(), "type": "arrow", "x": x1, "y": y1, "width": abs(dx), "height": abs(dy),
            "angle": 0, "strokeColor": color, "backgroundColor": "transparent", "fillStyle": "solid",
            "strokeWidth": 2, "strokeStyle": "solid", "roughness": 1, "opacity": 100,
            "groupIds": [], "frameId": None, "roundness": {"type": 2},
            "seed": random.randint(1,9999999), "version": 1, "versionNonce": random.randint(1,9999999),
            "isDeleted": False, "boundElements": [], "updated": TS, "link": None, "locked": False,
            "points": [[0,0],[dx,dy]], "lastCommittedPoint": None,
            "startBinding": None, "endBinding": None,
            "startArrowhead": None, "endArrowhead": "arrow", "elbowed": False}

def diamond(x, y, w, h, stroke, bg):
    return {"id": uid(), "type": "diamond", "x": x, "y": y, "width": w, "height": h,
            "angle": 0, "strokeColor": stroke, "backgroundColor": bg, "fillStyle": "solid",
            "strokeWidth": 2, "strokeStyle": "solid", "roughness": 1, "opacity": 100,
            "groupIds": [], "frameId": None, "roundness": {"type": 2},
            "seed": random.randint(1,9999999), "version": 1, "versionNonce": random.randint(1,9999999),
            "isDeleted": False, "boundElements": [], "updated": TS, "link": None, "locked": False}

def save(name, elements):
    doc = {"type": "excalidraw", "version": 2, "source": "https://excalidraw.com",
           "elements": elements,
           "appState": {"gridSize": 20, "viewBackgroundColor": "#ffffff",
                        "currentItemFontFamily": 1, "currentItemRoughness": 1},
           "files": {}}
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
    print(f"  Created: {path}")

# ─────────────────────────────────────────────────────────────────────────────
# DIAGRAM 1: Architecture Platform
# ─────────────────────────────────────────────────────────────────────────────
def diagram1():
    el = []

    # ── Banner ────────────────────────────────────────────────────────────────
    el.append(rect(20, 20, 1960, 65, "#0f4761", "#0f4761", roughness=0))
    el.append(txt(20, 20, 1960, 65,
        "GovTech Platform  ·  TMForum SID  ·  Event-Driven  ·  Cloud-Native  ·  Multi-Tenant",
        size=22, color="#ffffff"))

    # ── Presentation Layer (y=105) ────────────────────────────────────────────
    el.append(rect(20, 105, 1960, 155, "#c92a2a", "#fff5f5"))
    el.append(txt(30, 108, 300, 18, "CAPA DE PRESENTACIÓN", size=11, color="#c92a2a", align="left"))
    portals = [
        ("Portal Ciudadano\nReact + Next.js", 50, 130),
        ("Portal Backoffice\nReact + shadcn/ui", 340, 130),
        ("Dashboard Ejecutivo\nBI + ML Charts", 630, 130),
        ("Mobile App\nPWA / React Native", 920, 130),
        ("API Gateway\nKong · REST · GraphQL · gRPC", 1220, 130),
    ]
    for label, px, py in portals:
        el.append(rect(px, py, 260, 80, "#c92a2a", "#ffffff", roughness=1))
        el.append(txt(px, py, 260, 80, label, size=13, color="#c92a2a"))

    # ── Microservices Layer (y=280) ───────────────────────────────────────────
    el.append(rect(20, 280, 1960, 310, "#1864ab", "#e7f5ff"))
    el.append(txt(30, 283, 350, 18, "MICROSERVICIOS — TMForum Open APIs  (Python FastAPI / Java Spring Boot)", size=11, color="#1864ab", align="left"))

    svc_row1 = [
        ("Party Service\nTMF632\nGestión Ciudadanos", 50),
        ("Product Catalog\nTMF620\nServicios & Productos", 310),
        ("Order Service\nTMF622\nTrámites & Solicitudes", 570),
        ("Billing Service\nTMF678\nPagos & Cobros", 830),
        ("Trouble Ticket\nTMF621\nPostventa & Soporte", 1090),
    ]
    svc_row2 = [
        ("Event Service\nTMF688\nDomain Events", 50),
        ("Notification Svc\nEmail · SMS · Push\nWebSocket realtime", 310),
        ("Eligibility Engine\nReglas + ML\nAuto-aprobación", 570),
        ("Config Service\nMulti-tenant\nOrganismo config", 830),
        ("Resource Catalog\nTMF634\nInfraestructura svc", 1090),
    ]
    for label, sx in svc_row1:
        el.append(rect(sx, 315, 240, 100, "#1864ab", "#ffffff", roughness=1))
        el.append(txt(sx, 315, 240, 100, label, size=12, color="#1864ab"))
    for label, sx in svc_row2:
        el.append(rect(sx, 430, 240, 100, "#1864ab", "#ffffff", roughness=1))
        el.append(txt(sx, 430, 240, 100, label, size=12, color="#1864ab"))

    # arrows: presentation -> microservices
    el.append(arrow(1000, 260, 1000, 280, "#1864ab"))

    # ── Event Bus (y=610) ─────────────────────────────────────────────────────
    el.append(rect(20, 610, 1960, 85, "#5f3dc4", "#f3f0ff"))
    el.append(txt(20, 610, 1960, 85,
        "EVENT BUS  —  Apache Kafka / Google Pub/Sub\n"
        "citizen.created · order.placed · order.completed · benefit.granted · sla.breach.risk · ml.score.updated",
        size=13, color="#5f3dc4"))
    el.append(arrow(600, 590, 600, 610, "#5f3dc4"))
    el.append(arrow(1000, 590, 1000, 610, "#5f3dc4"))

    # ── Bottom 3 columns (y=715) ──────────────────────────────────────────────
    el.append(rect(20, 715, 620, 165, "#862e9c", "#f8f0fc"))
    el.append(txt(20, 715, 620, 165,
        "ML / AI PIPELINE\nVertex AI · Gemini · BigQuery ML\nFeature Store · Churn · Propensión\nNPS predicho · SLA Risk · Next Best Action",
        size=13, color="#862e9c"))

    el.append(rect(680, 715, 620, 165, "#2b8a3e", "#ebfbee"))
    el.append(txt(680, 715, 620, 165,
        "DATA LAYER\nCloud Spanner — OLTP (entidades ACID)\nBigQuery — OLAP & Analytics\nRedis Memorystore — Cache",
        size=13, color="#2b8a3e"))

    el.append(rect(1340, 715, 640, 165, "#0c8599", "#e3fafc"))
    el.append(txt(1340, 715, 640, 165,
        "INTEGRACIONES\nIdentidad Nacional (OIDC / SAML)\nRegistros civiles · Padrón\nGov Systems (REST/SOAP)\nFirma digital · Pasarelas de pago",
        size=13, color="#0c8599"))

    el.append(arrow(330, 695, 330, 715, "#862e9c"))
    el.append(arrow(990, 695, 990, 715, "#2b8a3e"))
    el.append(arrow(1660, 695, 1660, 715, "#0c8599"))

    # ── Config Layer (y=900) ──────────────────────────────────────────────────
    el.append(rect(20, 900, 1960, 120, "#e67700", "#fff9db", stroke_style="dashed", sw=3))
    el.append(txt(30, 905, 500, 18, "CONFIGURACIÓN POR ORGANISMO  (multi-tenant — cambia sin tocar el core)", size=11, color="#e67700", align="left"))
    el.append(txt(20, 928, 1960, 80,
        "Reglas de elegibilidad  ·  Catálogo de servicios  ·  Actores y roles  ·  Normativa y SLAs  ·  Branding  ·  Integraciones específicas\n"
        "Instancias ejemplo:   ANSES Argentina   ·   BPS Uruguay   ·   IMSS México   ·   Ministerios   ·   Municipios   ·   Agencias regulatorias",
        size=14, color="#e67700"))

    # ── Infrastructure (y=1040) ───────────────────────────────────────────────
    el.append(rect(20, 1040, 1960, 70, "#495057", "#f1f3f5"))
    el.append(txt(20, 1040, 1960, 70,
        "INFRAESTRUCTURA  ·  GKE / Kubernetes  ·  Istio Service Mesh  ·  Cloud Build CI/CD  ·  Terraform IaC  ·  OpenTelemetry  ·  Cloud Armor WAF",
        size=13, color="#495057"))

    save("01-arquitectura-plataforma.excalidraw", el)


# ─────────────────────────────────────────────────────────────────────────────
# DIAGRAM 2: TMForum Entity Model
# ─────────────────────────────────────────────────────────────────────────────
def diagram2():
    el = []

    # Banner
    el.append(rect(20, 20, 1760, 55, "#0f4761", "#0f4761", roughness=0))
    el.append(txt(20, 20, 1760, 55, "Modelo de Entidades — TMForum SID adaptado para Sector Público  (Event Sourcing + ML Enrichment)", size=18, color="#ffffff"))

    # ── ORGANISM TENANT (top-center) ──────────────────────────────────────────
    el.append(rect(620, 105, 560, 100, "#e67700", "#fff9db", sw=3))
    el.append(txt(620, 105, 560, 25, "ORGANISM TENANT  (config root)", size=13, color="#e67700"))
    el.append(txt(620, 130, 560, 75,
        "id · name · country\ntype: ministry | agency | municipality\nconfig: rules, catalog, branding, integrations",
        size=12, color="#495057"))

    # arrows from organism to 3 entities
    el.append(arrow(700, 205, 280, 280, "#e67700"))
    el.append(arrow(900, 205, 900, 280, "#e67700"))
    el.append(arrow(1100, 205, 1460, 280, "#e67700"))

    # ── CITIZEN (TMF632) ──────────────────────────────────────────────────────
    el.append(rect(40, 280, 400, 270, "#0c8599", "#e3fafc"))
    el.append(txt(40, 280, 400, 30, "CITIZEN  (TMF632)", size=14, color="#ffffff"))
    el.append(rect(40, 310, 400, 30, "#0c8599", "#0c8599", roughness=0))  # header bg trick
    # just use text
    el.append(txt(40, 315, 400, 230,
        "id\ndocument_id  (CUIL / RUT / DNI)\nfull_name\nbirth_date\naddress\ncontact  (email, phone)\nsegment  (A / B / C)\nstatus  (active | inactive)\n— ML scores —\nchurn_score · propensity\nnps_predicted · lifetime_value",
        size=12, color="#1e1e1e", align="left"))

    # ── PRODUCT CATALOG (TMF620) ──────────────────────────────────────────────
    el.append(rect(660, 280, 400, 230, "#1864ab", "#e7f5ff"))
    el.append(txt(660, 280, 400, 30, "PRODUCT CATALOG  (TMF620)", size=14, color="#1864ab"))
    el.append(txt(660, 310, 400, 200,
        "id\nname\ntype  (service | benefit | subsidy)\ndescription\nprice_model\nlifecycle  (launched | active | retired)\nchannels[]\n— ML —\ndemand_score · popularity_rank",
        size=12, color="#1e1e1e", align="left"))

    # ── OFFERING (TMF620 Offering) ────────────────────────────────────────────
    el.append(rect(1360, 280, 400, 230, "#862e9c", "#f8f0fc"))
    el.append(txt(1360, 280, 400, 30, "OFFERING  (TMF620)", size=14, color="#862e9c"))
    el.append(txt(1360, 310, 400, 200,
        "id\nproduct_ids[]\neligibility_rules\nprice_model\nvalid_from / valid_to\nchannels[]\nmax_beneficiaries\n— ML —\nrecommendation_score\npropensity_score",
        size=12, color="#1e1e1e", align="left"))

    # arrows to ORDER
    el.append(arrow(240, 550, 700, 640, "#495057"))
    el.append(arrow(860, 510, 860, 640, "#495057"))
    el.append(arrow(1560, 510, 1000, 640, "#495057"))

    # relationship labels
    el.append(txt(350, 580, 160, 20, "requests  1:N", size=11, color="#495057"))
    el.append(txt(900, 560, 120, 20, "contains", size=11, color="#495057"))
    el.append(txt(1220, 575, 120, 20, "applies  N:M", size=11, color="#495057"))

    # ── ORDER / TRAMITE (TMF622) ──────────────────────────────────────────────
    el.append(rect(540, 640, 720, 230, "#2b8a3e", "#ebfbee"))
    el.append(txt(540, 640, 720, 30, "ORDER / TRÁMITE  (TMF622)", size=14, color="#2b8a3e"))
    el.append(txt(540, 670, 720, 200,
        "id · citizen_id · offering_id · channel\n"
        "status:  pending | processing | completed | cancelled\n"
        "created_at · sla_due · priority · assigned_to\n"
        "— ML enrichment —\n"
        "sla_risk_score · auto_approved  (bool)\n"
        "recommended_action · fraud_risk",
        size=12, color="#1e1e1e", align="left"))

    # arrows from ORDER to BILLING & TICKET
    el.append(arrow(640, 870, 200, 940, "#495057"))
    el.append(arrow(1160, 870, 1440, 940, "#495057"))

    # ── BILLING (TMF678) ──────────────────────────────────────────────────────
    el.append(rect(40, 940, 380, 190, "#c92a2a", "#fff5f5"))
    el.append(txt(40, 940, 380, 30, "BILLING  (TMF678)", size=14, color="#c92a2a"))
    el.append(txt(40, 970, 380, 160,
        "id · order_id\namount · currency · tax\nstatus  (pending | paid | overdue)\ndue_date · payment_method\npayment_gateway_ref",
        size=12, color="#1e1e1e", align="left"))

    # ── TROUBLE TICKET (TMF621) ───────────────────────────────────────────────
    el.append(rect(1380, 940, 380, 190, "#e67700", "#fff9db"))
    el.append(txt(1380, 940, 380, 30, "TROUBLE TICKET  (TMF621)", size=14, color="#e67700"))
    el.append(txt(1380, 970, 380, 160,
        "id · order_id · citizen_id\nissue_type · description\npriority  (low | medium | high | critical)\nsla_due · status · resolution\nassigned_to · channel",
        size=12, color="#1e1e1e", align="left"))

    # ── DOMAIN EVENTS (TMF688) — dashed ──────────────────────────────────────
    el.append(rect(20, 1165, 1760, 85, "#5f3dc4", "#f3f0ff", stroke_style="dashed", sw=2))
    el.append(txt(20, 1165, 400, 20, "DOMAIN EVENTS  (TMF688)  — Event Bus", size=12, color="#5f3dc4", align="left"))
    el.append(txt(20, 1188, 1760, 62,
        "CitizenCreated · CitizenSegmentChanged · OfferingPublished · OrderPlaced · OrderApproved\n"
        "OrderCompleted · SLABreachRisk · BenefitGranted · PaymentProcessed · TicketOpened · TicketResolved · ML_ScoreUpdated",
        size=12, color="#5f3dc4"))

    # ── ML ENRICHMENT LAYER — dashed ─────────────────────────────────────────
    el.append(rect(20, 1280, 1760, 80, "#862e9c", "#f8f0fc", stroke_style="dashed", sw=2))
    el.append(txt(20, 1280, 400, 20, "ML ENRICHMENT LAYER  (cross-cutting)", size=12, color="#862e9c", align="left"))
    el.append(txt(20, 1303, 1760, 57,
        "churn_score · propensity_to_apply · nps_predicted · lifetime_value · segment_ml\n"
        "next_best_action · fraud_risk · eligibility_score · sla_breach_probability · demand_forecast",
        size=12, color="#862e9c"))

    save("02-modelo-entidades-tmforum.excalidraw", el)


# ─────────────────────────────────────────────────────────────────────────────
# DIAGRAM 3: Domain Events Flow (Sales + Post-sale)
# ─────────────────────────────────────────────────────────────────────────────
def diagram3():
    el = []

    # Banner
    el.append(rect(20, 20, 2360, 55, "#0f4761", "#0f4761", roughness=0))
    el.append(txt(20, 20, 2360, 55, "Flujo Venta & Postventa — Arquitectura Event-Driven  (Domain Events + ML Inference)", size=20, color="#ffffff"))

    lane_h = 165
    lane_x = 20
    lane_w = 2360
    lanes = [
        ("CIUDADANO  (Portal / Mobile)", "#c92a2a", "#fff5f5"),
        ("PLATFORM CORE  (Microservicios TMForum)", "#1864ab", "#e7f5ff"),
        ("EVENT BUS + ML  (Kafka / Vertex AI)", "#5f3dc4", "#f3f0ff"),
        ("SISTEMAS EXTERNOS  (Integraciones)", "#2b8a3e", "#ebfbee"),
    ]
    lane_tops = []
    for i, (label, stroke, bg) in enumerate(lanes):
        y = 100 + i * lane_h
        lane_tops.append(y)
        el.append(rect(lane_x, y, lane_w, lane_h, stroke, bg))
        el.append(txt(lane_x + 8, y + 6, 400, 20, label, size=12, color=stroke, align="left"))

    # Lane Y centers
    L = [lt + lane_h // 2 for lt in lane_tops]

    # ── Step boxes ────────────────────────────────────────────────────────────
    # Steps layout: each step has x position and content per lane
    steps_x = [110, 360, 610, 870, 1130, 1400, 1700, 1980]
    bw, bh = 210, 90

    # LANE 0 — Ciudadano
    cit_steps = [
        ("Accede al\nportal", steps_x[0]),
        ("Busca\nservicio", steps_x[1]),
        ("Elige\noferta", steps_x[2]),
        ("Completa\nformulario", steps_x[3]),
        ("Firma\ndigital", steps_x[4]),
        ("Sigue\nestado", steps_x[5]),
        ("", steps_x[6]),
        ("Recibe\nbeneficio", steps_x[7]),
    ]
    for label, sx in cit_steps:
        if label:
            el.append(rect(sx, L[0]-40, bw, bh, "#c92a2a", "#ffffff", roughness=1))
            el.append(txt(sx, L[0]-40, bw, bh, label, size=13, color="#c92a2a"))

    # LANE 1 — Platform Core
    plat_steps = [
        ("Party Svc\nconsulta ciudadano\nTMF632", steps_x[0]),
        ("Catalog Svc\nML top-3 ofertas\nTMF620", steps_x[1]),
        ("Eligibility\nEngine valida\nauto / manual", steps_x[2]),
        ("Order Svc\ncrea trámite\nTMF622", steps_x[3]),
        ("Notif Svc\n'Orden recibida'\nTMF688", steps_x[4]),
        ("Order Svc\nactualiza estado\nSLA check", steps_x[5]),
        ("Order Svc\nresuelve\nTMF622", steps_x[6]),
        ("Billing Svc\nprocesa pago\nTMF678", steps_x[7]),
    ]
    for label, sx in plat_steps:
        el.append(rect(sx, L[1]-45, bw, bh+10, "#1864ab", "#ffffff", roughness=1))
        el.append(txt(sx, L[1]-45, bw, bh+10, label, size=12, color="#1864ab"))

    # LANE 2 — Event Bus + ML
    event_steps = [
        ("CitizenAccessed\nML: propensity\nscores", steps_x[0]),
        ("OfferingViewed\nML: recommend.\nranking", steps_x[1]),
        ("EligibilityChecked\nML: eligibility\nscore", steps_x[2]),
        ("OrderPlaced\nKafka publish\nML: sla_risk", steps_x[3]),
        ("OrderConfirmed\nML: ETA predict.\nnotif dispatch", steps_x[4]),
        ("SLABreachRisk?\nML alert if\nrisk > 0.7", steps_x[5]),
        ("OrderCompleted\nML: NPS predict\nBenefitGranted", steps_x[6]),
        ("PaymentProcessed\nML: LTV update\nsegment refresh", steps_x[7]),
    ]
    for label, sx in event_steps:
        el.append(rect(sx, L[2]-45, bw, bh+10, "#5f3dc4", "#f3f0ff", roughness=1))
        el.append(txt(sx, L[2]-45, bw, bh+10, label, size=11, color="#5f3dc4"))

    # LANE 3 — Sistemas externos
    ext_steps = [
        ("Identity Provider\nOIDC / SAML\nautenticación", steps_x[0]),
        ("", steps_x[1]),
        ("Registro Nacional\nverifica identidad\npadrón", steps_x[2]),
        ("", steps_x[3]),
        ("", steps_x[4]),
        ("", steps_x[5]),
        ("Provision Svc\notorga beneficio\nintegración", steps_x[6]),
        ("Notif Gateway\nSMS · Email · Push\nconfirmación", steps_x[7]),
    ]
    for label, sx in ext_steps:
        if label:
            el.append(rect(sx, L[3]-40, bw, bh, "#2b8a3e", "#ffffff", roughness=1))
            el.append(txt(sx, L[3]-40, bw, bh, label, size=11, color="#2b8a3e"))

    # ── Horizontal flow arrows in each lane ───────────────────────────────────
    for i in range(len(steps_x)-1):
        x1 = steps_x[i] + bw + 4
        x2 = steps_x[i+1] - 4
        # Ciudadano
        if cit_steps[i][0] and cit_steps[i+1][0]:
            el.append(arrow(x1, L[0], x2, L[0], "#c92a2a"))
        # Platform
        el.append(arrow(x1, L[1], x2, L[1], "#1864ab"))
        # Events
        el.append(arrow(x1, L[2], x2, L[2], "#5f3dc4"))

    # ── Vertical arrows between lanes ────────────────────────────────────────
    # Cit -> Plat (each step)
    for sx in [steps_x[1], steps_x[3], steps_x[4]]:
        mid = sx + bw//2
        el.append(arrow(mid, L[0]+50, mid, L[1]-50, "#999999"))
    # Plat -> Events (publish)
    for sx in [steps_x[2], steps_x[3], steps_x[5], steps_x[6]]:
        mid = sx + bw//2
        el.append(arrow(mid, L[1]+55, mid, L[2]-50, "#5f3dc4"))
    # Plat -> Ext
    for sx in [steps_x[0], steps_x[2], steps_x[6], steps_x[7]]:
        mid = sx + bw//2
        el.append(arrow(mid, L[1]+55, mid, L[3]-45, "#2b8a3e"))

    # ── Decision diamond: auto-approve? ──────────────────────────────────────
    diam_x = 870 + bw + 20
    diam_y = L[1] - 55
    el.append(diamond(diam_x, diam_y, 120, 80, "#e67700", "#fff9db"))
    el.append(txt(diam_x, diam_y, 120, 80, "¿Auto-\naprueba?", size=11, color="#e67700"))
    el.append(txt(diam_x + 125, diam_y + 20, 60, 20, "SÍ →", size=11, color="#2b8a3e"))
    el.append(txt(diam_x + 35, diam_y + 85, 100, 20, "NO ↓ funcionario", size=10, color="#c92a2a"))

    # ── ML inference badges ───────────────────────────────────────────────────
    ml_positions = [steps_x[1], steps_x[2], steps_x[3], steps_x[5], steps_x[6]]
    for sx in ml_positions:
        bx = sx + bw - 28
        by = L[2] - 55
        el.append(rect(bx, by, 32, 22, "#862e9c", "#862e9c", roughness=0, sw=1))
        el.append(txt(bx, by, 32, 22, "ML", size=10, color="#ffffff"))

    save("03-flujo-eventos-dominio.excalidraw", el)


if __name__ == "__main__":
    print("Generating GovTech Platform Excalidraw diagrams...")
    diagram1()
    diagram2()
    diagram3()
    print("Done! Open files in excalidraw.com or VS Code (Excalidraw extension).")
