from pathlib import Path
from typing import Literal

import pytest
from pytest_httpserver import HTTPServer


@pytest.mark.asyncio
async def test_fetch_wikipedia(httpserver: HTTPServer):
    from agent_penny.capabilities.web import WebResponse, web_fetch

    # Mock Wikipedia response since Wikipedia is blocking Github tests
    httpserver.expect_request("/wiki/Miss_Moneypenny").respond_with_data(
        Path("tests/wikipedia_Miss_Moneypenny.html").read_text(),
        200,
        content_type="text/html",
    )

    result = await web_fetch(
        httpserver.url_for("/wiki/Miss_Moneypenny"), format="markdown"
    )

    assert result
    assert isinstance(result, WebResponse)
    assert result.success
    assert result.status_code == 200

    assert result.content
    content = result.content
    assert "secretary" in content.lower()
    assert "Lois Maxwell" in content
    assert "James Bond" in content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url,format,status_code,content",
    [
        args
        for format in ["raw", "markdown"]
        for args in [
            (
                "https://api.github.com/repos/dgootman/agent-penny",
                format,
                200,
                '"name": "agent-penny"',
            ),
            ("https://httpbin.org/html", format, 200, "Herman Melville - Moby-Dick"),
            ("https://httpbin.org/json", format, 200, "Sample Slide Show"),
            ("https://httpbin.org/xml", format, 200, "Wake up to WonderWidgets!"),
            ("https://httpbin.org/encoding/utf8", format, 200, "STARGΛ̊TE SG-1"),
        ]
    ],
)
async def test_fetch_response(
    url: str, format: Literal["raw", "markdown"], status_code: int, content: str
):
    is_success = 200 <= status_code < 300

    from agent_penny.capabilities.web import WebResponse, web_fetch

    result = await web_fetch(url, format=format)

    assert result
    assert isinstance(result, WebResponse)
    assert result.success == is_success
    assert result.status_code == status_code
    assert content in result.content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url,timeout,error",
    [
        ("https://httpbin.org/delay/1", 0.1, "TimeoutError"),
        ("https://no-such.example.org", 5, "DnsLookupError"),
        ("https://expired.badssl.com", 5, "CertificateError"),
        ("https://wrong.host.badssl.com", 5, "CertificateError"),
        ("https://self-signed.badssl.com", 5, "CertificateError"),
        ("https://untrusted-root.badssl.com", 5, "CertificateError"),
        # TODO: Figure out how to enable revocation and pinning
        # ("https://revoked.badssl.com", 5, "CertificateError"),
        # ("https://pinning-test.badssl.com", 5, "CertificateError"),
    ],
)
async def test_fetch_error(url: str, timeout: float, error: str):
    from agent_penny.capabilities.web import WebError, web_fetch

    result = await web_fetch(url, timeout=timeout)

    assert result
    assert isinstance(result, WebError)
    assert result.error == error
