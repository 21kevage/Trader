"""Optional localhost-only report viewer; no order endpoints."""
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

app = FastAPI(title="AI Trading Fleet – offline demo report", docs_url=None, redoc_url=None)
_REPORT = Path("output/report.json")

@app.get("/health")
def health():
    return {"ok": True, "mode": "OFFLINE_SYNTHETIC_SIMULATION_ONLY", "orders_enabled": False}

@app.get("/api/report")
def report():
    if not _REPORT.exists():
        raise HTTPException(404, "Run 'fleet run-demo' first")
    return json.loads(_REPORT.read_text(encoding="utf-8"))

@app.get("/", response_class=HTMLResponse)
def home():
    return """<!DOCTYPE html><html lang='de'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>AI Trading Fleet – Demo</title><style>
:root{font-family:system-ui;color:#e6edf3;background:#091622}
main{max-width:860px;margin:32px auto;padding:0 20px}header{margin:40px 0}
.note{color:#ffca7a}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
.card{background:#12283b;padding:18px;border:1px solid #22435d;border-radius:14px}
.label{font-size:12px;color:#9eb4c5}.val{font-size:26px;font-weight:750;margin-top:8px}
table{width:100%;border-collapse:collapse;margin:22px 0}td,th{padding:11px;border-bottom:1px solid #244157;text-align:left;font-size:13px}
small{color:#9eb4c5}a{color:#95d8ff}
</style></head><body><main><header><small>Fleet v0.1.0 · OFFLINE DEMO</small>
<h1>AI Trading Fleet</h1><p class='note'>Nur synthetische Testdaten. Keine KI-Prognose. Kein Broker. Kein Echtgeld.</p></header>
<section id='cards' class='cards'></section><h2>Letzte simulierte Orders</h2><table>
<thead><tr><th>Datum</th><th>Instrument</th><th>Seite</th><th>Anzahl</th><th>Preis</th></tr></thead><tbody id='trades'></tbody></table>
<small>Vollständige Prüfhistorie: <a href='/api/report'>JSON-Report</a></small>
<script>fetch('/api/report').then(r=>r.json()).then(d=>{
const items=[['Modus','OFFLINE DEMO'],['Endwert',d.final_equity.toFixed(2)+' €'],
['Rendite',d.return_pct.toFixed(2)+' %'],['Drawdown',d.max_observed_drawdown_pct.toFixed(2)+' %'],
['Gebühren',d.fees_paid.toFixed(2)+' €'],['Ausführungen',d.trades]];
document.getElementById('cards').innerHTML=items.map(([k,v])=>
`<div class='card'><div class='label'>${k}</div><div class='val'>${v}</div></div>`).join('');
const tb=document.getElementById('trades');
d.fills.slice(-20).reverse().forEach(f=>{let tr=tb.insertRow();
[f.date,f.symbol,f.side,f.qty,f.price].forEach(x=>{let td=tr.insertCell();td.textContent=x})});
}).catch(()=>document.getElementById('cards').textContent='Bitte zuerst den Demolauf starten.');</script>
</main></body></html>"""
