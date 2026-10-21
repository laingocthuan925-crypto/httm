from app.services.quotes import quote_supported
from app.services.style_checks import analyze_style
from app.services.citations import render_citations, inline_cite, format_reference
from app.services.citation_checker import check_citations
from app.services.exporter import assemble, to_markdown
from app.services.openalex import rebuild_abstract, norm_doi
from app.services import prompts as P

SRC = "Students who used the tutoring system improved their exam scores by 12% compared with controls (n = 240)."


def test_quote_exact_and_fuzzy():
    assert quote_supported("improved their exam scores by 12% compared with controls", SRC)
    assert quote_supported("Students who used the tutoring system improved exam scores by 12% compared with controls", SRC)


def test_quote_fabricated_rejected():
    assert not quote_supported("students showed a 45% reduction in dropout across three semesters", SRC)
    assert not quote_supported("too short", SRC)


def test_style_flags_ai_like_text():
    txt = "\n\n".join(["Moreover, it is important to note that AI plays a crucial role in education today. " * 3] * 5)
    r = analyze_style(txt)
    assert r["banned_found"] and r["flags"]


def test_style_ok_for_varied_text():
    txt = ("Adoption was uneven. In the three largest samples, students reported using generative tools weekly, yet "
           "instructors rarely knew. That gap matters. It shapes how any productivity estimate should be read, because "
           "self-reports and grades are only loosely aligned in most of the reviewed studies and often measured months apart.\n\n"
           "Results diverge on grades. Two studies find gains; a third finds none once prior attainment is controlled. "
           "The difference probably lies in design rather than in the tools themselves.\n\n"
           "Effect sizes cluster low. Only one trial is randomised.\n\n"
           "Costs are rarely reported, which makes comparisons across settings hard and leaves policy makers guessing about scale.")
    assert analyze_style(txt)["banned_found"] == []


IDX = {"W1": {"authors": ["Alice Smith", "Bob Lee", "Cy Wu"], "year": 2021, "title": "T1", "venue": "J1", "doi": "10.1/a"},
       "W2": {"authors": ["Dan Roe"], "year": 2019, "title": "T2", "venue": None, "doi": None}}


def test_render_citations():
    out, used = render_citations("Gains were small [W1][W2]. Unknown [W9].", IDX)
    assert "(Smith et al., 2021; Roe, 2019)" in out and "(?W9)" in out and used == ["W1", "W2"]


def test_reference_format():
    assert format_reference(IDX["W1"]).startswith("Smith, Alice") or "Smith" in format_reference(IDX["W1"])
    assert "https://doi.org/10.1/a" in format_reference(IDX["W1"])


def test_meta_sentences_not_flagged_uncited():
    r = check_citations("This paper synthesises the evidence on tutoring systems in higher education.", set())
    assert r["n_uncited"] == 0


def test_assemble_markdown():
    draft = {"title": "X", "order": ["introduction"], "abstract": "abs",
             "sections": {"introduction": {"heading": "Introduction", "text": "Gains were small [W1]."}}}
    md = to_markdown(assemble(draft, IDX))
    assert "## References" in md and "Smith et al., 2021" in md


def test_openalex_helpers():
    assert rebuild_abstract({"Hello": [0], "world": [1]}) == "Hello world"
    assert norm_doi("https://doi.org/10.1000/ABC") == "10.1000/abc"


def test_prompts_build():
    s = P.writer_system("en", "Computers & Education", P.DEFAULT_STYLE)
    assert "GROUNDING RULES" in s and "delve" in s
    sec = {"key": "introduction", "heading": "Introduction", "purpose": "p", "key_points": [{"point": "a", "paper_ids": ["W1"]}]}
    assert "CARS" in P.section_prompt(sec, "T", "[W1] pack", "", "RQ?", "", "", 900)
