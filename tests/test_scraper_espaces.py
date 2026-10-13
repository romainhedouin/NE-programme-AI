import re

from scripts.scrape_programme import extract_chunks

HTML = """
<html><body><main>
<h1>Titre de la page</h1>
<h2>Section de l’<em>énergie</em></h2>
<p>Nous voulons <a href="#">alléger la formation</a>, la <strong>perception</strong> et l’<em>allégement</em> des normes (voir <a href="#">la page de programme</a>).</p>
<p>Première ligne de ce paragraphe assez longue<br>deuxième ligne de ce paragraphe assez longue.</p>
<ul>
<li>Premier point de la liste, suffisamment long pour être gardé</li>
<li>Parent assez long pour être gardé<ul><li>Enfant lui aussi assez long pour être gardé</li></ul></li>
<li><div>Premier bloc contenu dans un item de liste</div><div>Second bloc contenu dans un item de liste</div></li>
</ul>
<blockquote><p>Premier paragraphe de la citation assez long</p><p>Second paragraphe de la citation assez long</p></blockquote>
</main></body></html>
"""


def texts() -> list[str]:
    return [c["text"] for c in extract_chunks("https://example.test/notre-programme/x/", HTML)]


def test_pas_d_espace_parasite_autour_des_balises_inline():
    chunks = extract_chunks("https://example.test/notre-programme/x/", HTML)
    assert chunks[0]["section"] == "Section de l’énergie"
    assert (
        "Nous voulons alléger la formation, la perception et l’allégement des normes "
        "(voir la page de programme)."
    ) in texts()
    assert not [t for t in texts() if re.search(r" [,.]|’ \w", t)]


def test_les_mots_ne_sont_pas_colles_entre_blocs():
    t = texts()
    assert "Première ligne de ce paragraphe assez longue deuxième ligne de ce paragraphe assez longue." in t
    assert "Parent assez long pour être gardé Enfant lui aussi assez long pour être gardé" in t
    assert "Premier bloc contenu dans un item de liste Second bloc contenu dans un item de liste" in t
    assert (
        "Premier paragraphe de la citation assez long Second paragraphe de la citation assez long"
    ) in t
