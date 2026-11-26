"""Saved-link parsing: what is stored, what counts as a duplicate, what is refused."""

import pytest

from app.core.errors import BadRequest
from app.modules.library.urls import parse

VIDEO = "https://youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.mark.parametrize(
    ("raw", "url", "key"),
    [
        ("example.com/post", "https://example.com/post", "https://example.com/post"),
        ("  HTTPS://Example.COM/Post  ", "https://example.com/Post", "https://example.com/Post"),
        ("http://www.example.com:80/a/", "http://www.example.com/a/", "https://example.com/a"),
        ("https://example.com:443/", "https://example.com/", "https://example.com"),
        ("https://example.com:8443/a", "https://example.com:8443/a", "https://example.com:8443/a"),
        (
            "https://example.com/a?utm_source=x&b=2&fbclid=y&a=1#section",
            "https://example.com/a?utm_source=x&b=2&fbclid=y&a=1#section",
            "https://example.com/a?a=1&b=2",
        ),
        ("https://bücher.de/x", "https://bücher.de/x", "https://xn--bcher-kva.de/x"),
        (
            "http://[2001:db8::1]:8080/x/",
            "http://[2001:db8::1]:8080/x/",
            "https://[2001:db8::1]:8080/x",
        ),
        ("localhost:3000/notes", "https://localhost:3000/notes", "https://localhost:3000/notes"),
    ],
)
def test_links_keep_their_spelling_and_get_a_normalised_key(raw: str, url: str, key: str) -> None:
    saved = parse(raw)
    assert (saved.url, saved.key, saved.kind) == (url, key, "link")


def test_spellings_of_one_page_share_a_key() -> None:
    keys = {
        parse(u).key
        for u in (
            "https://example.com/a?b=2&a=1",
            "http://www.example.com/a/?a=1&b=2&utm_medium=email",
            "example.com/a?a=1&b=2#top",
        )
    }
    assert len(keys) == 1


def test_internationalised_domain_spellings_match() -> None:
    assert parse("https://bücher.de/x").key == parse("https://xn--bcher-kva.de/x").key
    assert parse("https://bücher.de/x").host == "bücher.de"


@pytest.mark.parametrize(
    "raw",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?feature=share&v=dQw4w9WgXcQ&t=42",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ?si=abc",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "https://www.youtube.com/live/dQw4w9WgXcQ",
    ],
)
def test_youtube_variants_are_one_video(raw: str) -> None:
    saved = parse(raw)
    assert (saved.kind, saved.key, saved.host) == ("video", VIDEO, "youtube.com")
    assert saved.url.startswith("https://")


@pytest.mark.parametrize(
    "raw",
    [
        "https://www.youtube.com/",
        "https://www.youtube.com/@channel",
        "https://www.youtube.com/watch?v=short",
        "https://youtu.be/",
        "https://notyoutube.com/watch?v=dQw4w9WgXcQ",
    ],
)
def test_other_youtube_pages_are_plain_links(raw: str) -> None:
    assert parse(raw).kind == "link"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "mailto:someone@example.com",
        "file:///etc/passwd",
        "ftp://example.com/file",
        "https://user:pass@example.com/",
        "https://user@example.com/",
        "https://example.com:99999/",
        "https://exa mple.com/",
        "https://example.com/\x00",
        "https://example.com/" + "a" * 2048,
        "https://",
    ],
)
def test_unsafe_or_malformed_addresses_are_refused(raw: str) -> None:
    with pytest.raises(BadRequest) as error:
        parse(raw)
    assert error.value.code == "library_url_invalid"
