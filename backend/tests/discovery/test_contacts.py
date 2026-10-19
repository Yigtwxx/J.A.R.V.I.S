"""What may be published as somebody's e-mail address or phone number.

The phone half is where the danger is. A run of digits with punctuation is
indistinguishable from a price, an invoice id, a date or a coordinate, and the
legacy extractor matched all four — so the rejection cases below are the point of
this file, not an afterthought to the acceptance ones.
"""

from __future__ import annotations

import pytest

from app.discovery.identity import contacts
from app.discovery.types import EvidenceKind

CONTACT_PAGE = "https://example.dev/iletisim"
PLAIN_PAGE = "https://example.dev/notes"


def _values(hits: list[contacts.ContactHit]) -> list[str]:
    return [hit.value for hit in hits]


class TestEmail:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("write to yigit@example.dev", "yigit@example.dev"),
            ("YIGIT@Example.DEV", "yigit@example.dev"),
            ("yigit+jobs@example.dev", "yigit+jobs@example.dev"),
            ("yigit [at] example [dot] dev", "yigit@example.dev"),
            ("yigit(at)example(dot)dev", "yigit@example.dev"),
            ("yigit AT example DOT dev", "yigit@example.dev"),
            ("yigit&#64;example.dev", "yigit@example.dev"),
        ],
    )
    def test_an_address_is_found_and_normalised(self, text: str, expected: str) -> None:
        hits = contacts.emails_from(text, source_url=PLAIN_PAGE)

        assert expected in _values(hits), f"expected {expected!r} from {text!r}, got {_values(hits)}"

    def test_plus_addressing_is_never_rewritten(self) -> None:
        """Two published facts, not one. Collapsing them prints an address the
        page never contained."""
        hits = contacts.emails_from("a: yigit+jobs@example.dev b: yigit@example.dev", source_url=PLAIN_PAGE)

        assert sorted(_values(hits)) == ["yigit+jobs@example.dev", "yigit@example.dev"]

    @pytest.mark.parametrize(
        "text",
        [
            "logo@2x.png",
            "noreply@example.dev",
            "no-reply@getir.com",
            "webmaster@example.dev",
            "youremail@domain.com",
            "user@yourdomain.com",
            "a1b2c3d4e5f60718293a4b5c6d7e8f90@sentry.wixpress.com",
            "ada@users.noreply.github.com",
        ],
    )
    def test_a_non_address_is_refused(self, text: str) -> None:
        assert contacts.emails_from(text, source_url=PLAIN_PAGE) == [], f"{text!r} must not be published"

    def test_a_mailto_href_is_read_without_its_query(self) -> None:
        hits = contacts.from_hrefs(["mailto:yigit@example.dev?subject=Hi%20there"], source_url=PLAIN_PAGE)

        assert _values(hits) == ["yigit@example.dev"]
        assert hits[0].extractor == "mailto"


