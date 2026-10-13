import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import scrape_programme as sp  # noqa: E402

LEGIT = "https://www.unenouvelleenergie.fr/questions/securite/"
SITEMAP = f"""<urlset>
<url><loc>{LEGIT}</loc></url>
<url><loc>https://evil.example/questions/phishing/</loc></url>
<url><loc>http://www.unenouvelleenergie.fr/questions/http/</loc></url>
<url><loc>https://www.unenouvelleenergie.fr.evil.example/questions/suffixe/</loc></url>
<url><loc>https://www.unenouvelleenergie.fr@evil.example/questions/userinfo/</loc></url>
<url><loc>https://www.unenouvelleenergie.fr:8443/questions/port/</loc></url>
</urlset>"""


def test_sitemap_ne_garde_que_l_hote_officiel_en_https():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=SITEMAP)

    with sp.make_client(transport=httpx.MockTransport(handler)) as client:
        urls = sp.sitemap_urls(client)

    assert urls == [f"{sp.BASE}/notre-programme/", LEGIT]


def test_redirection_vers_un_autre_hote_refusee():
    vus: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        vus.append(request.url.host)
        if request.url.host == "www.unenouvelleenergie.fr":
            return httpx.Response(302, headers={"Location": "https://evil.example/x"})
        return httpx.Response(200, text="pwned")

    with sp.make_client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(Exception):
            sp.fetch(client, LEGIT)

    assert "evil.example" not in vus
