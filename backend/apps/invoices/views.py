"""Invoice Center API: cards for every purchase / booking, invoice detail, and the server-rendered document."""

from datetime import date

from django.http import HttpResponse
from django.utils.html import escape
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.activity.services import record
from apps.core.api.exceptions import DomainError
from apps.core.api.permissions import IsCustomer

from . import builder


def _date(v):
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        raise DomainError("Choose valid dates.", code="validation_error")


class InvoicesView(APIView):
    """GET /customer/invoices?service=&status=&q=&from=&to="""

    permission_classes = [IsCustomer]

    def get(self, request):
        qp = request.query_params
        c = request.user.customer_profile
        rows = builder.cards(c, service=qp.get("service", ""), status=qp.get("status", ""), q=qp.get("q", "")[:60],
                             date_from=_date(qp.get("from")), date_to=_date(qp.get("to")))
        filtered = any(qp.get(k) for k in ("service", "status", "q", "from", "to"))
        services = sorted({r["service"] for r in (builder.cards(c) if filtered else rows)})
        return Response({"results": rows, "services": services})


class InvoiceView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request, pk):
        inv = builder.owned_invoice(request.user.customer_profile, pk)
        if inv is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        builder.ensure(inv.payment)  # picks up refunds made since it was issued
        inv.refresh_from_db()
        return Response(builder.detail(inv))


class InvoiceDocumentView(APIView):
    """GET /customer/invoices/<id>/document — the invoice as a self-contained, printable HTML document (owner only)."""

    permission_classes = [IsCustomer]

    def get(self, request, pk):
        inv = builder.owned_invoice(request.user.customer_profile, pk)
        if inv is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        d = builder.detail(inv)
        record(request.user.customer_profile, "invoice.downloaded", {"number": inv.number})
        resp = HttpResponse(render(d), content_type="text/html; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{inv.number}.html"'
        resp["Cache-Control"] = "private, no-store"
        return resp


def _rs(v):
    return f"₹{float(v):,.2f}" if v not in (None, "") else ""


def render(d: dict) -> str:
    e = escape
    t = d["totals"]
    s, b = d["seller"], d["buyer"]
    rows = "".join(f"<tr><td>{e(x['description'])}</td><td class=n>{x['quantity']}</td><td class=n>{_rs(x['unit_price'])}</td>"
                   f"<td class=n>{_rs(x['total'])}</td></tr>" for x in d["lines"])
    discount_label = "Discount" + (f" ({e(t['offer'])})" if t.get("offer") else "")
    parts = [("Subtotal", t.get("subtotal"), ""), (discount_label, t.get("discount"), "−"), ("Delivery fee", t.get("delivery_fee"), ""),
             ("Fees", t.get("fees"), ""), ("Taxes", t.get("tax"), "")]
    tot_html = "".join(f"<tr><td>{k}</td><td class=n>{sign}{_rs(v)}</td></tr>" for k, v, sign in parts if v and float(v))
    refunds = "".join(f"<tr><td>{e(r['number'])}</td><td>{e(r['reason'])}</td><td>{e(r['to'])}</td><td class=n>{_rs(r['amount'])}</td></tr>"
                      for r in d["refunds"])
    seller_extra = (f"<div>Partner ID {e(s['partner_id'])}</div>" if s.get("partner_id") else "") + (f"<div>GSTIN {e(s['gstin'])}</div>" if s.get("gstin") else "")
    refund_block = f"<h3>Refund documents</h3><table><tbody>{refunds}</tbody></table>" if refunds else ""
    style = """
body{font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#111;margin:0;background:#f4f5f7}
.doc{max-width:760px;margin:24px auto;background:#fff;padding:32px;border-radius:12px}
h1{font-size:20px;margin:0}.brand{font-size:26px;font-weight:800}.brand b{color:#f59e0b}
.top{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;border-bottom:2px solid #111;padding-bottom:16px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:20px 0}.k{color:#666;font-size:12px;text-transform:uppercase;letter-spacing:.06em}
table{width:100%;border-collapse:collapse;margin:12px 0}td,th{padding:8px 6px;border-bottom:1px solid #e5e7eb;text-align:left;vertical-align:top}
.n{text-align:right;white-space:nowrap}.total td{font-weight:800;border-top:2px solid #111}.note{color:#666;font-size:12px;margin-top:16px}
@media print{body{background:#fff}.doc{margin:0;border-radius:0}}"""
    return (
        f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{e(d['title'])} {e(d['number'])}</title><style>{style}</style></head><body><div class=\"doc\">"
        f"<div class=\"top\"><div><div class=\"brand\">Click<b>.</b></div><h1>{e(d['title'])}</h1></div>"
        f"<div><div><span class=\"k\">Invoice no.</span> {e(d['number'])}</div><div><span class=\"k\">Date</span> {e(d['issued_at'][:10])}</div>"
        f"<div><span class=\"k\">For</span> {e(d['label'])} {e(d['reference'])}</div><div><span class=\"k\">Status</span> {e(d['status_label'])}</div></div></div>"
        f"<div class=\"cols\"><div><div class=\"k\">Seller</div><strong>{e(s.get('name', ''))}</strong><div>{e(s.get('address', ''))}</div>{seller_extra}</div>"
        f"<div><div class=\"k\">Billed to</div><strong>{e(b.get('name', ''))}</strong><div>{e(b.get('address', ''))}</div><div>{e(b.get('email', ''))}</div>"
        f"<div>{e(b.get('phone', ''))}</div><div>Click. ID {e(b.get('customer_id', ''))}</div></div></div>"
        f"<table><thead><tr><th>Item</th><th class=n>Qty</th><th class=n>Unit price</th><th class=n>Amount</th></tr></thead><tbody>{rows}</tbody></table>"
        f"<table><tbody>{tot_html}<tr class=\"total\"><td>Total</td><td class=n>{_rs(t.get('total'))}</td></tr>"
        f"<tr><td>Paid by {e(d['payment']['method'])} · {e(d['payment']['reference'])}</td><td class=n>{_rs(t.get('paid'))}</td></tr></tbody></table>"
        f"{refund_block}<p class=\"note\">{e(d['gst_note'])} Generated by Click. from the payment record. Questions: click.startup2026@gmail.com</p>"
        f"</div></body></html>"
    )
