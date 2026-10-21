"""One A4 landscape page, Uzbek and Russian together, laid out like mockup 5.

Everything printed comes from the certificate's snapshot (holder, branch, modules,
releases, signatory), so the PDF never changes after the certificate is issued.
The QR code links to the public verification page with the printed code.
"""

from __future__ import annotations

import io
from functools import cache
from pathlib import Path
from urllib.parse import urlsplit

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from app import clock
from app.config import settings
from app.models import Certificate
from app.models.enums import CertificateKind
from app.services import certificates
from app.services.i18n import t

FONT_DIR = Path(__file__).resolve().parent / "fonts"
REGULAR, SEMIBOLD, BOLD = "Inter", "Inter-SemiBold", "Inter-Bold"

TEAL = HexColor("#0B5A5A")
TEAL_SOFT = HexColor("#BCD8D4")
CHIP = HexColor("#E2EFEC")
INK = HexColor("#152528")
INK_SOFT = HexColor("#2F3E42")
GREY = HexColor("#5A686C")
RULE = HexColor("#C5D0D0")

WIDTH, HEIGHT = landscape(A4)
MARGIN = 72  # content edge, inside the double border
TEXT_WIDTH = 560


@cache
def _fonts() -> None:
    for name, file in (
        (REGULAR, "Inter-Regular.ttf"),
        (SEMIBOLD, "Inter-SemiBold.ttf"),
        (BOLD, "Inter-Bold.ttf"),
    ):
        pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))


def both(key: str, **params: object) -> str:
    """The same phrase in Uzbek and Russian: "Berilgan sana / Дата выдачи"."""
    return f"{t('uz', key, **params)} / {t('ru', key, **params)}"


def _width(text: str, font: str, size: float, spacing: float = 0.0) -> float:
    return pdfmetrics.stringWidth(text, font, size) + spacing * max(len(text) - 1, 0)


def _fit(text: str, font: str, size: float, max_width: float, smallest: float) -> float:
    while size > smallest and _width(text, font, size) > max_width:
        size -= 0.5
    return size


def _text(c: Canvas, x: float, y: float, text: str, font: str, size: float, color,
          align: str = "left", spacing: float = 0.0) -> None:  # fmt: skip
    width = _width(text, font, size, spacing)
    if align == "center":
        x -= width / 2
    elif align == "right":
        x -= width
    obj = c.beginText(x, y)
    obj.setFont(font, size)
    obj.setFillColor(color)
    obj.setCharSpace(spacing)
    obj.textOut(text)
    c.drawText(obj)


def _paragraph(c: Canvas, y: float, text: str, font: str, size: float, color,
               width: float = TEXT_WIDTH, leading: float = 1.35) -> float:  # fmt: skip
    """Centred lines; returns the baseline below the last one."""
    for line in simpleSplit(text, font, size, width):
        _text(c, WIDTH / 2, y, line, font, size, color, align="center")
        y -= size * leading
    return y


def _qr(c: Canvas, url: str, x: float, y: float, size: float) -> None:
    widget = QrCodeWidget(url, barLevel="M", barBorder=0)
    x0, y0, x1, y1 = widget.getBounds()
    drawing = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
    drawing.add(widget)
    renderPDF.draw(drawing, c, x, y)


def _chips(c: Canvas, titles: list[str]) -> None:
    """Module chips, bottom-left; extra rows grow upwards so the footer stays put."""
    font, size, pad, height, gap, right = SEMIBOLD, 9.0, 7.5, 17.0, 5.0, 470.0
    rows: list[list[tuple[str, float]]] = [[]]
    x = MARGIN
    for title in titles:
        w = _width(title, font, size) + 2 * pad
        if rows[-1] and x + w > right:
            rows.append([])
            x = MARGIN
        rows[-1].append((title, w))
        x += w + gap
    first_bottom = 72 + (len(rows) - 1) * (height + gap)
    _text(c, MARGIN, first_bottom + height + 9, both("pdf.modules").upper(), SEMIBOLD, 8.5,
          GREY, spacing=1.2)  # fmt: skip
    for i, row in enumerate(rows):
        bottom, x = first_bottom - i * (height + gap), MARGIN
        for title, w in row:
            c.setFillColor(CHIP)
            c.roundRect(x, bottom, w, height, 4, stroke=0, fill=1)
            _text(c, x + pad, bottom + 5.2, title, font, size, TEAL)
            x += w + gap


