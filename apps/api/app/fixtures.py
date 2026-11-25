"""A self-hosted practice target so the crawler can be exercised with zero network."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from .config import settings

PDF_TEXT = {
    "climate-grant-guidelines.pdf": [
        "CLIMATE RESILIENCE GRANT - GUIDELINES 2026",
        "Applications close 28 February 2026. Late submissions are not considered.",
        "Eligible applicants: registered non-profits and community trusts in East Africa.",
        "Awards range from USD 15,000 to USD 90,000 for 18-month projects.",
        "Submit the application form and budget worksheet to grants@example.org.",
        "Annex A: eligibility checklist. Annex B: monitoring framework.",
    ],
    "tender-notice-2026.pdf": [
        "TENDER NOTICE - PROVISION OF SOLAR MINI-GRID SERVICES",
        "Bid reference: NH-2026-0042. Closing date: 09 January 2026 at 11:00.",
        "A compulsory site briefing will be held on 18 December 2025.",
        "Bids must be submitted in a sealed envelope to the procurement office.",
    ],
    "annual-report-2025.pdf": [
        "ANNUAL REPORT 2025 - WATER AND SANITATION PROGRAMME",
        "Cumulative reach: 184,000 people across 42 districts.",
        "Expenditure: USD 6.2 million. Administrative ratio: 11.4 percent.",
        "Audited financial statements are available in Annex C.",
    ],
}

def _pdf_bytes(lines: list[str]) -> bytes:
    text = " ".join(lines)
    escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    # wrap long lines into separate Tj operations
    chunks = [escaped[i:i + 88] for i in range(0, len(escaped), 88)] or [""]
    ops = ["BT", "/F1 11 Tf", "40 780 Td"]
    for chunk in chunks:
        ops.append(f"({chunk}) Tj")
        ops.append("0 -16 Td")
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1", "replace")
    objs: list[bytes] = []
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>")
    objs.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n").encode()
    return bytes(out)


CSV = """programme,district,year,budget_usd,beneficiaries,status
Solar mini-grids,Kisumu,2025,420000,18400,active
Water points,Nakuru,2025,180000,9600,active
School sanitation,Eldoret,2024,95000,5200,closed
Clinic electrification,Mombasa,2025,260000,12000,active
"""

PAGES: dict[str, str] = {
    "index.html": """<!doctype html><html><head><title>Nighthawk Practice Target</title></head><body>
<h1>Practice target: community energy programme</h1>
<p>This is a local fixture site used to exercise the crawler end to end. It contains
documents, datasets, listings and an application pack.</p>
<ul>
<li><a href="/demo/programmes.html">Programmes</a></li>
<li><a href="/demo/opportunities.html">Open opportunities</a></li>
<li><a href="/demo/documents.html">Documents</a></li>
<li><a href="/demo/index-of-files.html">Index of /files</a></li>
<li><a href="/demo/files/climate-grant-guidelines.pdf">Grant guidelines (PDF)</a></li>
</ul></body></html>""",
    "programmes.html": """<!doctype html><html><head><title>Programmes — 2025 portfolio</title></head><body>
<h1>Programmes</h1><p>Four active programmes across water, energy and sanitation.</p>
<table><tr><th>Programme</th><th>District</th><th>Budget</th></tr>
<tr><td>Solar mini-grids</td><td>Kisumu</td><td>420,000</td></tr>
<tr><td>Water points</td><td>Nakuru</td><td>180,000</td></tr></table>
<p><a href="/demo/files/budget.csv">Download budget (CSV)</a></p>
<p><a href="/demo/files/annual-report-2025.pdf">Annual report 2025 (PDF)</a></p>
</body></html>""",
    "opportunities.html": """<!doctype html><html><head><title>Open opportunities</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Grant",
 "name":"Climate Resilience Grant 2026",
 "funder":{"@type":"Organization","name":"Ford Foundation"},
 "amount":{"@type":"MonetaryAmount","currency":"USD","value":90000},
 "applicationDeadline":"2026-02-28",
 "location":{"@type":"Place","name":"Nairobi, Kenya"},
 "description":"Grants of USD 15,000 to 90,000 for community organisations working on climate adaptation."}
</script></head><body>
<h1>Open calls</h1>
<article><h2>Climate Resilience Grant 2026</h2>
<p>Grants of USD 15,000 to 90,000 for community organisations. Applications close
28 February 2026. Read the <a href="/demo/files/climate-grant-guidelines.pdf">guidelines</a>
and submit the <a href="/demo/files/application-form.pdf">application form</a>.</p></article>
<article><h2>Solar mini-grid tender NH-2026-0042</h2>
<p>Procurement of solar mini-grid services. Closing date 09 January 2026.
See <a href="/demo/files/tender-notice-2026.pdf">tender notice</a>.</p></article>
<article><h2>Research fellowship — energy access</h2>
<p>12-month fellowship. Deadline 15 March 2026. Apply with CV and proposal.</p></article>
</body></html>""",
    "documents.html": """<!doctype html><html><head><title>Document library</title></head><body>
