"""What the free-text parser may and may not conclude.

The parser only ever *narrows* a search, so every test here is really about the
same thing: it must claim a field when the shape is unmistakable, and it must
refuse to guess the rest. A wrong guess here silently steers the whole search at
the wrong person, and nothing downstream can recover from that.
"""

from __future__ import annotations

import pytest

from app.discovery.brief.gender import gender_from_bio, parse_gender_token, parse_gender_word
from app.discovery.brief.parse import parse_brief
from app.discovery.types import EntityType, Gender


class TestKnownProfiles:
    def test_a_bare_platform_url_becomes_a_known_profile(self) -> None:
        brief = parse_brief("Eylul Akduman, instagram.com/eylulakduman")

        assert [(p.platform, p.username) for p in brief.known_profiles] == [("instagram", "eylulakduman")]
        assert brief.name == "Eylul Akduman", "the URL must not be swallowed into the name"

    def test_a_full_url_with_scheme_and_trailing_slash_resolves_the_same(self) -> None:
        brief = parse_brief("Eylul Akduman, https://www.instagram.com/eylulakduman/")

        assert brief.known_profiles[0].canonical_url == "https://www.instagram.com/eylulakduman/"

    def test_a_non_profile_url_is_surfaced_rather_than_matched(self) -> None:
        """The bug class `urlmatch` exists for: `roblox.com/users/1` is not an X profile.

        It must not become a known profile, and it must not be silently dropped
        either — the user said something, and they need to see it was not used.
        """
        brief = parse_brief("Jane Doe, roblox.com/users/1")

        assert brief.known_profiles == ()
        assert "roblox.com/users/1" in brief.unparsed

    def test_a_second_url_for_one_platform_is_surfaced_not_silently_preferred(self) -> None:
        brief = parse_brief("Ayse, instagram.com/first, instagram.com/second")

        assert [p.username for p in brief.known_profiles] == ["first"]
        assert any("second" in item for item in brief.unparsed)

    def test_several_platforms_all_seed_the_same_search(self) -> None:
        brief = parse_brief("Ali Veli, github.com/aliveli, x.com/aliveli2, aliveli.dev")

        assert brief.pinned_platforms == {"github": "aliveli", "x": "aliveli2"}
        assert brief.domain == "aliveli.dev", "a host that is not a platform is the target's own site"
        assert brief.seed_usernames() == ("aliveli", "aliveli2")


class TestGender:
    @pytest.mark.parametrize("word", ["kız", "kadın", "bayan", "female", "woman", "k"])
    def test_a_standalone_female_word_is_read(self, word: str) -> None:
        assert parse_brief(f"Eylul Akduman, {word}").gender is Gender.FEMALE

    @pytest.mark.parametrize("word", ["erkek", "oğlan", "male", "man", "e"])
    def test_a_standalone_male_word_is_read(self, word: str) -> None:
        assert parse_brief(f"Yigit Erdogan, {word}").gender is Gender.MALE

    def test_a_lone_segment_is_a_name_even_when_it_contains_a_gender_word(self) -> None:
        """ "Adam Smith" is a person, not "a man called Smith".

        Without this rule the generous vocabulary ate the first name and set a
        gender the user never stated — which then filtered the search.
        """
        brief = parse_brief("Adam Smith")

        assert brief.name == "Adam Smith"
        assert brief.gender is Gender.UNKNOWN

    def test_an_initial_is_not_a_gender(self) -> None:
        brief = parse_brief("Ahmet K. Yilmaz, erkek")

        assert brief.name == "Ahmet K. Yilmaz", "the single-letter vocabulary must not eat an initial"
        assert brief.gender is Gender.MALE

    @pytest.mark.parametrize("name", ["Deniz Kaya", "Evren Yilmaz", "Yagmur Ozgan", "Ozgur Demir"])
    def test_a_unisex_given_name_never_implies_a_gender(self, name: str) -> None:
        """Turkish is full of these. Guessing would reject the target themselves."""
        assert parse_brief(f"{name}, instagram.com/x_y_z").gender is Gender.UNKNOWN

    @pytest.mark.parametrize("word", ["Adam", "K.", "Deniz", ""])
    def test_the_strict_token_vocabulary_refuses_name_shaped_words(self, word: str) -> None:
        assert parse_gender_token(word) is Gender.UNKNOWN

    def test_an_explicit_key_wins_over_the_lexicon(self) -> None:
        assert parse_brief("Someone, cinsiyet: kadın").gender is Gender.FEMALE


