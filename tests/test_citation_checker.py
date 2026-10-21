from app.services.citation_checker import check_citations


def test_all_valid():
    r = check_citations("AI improves diagnosis accuracy in radiology [p1]. Costs fall [p2].", {"p1", "p2"})
    assert r["passed"] and r["n_invalid"] == 0


def test_missing_id_detected():
    r = check_citations("AI improves diagnosis accuracy in radiology [p9].", {"p1"})
    assert not r["passed"]
    assert r["issues"][0]["missing_ids"] == ["p9"]


def test_uncited_long_claim_flagged():
    r = check_citations("Deep learning has dramatically improved diagnostic accuracy in many domains.", set())
    assert r["n_uncited"] == 1