<h1>Document library</h1>
<ul>
<li><a href="/demo/files/climate-grant-guidelines.pdf">Climate grant guidelines</a></li>
<li><a href="/demo/files/tender-notice-2026.pdf">Tender notice 2026</a></li>
<li><a href="/demo/files/annual-report-2025.pdf">Annual report 2025</a></li>
<li><a href="/demo/files/budget.csv">Budget worksheet</a></li>
<li><a href="/demo/files/contacts.json">Partner contacts</a></li>
<li><a href="/demo/files/toolkit.zip">Field toolkit (ZIP)</a></li>
</ul></body></html>""",
    "index-of-files.html": """<!doctype html><html><head><title>Index of /demo/files</title></head><body>
<h1>Index of /demo/files</h1><pre>
<a href="../">../</a>
<a href="annual-report-2025.pdf">annual-report-2025.pdf</a>            2025-11-02 09:14  12K
<a href="budget.csv">budget.csv</a>                          2025-10-18 16:41   3K
<a href="climate-grant-guidelines.pdf">climate-grant-guidelines.pdf</a>       2025-12-01 11:02   9K
<a href="contacts.json">contacts.json</a>                       2025-09-30 08:22   1K
<a href="tender-notice-2026.pdf">tender-notice-2026.pdf</a>             2025-12-04 14:37   7K
<a href="toolkit.zip">toolkit.zip</a>                         2025-08-11 10:05   2K
</pre></body></html>""",
    "sitemap.xml": """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>http://127.0.0.1:{port}/demo/programmes.html</loc></url>
<url><loc>http://127.0.0.1:{port}/demo/opportunities.html</loc></url>
<url><loc>http://127.0.0.1:{port}/demo/documents.html</loc></url>
<url><loc>http://127.0.0.1:{port}/demo/index-of-files.html</loc></url>
</urlset>""",
    "robots.txt": """User-agent: *
Allow: /
Disallow: /demo/private/
Sitemap: http://127.0.0.1:{port}/demo/sitemap.xml
""",
    # deliberately unlinked: no page, no sitemap entry, no robots reference — the
    # only way to reach it is to paste the exact URL (the deep-link test target)
    "annex/off-cycle-notice.html": """<!doctype html><html><head><title>Off-cycle notice — climate resilience grant addendum</title>
<meta name="description" content="Addendum to the climate resilience grant: an additional USD 120,000 for coastal districts.">
</head><body>
<h1>Off-cycle notice: climate resilience grant addendum</h1>
<p>An additional <b>USD 120,000</b> is available under the climate resilience grant for
coastal districts. Applications close <time datetime="2026-04-30">30 April 2026</time>.</p>
<p>Full terms are in the <a href="/demo/files/tender-notice-2026.pdf">tender notice (PDF)</a>.</p>
</body></html>""",
    "private/internal-notes.html": """<!doctype html><html><head><title>Internal notes</title></head><body>
<h1>Internal — do not distribute</h1><p>Draft negotiation notes and unredacted figures.</p>
<p><a href="/demo/files/internal-dump.sql">export.sql</a></p></body></html>""",
}

EXTRA_FILES = {
    "files/contacts.json": json.dumps({
        "partners": [
            {"name": "Kisumu Energy Trust", "email": "info@example.org", "role": "implementation"},
            {"name": "Nakuru Water Board", "email": "procurement@example.org", "role": "offtaker"},
        ],
        "updated": "2025-09-30",
    }, indent=2),
    "files/internal-dump.sql": "CREATE TABLE grants (id int, applicant text, amount int);\n"
                               "INSERT INTO grants VALUES (1,'Kisumu Energy Trust',42000);\n",
}


def build(port: int = 8000) -> Path:
    root = settings.data_dir / "demo_site"
    root.mkdir(parents=True, exist_ok=True)
    for name, body in PAGES.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body.replace("{port}", str(port)), encoding="utf-8")
    files = root / "files"
    files.mkdir(parents=True, exist_ok=True)
    for name, lines in PDF_TEXT.items():
        (files / name).write_bytes(_pdf_bytes(lines))
    (files / "application-form.pdf").write_bytes(_pdf_bytes([
        "APPLICATION FORM - CLIMATE RESILIENCE GRANT 2026",
        "Section 1: applicant details. Section 2: project description (max 1500 words).",
        "Section 3: budget. Section 4: declaration. Submit before 28 February 2026.",
    ]))
    for name, body in EXTRA_FILES.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    (files / "budget.csv").write_text(CSV, encoding="utf-8")
    with zipfile.ZipFile(files / "toolkit.zip", "w") as zf:
        zf.writestr("README.txt", "Field toolkit: monitoring templates and checklists.\n")
        zf.writestr("checklist.csv", "item,owner,done\nbaseline survey,M&E,no\n")
    return root
