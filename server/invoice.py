"""Invoices (Rechnungen) for ad bookings, as a one-page PDF written with the standard library.

Your business details come from the DMG_INVOICE_* settings (see server/README.md). Prices are
treated as the total the advertiser pays, VAT included. Without your name, address and tax
number the PDF says "Muster" (sample), because it wouldn't be a valid German invoice.
"""

import os
import time

# Helvetica character widths (per 1000 units of font size) for ASCII; other characters ~556.
WIDTHS = dict(zip(
    " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~",
    [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, *[556] * 10,
     278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667,
     556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278,
     469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
     556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584],
))
PAY_DAYS = 14


class Seller:
    def __init__(self, env=os.environ):
        self.name = env.get("DMG_INVOICE_NAME", "").strip()
        self.address = [x.strip() for x in env.get("DMG_INVOICE_ADDRESS", "").split("|") if x.strip()]
        self.email = env.get("DMG_INVOICE_EMAIL", "").strip()
        self.tax_id = env.get("DMG_INVOICE_TAX_ID", "").strip()
        self.bank = env.get("DMG_INVOICE_BANK", "").strip()
        try:
            self.vat = float(env.get("DMG_INVOICE_VAT", "19"))
        except ValueError:
            self.vat = 19.0

    @property
    def complete(self) -> bool:
        return bool(self.name and self.address and self.tax_id)


def number(n: int, issued_at: float) -> str:
    return f"DMG-{time.localtime(issued_at).tm_year}-{n:04d}"


def eur(cents: int) -> str:
    return f"{cents / 100:,.2f} €".replace(",", "_").replace(".", ",").replace("_", ".")


def day(t: float) -> str:
    return time.strftime("%d.%m.%Y", time.localtime(t))


def split_vat(gross: int, rate: float) -> tuple[int, int]:
    """(net, vat) in cents for a price that includes VAT."""
    net = round(gross * 100 / (100 + rate))
    return net, gross - net


def clean_address(text: str) -> str:
    """The advertiser's billing address: at most 5 lines of 60 characters."""
    lines = [" ".join(x.split())[:60] for x in text.replace("\r", "").split("\n")]
    return "\n".join([x for x in lines if x][:5])


class Canvas:
    """Just enough PDF: Helvetica text and thin lines on one A4 page."""

    def __init__(self):
        self.ops = []

    @staticmethod
    def width(s: str, size: float, bold: bool = False) -> float:
        return sum(WIDTHS.get(ch, 556) for ch in s) * size / 1000 * (1.05 if bold else 1)

    def text(self, x: float, y: float, s: str, size: float = 10, bold: bool = False):
        raw = s.encode("cp1252", "replace").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
        self.ops.append(b"BT /F%d %g Tf %.2f %.2f Td (" % (2 if bold else 1, size, x, y) + raw + b") Tj ET")

    def right(self, x: float, y: float, s: str, size: float = 10, bold: bool = False):
        self.text(x - self.width(s, size, bold), y, s, size, bold)

    def line(self, x1: float, y1: float, x2: float, y2: float):
        self.ops.append(b"0.6 w %.2f %.2f m %.2f %.2f l S" % (x1, y1, x2, y2))

    def wrap(self, s: str, size: float, width: float) -> list[str]:
        lines, current = [], ""
        for word in s.split():
            test = f"{current} {word}".strip()
            if current and self.width(test, size) > width:
                lines.append(current)
                current = word
            else:
                current = test
        return lines + [current] if current else lines

    def render(self, title: str) -> bytes:
        stream = b"\n".join(self.ops)
        font = b"<< /Type /Font /Subtype /Type1 /BaseFont /%s /Encoding /WinAnsiEncoding >>"
        info = title.encode("cp1252", "replace").replace(b"(", b"").replace(b")", b"")
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            font % b"Helvetica",
            font % b"Helvetica-Bold",
            b"<< /Title (" + info + b") /Producer (Deutsch mit Geschichten) >>",
        ]
        out, offsets = bytearray(b"%PDF-1.4\n"), []
        for i, obj in enumerate(objects, 1):
            offsets.append(len(out))
            out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
        out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
        out += b"trailer\n<< /Size %d /Root 1 0 R /Info 7 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
            len(objects) + 1, xref)
        return bytes(out)