class TestBioMarkers:
    @pytest.mark.parametrize("bio", ["she/her", "Mrs. Akduman", "anne ve yazılımcı", "photographer, her work"])
    def test_an_explicit_female_marker_is_read(self, bio: str) -> None:
        assert gender_from_bio(bio) is Gender.FEMALE

    @pytest.mark.parametrize("bio", ["he/him", "Mr. Erdogan", "baba", "his portfolio"])
    def test_an_explicit_male_marker_is_read(self, bio: str) -> None:
        assert gender_from_bio(bio) is Gender.MALE

    @pytest.mark.parametrize(
        "bio",
        [
            "",
            "photographer and traveller",
            "there is another history here",  # 'her' and 'his' as substrings
            "she and he built this together",  # both sides fire
            "Istanbul | design | coffee",
        ],
    )
    def test_silence_and_ambiguity_are_never_a_claim(self, bio: str) -> None:
        """Most bios say nothing about gender, and that must never read as disagreement."""
        assert gender_from_bio(bio) is Gender.UNKNOWN


class TestOtherFields:
    def test_labelled_fields_in_turkish_and_english(self) -> None:
        brief = parse_brief("Yigit Erdogan, şehir: İstanbul, okul: Boğaziçi, work: Getir")

        assert (brief.location, brief.school, brief.employer) == ("İstanbul", "Boğaziçi", "Getir")

    def test_handles_and_emails_are_claimed_by_shape(self) -> None:
        brief = parse_brief("Yigit Erdogan, @Yigtwxx, yigit@example.com")

        assert brief.usernames == ("Yigtwxx",)
        assert brief.email == "yigit@example.com"
        assert brief.name == "Yigit Erdogan"

    def test_the_first_value_for_a_field_wins(self) -> None:
        brief = parse_brief("X Y, sehir: Istanbul, sehir: Ankara")

        assert brief.location == "Istanbul", "a later value is not a correction, it is a second claim"

    def test_leftovers_are_reported_rather_than_forced_into_a_field(self) -> None:
        brief = parse_brief("Jane Doe, likes hiking, sehir: Oslo")

        assert brief.unparsed == ("likes hiking",)
        assert brief.location == "Oslo"


class TestShape:
    def test_a_plain_name_produces_an_empty_brief(self) -> None:
        brief = parse_brief("Jane Doe")

        assert brief.is_empty, "nothing was stated, so nothing may be constrained"
        assert brief.name == "Jane Doe"

    def test_a_query_that_parses_away_to_nothing_keeps_its_text_as_the_name(self) -> None:
        brief = parse_brief("instagram.com/eylulakduman")

        assert brief.name == "instagram.com/eylulakduman", "an empty name would make the search meaningless"
        assert brief.known_profiles[0].username == "eylulakduman"

    def test_empty_input_never_raises(self) -> None:
        assert parse_brief("").name == ""
        assert parse_brief("   ").is_empty

    def test_the_entity_type_is_carried_through(self) -> None:
        assert parse_brief("Acme Robotics", entity=EntityType.COMPANY).entity is EntityType.COMPANY

    def test_the_worked_example_end_to_end(self) -> None:
        """The exact query this feature was built for."""
        brief = parse_brief("Eylul Akduman, kız, instagram.com/eylulakduman")

        assert brief.name == "Eylul Akduman"
        assert brief.gender is Gender.FEMALE
        assert brief.pinned_platforms == {"instagram": "eylulakduman"}
        assert brief.seed_usernames() == ("eylulakduman",)
        assert not brief.is_empty
        assert brief.unparsed == ()


def test_parse_gender_word_reads_a_pronoun_pair() -> None:
    assert parse_gender_word("she/her") is Gender.FEMALE
    assert parse_gender_word("he/him") is Gender.MALE