def render(cert: Certificate) -> bytes:
    _fonts()
    snap = cert.snapshot
    modules = snap.get("modules", [])
    operator = cert.kind == CertificateKind.operator
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=(WIDTH, HEIGHT), pageCompression=1)
    c.setTitle(f"{t('uz', 'pdf.title').title()} {cert.number}")
    c.setAuthor(t("uz", "pdf.brand"))

    # Double border.
    c.setStrokeColor(TEAL)
    c.setLineWidth(2.2)
    c.roundRect(22, 22, WIDTH - 44, HEIGHT - 44, 5)
    c.setStrokeColor(TEAL_SOFT)
    c.setLineWidth(0.8)
    c.roundRect(29, 29, WIDTH - 58, HEIGHT - 58, 3)

    # Header: platform name (logo placeholder) and the number.
    brand_top, brand_bottom = t("uz", "pdf.brand").rsplit(" ", 1)
    _text(c, MARGIN, 517, brand_top, BOLD, 17, TEAL)
    _text(c, MARGIN, 502, brand_bottom, SEMIBOLD, 11, TEAL)
    _text(c, WIDTH - MARGIN, 526, both("pdf.number"), REGULAR, 9, GREY, align="right")
    _text(c, WIDTH - MARGIN, 510, cert.number, BOLD, 13, INK, align="right", spacing=0.5)

    # Title, holder, branch.
    _text(c, WIDTH / 2, 432, t("uz", "pdf.title"), BOLD, 34, TEAL, "center", spacing=6)
    _text(c, WIDTH / 2, 406, t("ru", "pdf.title"), SEMIBOLD, 12, GREY, "center", spacing=4)
    _text(c, WIDTH / 2, 374, both("pdf.confirms"), REGULAR, 10.5, INK_SOFT, "center")
    name = snap["holder"]["full_name"]
    _text(c, WIDTH / 2, 333, name, BOLD, _fit(name, BOLD, 26, TEXT_WIDTH, 14), INK, "center")
    c.setStrokeColor(RULE)
    c.setLineWidth(0.7)
    c.line(270, 318, WIDTH - 270, 318)
    place = " · ".join(p["name_uz"] for p in (snap.get("branch"), snap.get("region")) if p)
    if place:
        _text(c, WIDTH / 2, 300, place, REGULAR, 10, GREY, "center")

    # What was achieved.
    body = "pdf.body_operator" if operator else "pdf.body_module"
    y = _paragraph(c, 270, t("uz", body), REGULAR, 11, INK)
    y = _paragraph(c, y - 2, t("ru", body), REGULAR, 10, GREY, width=600)
    if operator:
        pill = f"{t('uz', 'pdf.qualification')} · {t('ru', 'pdf.qualification')}"
    else:
        pill = f"{modules[0]['title_uz']} · {modules[0]['title_ru']}"
    size = _fit(pill, BOLD, 14, 600, 9)
    pill_w, pill_top = _width(pill, BOLD, size) + 44, y - 8
    c.setFillColor(TEAL)
    c.roundRect(WIDTH / 2 - pill_w / 2, pill_top - 32, pill_w, 32, 16, stroke=0, fill=1)
    _text(c, WIDTH / 2, pill_top - 21, pill, BOLD, size, white, "center")

    # Bottom left: modules, date and release.
    _chips(c, [m["title_uz"] for m in modules])
    releases = sorted({m["release"] for m in modules if m.get("release")})
    issued = clock.local_date(cert.issued_at).strftime("%d.%m.%Y")
    footer = f"{both('pdf.issued')}: {issued}"
    if releases:
        footer += f" · {t('uz', 'pdf.release', codes=', '.join(releases))}"
    _text(c, MARGIN, 56, footer, REGULAR, 9, GREY)

    # Signature.
    c.setStrokeColor(INK)
    c.line(504, 89, 654, 89)
    if snap.get("signatory"):
        _text(c, 579, 76, snap["signatory"], REGULAR, 10, INK, "center")
    _text(c, 579, 63, t("uz", "pdf.signatory_title"), REGULAR, 9.5, INK, "center")
    _text(c, 579, 51, t("ru", "pdf.signatory_title"), REGULAR, 8.5, GREY, "center")

    # Verification: QR with number and code, plus the code in print for typing in.
    qr_x, qr_y, qr_size = 690, 88, 72
    c.setLineWidth(0.6)
    c.rect(qr_x - 4, qr_y - 4, qr_size + 8, qr_size + 8)
    _qr(c, certificates.verify_url(cert), qr_x, qr_y, qr_size)
    host = urlsplit(settings.public_base_url).netloc or settings.public_base_url
    _text(c, qr_x + qr_size / 2, 71, both("pdf.verify"), REGULAR, 8.5, GREY, "center")
    _text(c, qr_x + qr_size / 2, 61, f"{host}/verify", REGULAR, 8.5, GREY, "center")
    code = f"{both('pdf.code')}: {cert.verify_code}"
    _text(c, qr_x + qr_size / 2, 50, code, SEMIBOLD, 8, INK, "center")

    c.showPage()
    c.save()
    return buf.getvalue()