def render(c, inv, seller: Seller) -> bytes:
    """c: the campaign row, inv: the invoice row (number, address, issued_at)."""
    no = number(inv["number"], inv["issued_at"])
    test = (c["payment_ref"] or "").startswith("test-")
    pdf, left, right = Canvas(), 56, 539
    y = 786

    pdf.text(left, y, seller.name or "Deutsch mit Geschichten", 13, bold=True)
    for line in seller.address + [seller.email]:
        if line:
            y -= 14
            pdf.text(left, y, line, 9)
    if not seller.complete or test:
        pdf.right(right, 786, "MUSTER / SAMPLE", 13, bold=True)
        pdf.right(right, 772, "Testzahlung, keine gültige Rechnung" if test
                  else "Keine gültige Rechnung: Absenderangaben fehlen", 8)

    y = 680
    pdf.text(left, y + 14, "Rechnung an / Bill to", 8)
    for i, line in enumerate([c["business"], *inv["address"].split("\n"), c["email"]]):
        if line:
            pdf.text(left, y, line, 10, bold=i == 0)
            y -= 14

    facts = [("Rechnungsnummer", no), ("Rechnungsdatum", day(inv["issued_at"])),
             ("Buchung", f"#{c['id']}")]
    if seller.tax_id:
        facts.append(("Steuernummer / USt-IdNr.", seller.tax_id))
    for i, (label, value) in enumerate(facts):
        pdf.text(340, 680 - 14 * i, label, 8)
        pdf.right(right, 680 - 14 * i, value, 9, bold=i == 0)

    y = min(y, 680 - 14 * len(facts)) - 36
    pdf.text(left, y, "Rechnung", 18, bold=True)
    y -= 30
    pdf.text(left, y, "Leistung / Service", 8)
    pdf.right(right, y, "Betrag / Amount", 8)
    y -= 6
    pdf.line(left, y, right, y)
    y -= 16
    views = f"{c['views_target']:,}".replace(",", ".")
    pdf.text(left, y, f"Anzeige in der App „Deutsch mit Geschichten“: {views} Aufrufe", 10, bold=True)
    pdf.right(right, y, eur(c["price_cents"]), 10)
    levels = ", ".join(c["levels"].split(",")) if c["levels"] else "alle Lernenden"
    details = [f"Ad in the app: {c['views_target']:,} views",f"Anzeige: „{c['headline']}“",
               f"Zielgruppe / Audience: {levels}",
               "Leistungszeitraum: ab Freigabe der Anzeige bis zum Erreichen der Aufrufe"]
    for line in details:
        for part in pdf.wrap(line, 9, 360):
            y -= 13
            pdf.text(left, y, part, 9)
    y -= 12
    pdf.line(left, y, right, y)

    net, vat = split_vat(c["price_cents"], seller.vat) if seller.vat > 0 else (c["price_cents"], 0)
    rows = [("Nettobetrag / Net", eur(net))]
    if seller.vat > 0:
        rows.append((f"Umsatzsteuer {seller.vat:g} % / VAT".replace(".", ","), eur(vat)))
    for label, value in rows:
        y -= 16
        pdf.right(430, y, label, 9)
        pdf.right(right, y, value, 10)
    y -= 20
    pdf.right(430, y, "Gesamtbetrag / Total", 10, bold=True)
    pdf.right(right, y, eur(c["price_cents"]), 11, bold=True)

    y -= 40
    if c["paid_at"]:
        how = "Testzahlung" if test else "Karte (Stripe)" if (c["payment_ref"] or "").startswith("cs_") else "Überweisung"
        notes = [f"Bezahlt am {day(c['paid_at'])} per {how}. Vielen Dank!",
                 f"Paid on {day(c['paid_at'])}. Thank you!"]
    else:
        notes = [f"Bitte überweisen Sie den Betrag innerhalb von {PAY_DAYS} Tagen unter Angabe der "
                 f"Rechnungsnummer {no}.",
                 f"Please pay within {PAY_DAYS} days, quoting the invoice number."]
        if seller.bank:
            notes.append(seller.bank)
    if seller.vat <= 0:
        notes.append("Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.")
    for note in notes:
        for part in pdf.wrap(note, 9, right - left):
            pdf.text(left, y, part, 9)
            y -= 13

    pdf.line(left, 70, right, 70)
    footer = " · ".join(x for x in [seller.name, *seller.address, seller.tax_id] if x)
    for i, part in enumerate(pdf.wrap(footer, 7, right - left)[:2]):
        pdf.text(left, 58 - 9 * i, part, 7)
    return pdf.render(f"Rechnung {no}")
