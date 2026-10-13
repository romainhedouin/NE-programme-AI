from scripts.scrape_programme import (
    drop_duplicates,
    extract_chunks,
    is_boilerplate,
    strip_link_label,
)

BASE = "https://www.unenouvelleenergie.fr"

QUESTION = """<main><h1>Que ferait David Lisnard des 200 milliards d'économies ?</h1>
<h2>Une règle de partage, annoncée avant les économies</h2>
<p>L'ordre compte : la répartition est annoncée en même temps que l'effort.</p>
<p>D’après David Lisnard, <cite>Meeting de Saint-Raphaël</cite>, 4 juillet 2026 · <a>voir l’intervention</a></p>
<p>D’après David Lisnard, Livre, sixième partie</p>
<h2>Ce que David Lisnard a dit</h2>
<blockquote>soixante pour cent aux gens qui travaillent</blockquote>
<p>Le sujet en entier : <a>la page de programme</a> .</p></main>"""

INDEX = """<main><h1>Dette et dépense publique : les positions de David Lisnard</h1>
<p>Dette, dépense publique, économies : où passe l'argent public et ce que propose Lisnard.</p>
<h2>Les questions, une par une</h2>
<ul><li><a>Que propose David Lisnard face à la dette publique ?</a></li>
<li><a>Quelles économies propose David Lisnard ?</a></li></ul>
<p>Pour approfondir : <a>le programme sur ce sujet</a> .</p></main>"""

HUB = """<main><h1>Notre programme</h1>
<h2>Découvrez nos actualités</h2>
<article><h3>« Mon devoir impératif, c'est de faire gagner la France »</h3>
<p>Politique 24.09.2025 « Mon devoir impératif, c'est de faire gagner la France » Découvrir →</p></article>
<article><h3>Pas de pourboire pour l'Etat</h3>
<p>Economie 25.09.2025 Pas de pourboire pour l'Etat Découvrir →</p></article>
<h2>1. Être maître de notre destin</h2>
<p>Les menaces sur la souveraineté française et les libertés des Français sont identifiées.</p></main>"""


def texts(html, path="/questions/x/"):
    return [c["text"] for c in extract_chunks(BASE + path, html)]


def test_cta_et_label_de_lien_ne_sont_pas_indexes():
    out = texts(QUESTION)
    assert not any(t.startswith("Le sujet en entier") for t in out)
    assert not any("voir l’intervention" in t for t in out)


def test_provenance_et_contenu_restent():
    out = texts(QUESTION)
    assert "D’après David Lisnard, Meeting de Saint-Raphaël , 4 juillet 2026" in out
    assert "D’après David Lisnard, Livre, sixième partie" in out
    assert "L'ordre compte : la répartition est annoncée en même temps que l'effort." in out
    assert "soixante pour cent aux gens qui travaillent" in out


def test_index_de_questions_ne_garde_que_l_intro():
    assert texts(INDEX) == [
        "Dette, dépense publique, économies : où passe l'argent public et ce que propose Lisnard."
    ]


def test_vignettes_du_hub_ecartees():
    assert texts(HUB, "/notre-programme/") == [
        "Les menaces sur la souveraineté française et les libertés des Français sont identifiées."
    ]


def test_is_boilerplate_ne_touche_pas_au_vrai_contenu():
    assert is_boilerplate("Le sujet en entier : la page de programme .")
    assert is_boilerplate("Pour approfondir : le programme sur ce sujet .")
    assert is_boilerplate("Le livre noir de la bureaucratie Découvrir →")
    assert not is_boilerplate("Pour approfondir : " + "la réforme proposée prévoit " * 5)
    assert not is_boilerplate("Découvrir la réforme de l'école suppose de revenir aux savoirs fondamentaux.")


def test_strip_link_label():
    assert strip_link_label("D’après David Lisnard, RMC , 21 avril 2026 · voir l’intervention") == (
        "D’après David Lisnard, RMC , 21 avril 2026"
    )
    assert strip_link_label("Une phrase sans label.") == "Une phrase sans label."


def test_drop_duplicates_garde_la_premiere_page_et_les_sources():
    def chunk(text, url):
        return {"text": text, "url": url}

    seen = set()
    page_a = drop_duplicates([chunk("Intro identique sur deux pages.", "a"), chunk("D’après David Lisnard, RMC , 21 avril 2026", "a")], seen)
    page_b = drop_duplicates([chunk("Intro identique sur deux pages.", "b"), chunk("D’après David Lisnard, RMC , 21 avril 2026", "b")], seen)
    assert len(page_a) == 2
    assert [c["text"] for c in page_b] == ["D’après David Lisnard, RMC , 21 avril 2026"]
