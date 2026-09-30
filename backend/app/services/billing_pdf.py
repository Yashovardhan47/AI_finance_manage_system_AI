from __future__ import annotations

from hashlib import sha256
from importlib.resources import files
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.billing_models import BillingInvoice


FONT_REGULAR = "BillFlowSans"
FONT_BOLD = "BillFlowSans-Bold"


def _register_fonts() -> None:
    """Embed ReportLab's bundled Vera family for portable, consistent PDFs."""
    if FONT_REGULAR not in pdfmetrics.getRegisteredFontNames():
        font_dir = files("reportlab").joinpath("fonts")
        pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(font_dir.joinpath("Vera.ttf"))))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(font_dir.joinpath("VeraBd.ttf"))))
        pdfmetrics.registerFontFamily(FONT_REGULAR, normal=FONT_REGULAR, bold=FONT_BOLD)


_register_fonts()


def build_invoice_pdf(invoice: BillingInvoice, *, business_name: str, business_address: str) -> tuple[bytes, str]:
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Invoice {invoice.invoice_number}",
        author=business_name,
    )
    styles = getSampleStyleSheet()
    styles["BodyText"].fontName = FONT_REGULAR
    styles.add(ParagraphStyle(name="Right", parent=styles["BodyText"], alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name="Muted", parent=styles["BodyText"], textColor=colors.HexColor("#60716a"), fontSize=8, leading=11))
    styles.add(ParagraphStyle(name="Brand", parent=styles["Title"], fontName=FONT_BOLD, textColor=colors.HexColor("#0d2e25"), fontSize=24, leading=28))
    styles.add(ParagraphStyle(name="InvoiceTitle", parent=styles["Heading1"], fontName=FONT_BOLD, textColor=colors.HexColor("#1a6c52"), alignment=TA_RIGHT, fontSize=19))

    customer = invoice.customer
    story = [
        Table(
            [[Paragraph(business_name, styles["Brand"]), Paragraph(f"INVOICE<br/><b>{invoice.invoice_number}</b>", styles["InvoiceTitle"])]],
            colWidths=[90 * mm, 84 * mm],
        ),
        Spacer(1, 5 * mm),
        Table(
            [
                [Paragraph(f"<b>From</b><br/>{business_address}", styles["BodyText"]), Paragraph(f"<b>Bill to</b><br/>{customer.name}<br/>{customer.email}<br/>{_address(customer.billing_address)}", styles["Right"])],
                [Paragraph(f"Issue date: {invoice.issue_date.isoformat()}<br/>Due date: {invoice.due_date.isoformat()}", styles["Muted"]), Paragraph(f"Currency: {invoice.currency}<br/>Terms: {invoice.payment_terms}", styles["Right"])],
            ],
            colWidths=[87 * mm, 87 * mm],
            style=TableStyle([("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]),
        ),
        Spacer(1, 4 * mm),
    ]

    rows = [["Description", "Type", "Qty", "Unit price", "Amount"]]
    for item in invoice.line_items:
        rows.append(
            [
                Paragraph(item.description, styles["BodyText"]),
                item.line_type.value.replace("_", " ").title(),
                f"{item.quantity:,.2f}",
                f"{invoice.currency} {item.unit_amount:,.2f}",
                f"{invoice.currency} {item.amount:,.2f}",
            ]
        )
    line_table = Table(rows, colWidths=[70 * mm, 30 * mm, 18 * mm, 28 * mm, 28 * mm], repeatRows=1)
    line_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d2e25")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
                ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
                ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#dce4dd")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7f4")]),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([line_table, Spacer(1, 5 * mm)])

    totals = Table(
        [
            ["Subtotal", f"{invoice.currency} {invoice.subtotal:,.2f}"],
            ["Proration", f"{invoice.currency} {invoice.proration_total:,.2f}"],
            ["Usage", f"{invoice.currency} {invoice.usage_total:,.2f}"],
            ["Tax", f"{invoice.currency} {invoice.tax_total:,.2f}"],
            ["Total", f"{invoice.currency} {invoice.total:,.2f}"],
            ["Paid", f"{invoice.currency} {invoice.amount_paid:,.2f}"],
            ["Refunded", f"{invoice.currency} {invoice.amount_refunded:,.2f}"],
        ],
        colWidths=[35 * mm, 42 * mm],
        hAlign="RIGHT",
    )
    totals.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LINEABOVE", (0, 4), (-1, 4), 1.2, colors.HexColor("#1a6c52")),
                ("FONTNAME", (0, 4), (-1, 4), FONT_BOLD),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend(
        [
            totals,
            Spacer(1, 9 * mm),
            Paragraph(f"Payment reference: {invoice.invoice_number} | Status: {invoice.status.value.replace('_', ' ').title()}", styles["Muted"]),
            Paragraph("This invoice was generated by BillFlow AI. Contact the billing business for questions about taxes, refunds, or service access.", styles["Muted"]),
        ]
    )
    document.build(story)
    payload = buffer.getvalue()
    return payload, sha256(payload).hexdigest()


def _address(value: dict) -> str:
    if not value:
        return "Address not provided"
    parts = [str(value.get(key, "")).strip() for key in ("line1", "line2", "city", "postal_code", "country")]
    return "<br/>".join(part for part in parts if part) or "Address not provided"
