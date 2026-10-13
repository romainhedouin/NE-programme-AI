import json

from app import retrieve

QUERIES = [
    "Quelle est la position sur l'IA ?",
    "nucléaire énergie électricité",
    "sécurité police insécurité",
    "impôts fiscalité réduction dépenses publiques",
    "éducation école enseignants",
    "santé hôpital médecins déserts médicaux",
    "retraites âge de départ",
    "intelligence artificielle numérique souveraineté",
]


class CountingVocab(dict):
    scans = 0

    def __iter__(self):
        self.scans += 1
        return super().__iter__()


def long_query(n):
    vocab = sorted({t[:4] for t in retrieve._lexical_index()["idf"] if len(t) >= 5 and t.isalpha()})
    return " ".join(vocab[:: len(vocab) // n][:n])


def test_requete_longue_ne_balaie_pas_le_vocabulaire_par_token(monkeypatch):
    query = long_query(200)
    assert len(set(retrieve.tokenize(query))) > 100
    index = retrieve._lexical_index()
    counting = CountingVocab(index["idf"])
    monkeypatch.setattr(retrieve, "_lexical_index", lambda: {**index, "idf": counting})

    retrieve._lexical_ranked(query)

    assert counting.scans <= retrieve.MAX_QUERY_TOKENS


def test_requete_longue_equivaut_a_ses_premiers_tokens():
    query = long_query(200)
    first = list(dict.fromkeys(retrieve.tokenize(query)))[: retrieve.MAX_QUERY_TOKENS]

    assert retrieve._lexical_ranked(query) == retrieve._lexical_ranked(" ".join(first))


def test_requetes_courantes_inchangees(monkeypatch):
    expected = {q: retrieve._lexical_ranked(q) for q in QUERIES}
    monkeypatch.setattr(retrieve, "MAX_QUERY_TOKENS", 10**6)

    for q in QUERIES:
        assert retrieve._lexical_ranked(q) == expected[q]
        assert len(set(retrieve.tokenize(q))) <= 24
