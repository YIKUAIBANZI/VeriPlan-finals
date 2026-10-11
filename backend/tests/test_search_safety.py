import pytest

from app.providers.search_safety import (
    canonicalize_public_https_url,
    host_matches_domain,
    normalize_domains,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/article",
        "ftp://example.com/article",
        "https://user:password@example.com/article",
        "https://localhost/article",
        "https://api.localhost/article",
        "https://service.local/article",
        "https://intranet/article",
        "https://127.0.0.1/article",
        "https://[::1]/article",
        "https://2130706433/article",
        "https://0177.0.0.1/article",
        "https:///article",
        "https://example.com:99999/article",
        "https://example.com:not-a-port/article",
        "https://example.com/article\nignored",
    ],
)
def test_canonical_url_rejects_non_public_or_ambiguous_targets(url):
    with pytest.raises(ValueError):
        canonicalize_public_https_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://blocked.example/article",
        "https://cdn.blocked.example/article",
    ],
)
def test_canonical_url_rejects_blocked_domains_and_subdomains(url):
    with pytest.raises(ValueError, match="blocked"):
        canonicalize_public_https_url(
            url,
            blocked_domains=("blocked.example",),
        )


def test_canonical_url_normalizes_identity_without_dropping_content_parameters():
    assert canonicalize_public_https_url(
        "https://Example.COM:443/articles?id=42&utm_source=mail&keep=A"
        "&gclid=tracking#section"
    ) == "https://example.com/articles?id=42&keep=A"


def test_canonical_url_idna_normalizes_hosts_and_preserves_parameter_order():
    assert canonicalize_public_https_url(
        "https://BÜCHER.example/路径?second=2&fbclid=x&first=1"
    ) == "https://xn--bcher-kva.example/路径?second=2&first=1"


def test_normalize_domains_trims_idna_converts_and_deduplicates_in_order():
    assert normalize_domains(
        (" Example.COM ", "bücher.example", "example.com", "")
    ) == ("example.com", "xn--bcher-kva.example")


@pytest.mark.parametrize(
    "domain",
    [
        "https://example.com",
        "example.com/path",
        "example.com:443",
        "*.example.com",
        "127.0.0.1",
        "localhost",
        "service.local",
        "com",
    ],
)
def test_normalize_domains_rejects_non_domain_configuration(domain):
    with pytest.raises(ValueError):
        normalize_domains((domain,))


def test_domain_matching_includes_subdomains_but_not_suffix_lookalikes():
    assert host_matches_domain("example.com", "example.com") is True
    assert host_matches_domain("api.example.com", "example.com") is True
    assert host_matches_domain("evilexample.com", "example.com") is False
