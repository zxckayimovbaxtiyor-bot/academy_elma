"""Certificate PDF (A4, uz + ru, QR) and the public verification page."""

from __future__ import annotations

from sqlalchemy import select

from app.config import settings
from app.models import Certificate
from app.models.enums import CertificateKind
from app.pdf import certificate as pdf
from tests.factories import (
    complete_lesson,
    login,
    make_learner,
    make_wave,
    pass_test,
    ready_module,
)


def _certified(db, client, reference) -> tuple[Certificate, Certificate]:
    """A learner assigned only Core passes it: module and operator certificates."""
    core = reference.modules["CORE"]
    make_wave(db, [reference.tashkent], {})
    [(_, version)] = ready_module(db, core)
    learner = make_learner(db, reference)
    complete_lesson(db, learner, version)
    login(client, learner)
    pass_test(db, client, core.id)
    rows = db.scalars(select(Certificate).where(Certificate.user_id == learner.id))
    certs = {c.kind: c for c in rows}
    return certs[CertificateKind.module], certs[CertificateKind.operator]


def test_pdf_is_the_owners_and_drawn_once(db, client, make_client, reference, clock, media_root):
    module_cert, operator = _certified(db, client, reference)
    url = f"/api/v1/me/certificates/{module_cert.number}/pdf"

    first = client.get(url)
    assert first.status_code == 200 and first.headers["content-type"] == "application/pdf"
    assert first.content.startswith(b"%PDF-") and len(first.content) > 10_000
    assert f'filename="{module_cert.number}.pdf"' in first.headers["content-disposition"]
    cached = media_root / module_cert.pdf_path
    assert module_cert.pdf_path.startswith("certs/") and cached.is_file()
    assert client.get(url).content == first.content  # served from the cache
    operator_pdf = client.get(f"/api/v1/me/certificates/{operator.number}/pdf")
    assert operator_pdf.status_code == 200 and operator_pdf.content != first.content

    stranger = make_client()
    login(stranger, make_learner(db, reference))
    hidden = stranger.get(url)
    assert hidden.status_code == 404 and hidden.json()["error"]["code"] == "certificate.not_found"
    assert make_client().get(url).status_code == 401


def test_qr_code_points_to_the_verification_page_with_the_code(db, client, reference, clock,
                                                               monkeypatch):  # fmt: skip
    module_cert, _ = _certified(db, client, reference)
    seen = []
    real = pdf.QrCodeWidget

    def spy(value, **kwargs):
        seen.append(value)
        return real(value, **kwargs)

    monkeypatch.setattr(pdf, "QrCodeWidget", spy)
    pdf.render(module_cert)
    expected = f"{settings.public_base_url}/verify/{module_cert.number}?c={module_cert.verify_code}"
    assert seen == [expected]


def test_verification_needs_the_number_and_the_printed_code(db, client, make_client, reference,
                                                            clock):  # fmt: skip
    module_cert, operator = _certified(db, client, reference)
    public = make_client()  # nobody logged in

    resp = public.get(f"/api/v1/verify/{module_cert.number}", params={"c": module_cert.verify_code})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["kind"], body["status"], body["number"]) == ("module", "valid", module_cert.number)
    assert body["holder"] == module_cert.snapshot["holder"]["full_name"]
    assert body["branch"]["code"] == "01-101" and body["region"]["code"] == "01"
    assert [m["code"] for m in body["modules"]] == ["CORE"]
    assert "employee_id" not in resp.text  # the page shows no more than the certificate

    code = operator.verify_code.lower()  # typed in by hand
    lower = public.get(f"/api/v1/verify/{operator.number}", params={"c": code})
    assert lower.status_code == 200 and lower.json()["kind"] == "operator"
    for number, code in (
        (module_cert.number, "WRONGCODE1"),
        (module_cert.number, ""),
        ("YO-2026-999999", module_cert.verify_code),
    ):
        miss = public.get(f"/api/v1/verify/{number}", params={"c": code})
        assert miss.status_code == 404 and miss.json()["error"]["code"] == "certificate.not_found"


def test_superseded_certificate_says_so(db, client, make_client, reference, clock):
    module_cert, _ = _certified(db, client, reference)
    module_cert.superseded_at = clock.now
    db.flush()
    resp = make_client().get(
        f"/api/v1/verify/{module_cert.number}", params={"c": module_cert.verify_code}
    )
    assert resp.json()["status"] == "superseded"