class TestPhone:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("telefon: +90 532 123 45 67", "+905321234567"),
            ("tel +905321234567", "+905321234567"),
            ("iletişim 0532 123 45 67", "+905321234567"),
            ("gsm 0(532) 123 45 67", "+905321234567"),
            ("phone 0212 456 78 90", "+902124567890"),
            ("call (555) 123-4567", "5551234567"),
        ],
    )
    def test_a_dialable_number_beside_a_contact_word_is_kept(self, text: str, expected: str) -> None:
        hits = contacts.phones_from(text, source_url=PLAIN_PAGE)

        assert expected in _values(hits), f"expected {expected!r} from {text!r}, got {_values(hits)}"

    @pytest.mark.parametrize(
        "text",
        [
            "12.03.2024",
            "2024-2025 arası",
            "1.299,00 TL",
            "Sipariş No: 202412031234",
            "TR33 0006 1005 1978 6457 8413 26",
            "41.0082, 28.9784",
            "TCKN 12345678901",
            "ISBN 978-0-13-235088-4",
            "0000000000",
            "tel 1234567890",
            "vergi no 0532 123 45 67",
        ],
    )
    def test_something_that_is_not_a_phone_number_is_refused(self, text: str) -> None:
        assert contacts.phones_from(text, source_url=PLAIN_PAGE) == [], f"{text!r} must not be published as a phone"

    def test_a_bare_number_with_no_contact_word_is_below_the_floor(self) -> None:
        """A footer number with nothing calling it a phone is usually the host's."""
        assert contacts.phones_from("+90 532 123 45 67", source_url=PLAIN_PAGE) == []

    def test_a_contact_page_lifts_the_same_number_over_the_floor(self) -> None:
        hits = contacts.phones_from("+90 532 123 45 67", source_url=CONTACT_PAGE)

        assert _values(hits) == ["+905321234567"]
        assert hits[0].confidence >= contacts.PHONE_FLOOR

    def test_a_tel_href_needs_no_context_at_all(self) -> None:
        """The document declared the type; second-guessing it loses real numbers."""
        hits = contacts.from_hrefs(["tel:+90-532-123-45-67"], source_url=PLAIN_PAGE)

        assert _values(hits) == ["+905321234567"]
        assert hits[0].extractor == "tel"
        assert hits[0].confidence > contacts.PHONE_FLOOR

    def test_a_number_with_no_region_signal_stays_national(self) -> None:
        """Inventing a country code would publish a number nobody can dial."""
        hits = contacts.phones_from("call (555) 123-4567", source_url=PLAIN_PAGE)

        assert hits[0].value == "5551234567", "no +1 may be invented for a NANP-shaped number"
        assert hits[0].extractor.endswith("national")


class TestNormalisation:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("0532 123 45 67", "+905321234567"),
            ("0090 532 123 45 67", "+905321234567"),
            ("+90 (532) 123-45-67", "+905321234567"),
        ],
    )
    def test_a_turkish_number_reaches_e164(self, raw: str, expected: str) -> None:
        result = contacts.normalize_phone(raw)

        assert result is not None and result[0] == expected

    def test_normalising_is_idempotent(self) -> None:
        once = contacts.normalize_phone("0532 123 45 67")
        assert once is not None

        twice = contacts.normalize_phone(once[0])

        assert twice is not None and twice[0] == once[0]


class TestDedupe:
    def test_the_same_address_twice_on_one_site_collapses(self) -> None:
        hits = contacts.emails_from("yigit@example.dev and yigit@example.dev", source_url=PLAIN_PAGE)

        assert len(contacts.dedupe(hits)) == 1

    def test_the_same_address_on_two_sites_survives_as_two(self) -> None:
        """Two independent sites saying it is corroboration, and the scorer counts
        distinct source domains — collapsing them would erase the signal."""
        hits = contacts.emails_from("yigit@example.dev", source_url=PLAIN_PAGE) + contacts.emails_from(
            "yigit@example.dev", source_url="https://other.dev/about"
        )

        assert len(contacts.dedupe(hits)) == 2

    def test_the_most_confident_hit_wins(self) -> None:
        hits = contacts.from_hrefs(["mailto:yigit@example.dev"], source_url=PLAIN_PAGE) + contacts.emails_from(
            "yigit@example.dev", source_url=PLAIN_PAGE
        )

        deduped = contacts.dedupe(hits)

        assert len(deduped) == 1
        assert deduped[0].extractor == "mailto", "a declared address beats one scraped out of prose"


def test_every_hit_carries_its_provenance() -> None:
    """Invariant 4 for contacts: no source, no finding."""
    hits = contacts.emails_from("yigit@example.dev", source_url=CONTACT_PAGE) + contacts.phones_from(
        "tel: +90 532 123 45 67", source_url=CONTACT_PAGE
    )

    assert hits, "the fixture must actually produce hits"
    for hit in hits:
        assert hit.source_url, f"{hit} has no source"
        assert hit.extractor, f"{hit} has no extractor"
        assert 0.0 < hit.confidence <= 1.0, f"{hit} has an out-of-range confidence"
        assert hit.subject in ("email", "phone")
        assert hit.kind in (EvidenceKind.EMAIL, EvidenceKind.PHONE)
