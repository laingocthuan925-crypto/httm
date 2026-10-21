"""
Toàn bộ prompt (phần 'não'). Prompt viết tiếng Anh vì chất lượng văn học thuật tốt hơn;
ngôn ngữ đầu ra điều khiển bằng tham số language.
Nguyên tắc xuyên suốt: EVIDENCE-FIRST — mọi thông tin phải đi từ bằng chứng đã kiểm chứng.
"""
import json
from app.services.style_checks import BANNED

# ---------------------------------------------------------------- Analyst
ANALYST_SYSTEM = """You are a meticulous research analyst extracting structured information from ONE paper.
Rules:
- Extract only what the provided text explicitly states. If something is not stated, use null (or list it in not_reported). Never infer methods, sample sizes, effect sizes or conclusions.
- Each finding needs 1-2 evidence quotes copied VERBATIM from the text (max 40 words, no paraphrase, no ellipsis, no edits). chunk_ref must be the label of the passage the quote came from (e.g. C123 or ABSTRACT).
- If the source is ABSTRACT only, be conservative: do not report details a typical abstract omits.
- Prefer fewer, well-supported findings (max 6) over many weak ones.
- claim_type is one of: finding, method, definition, limitation, theory."""


def analysis_prompt(paper: dict, context: str, source: str, focus: str) -> str:
    return (f"Research focus of the review: {focus}\n"
            f"Paper: {paper['title']} ({paper.get('year')})\nText source: {source}\n\n"
            f"--- TEXT ---\n{context}\n--- END TEXT ---\n\n"
            "Extract: research_question, method, sample_or_data, theoretical_lens, key_findings (relevant to the focus), limitations, not_reported.")


# ---------------------------------------------------------------- Screening
def screening_prompt(plan: dict, papers: list[dict]) -> str:
    s = plan.get("search_strategy", {})
    lst = "\n".join(f"[{p['id']}] {p['title']} ({p['year']}): {(p['abstract'] or '')[:900]}" for p in papers)
    return (f"Topic: {plan.get('topic')}\nResearch questions: {plan.get('research_questions')}\n"
            f"Inclusion guidance: study types {s.get('study_types')}, dates {s.get('date_range')}.\n\n"
            "Decide for each record whether it should be INCLUDED in a literature review on this topic "
            "(directly relevant, scholarly, has substantive content). Give a one-sentence reason. "
            "Return a decision for every paper_id.\n\n" + lst)


# ---------------------------------------------------------------- Synthesis
SYNTH_SYSTEM = """You are a senior researcher synthesising a corpus of analysed papers.
- Use ONLY the papers provided; cite them by their paper_id in paper_ids fields. Never invent ids.
- Group by IDEAS, not by paper. Identify consensus, real contradictions (different results/positions), and gaps.
- A gap must be phrased as 'within the reviewed corpus, X is under-examined' — never claim that no literature exists anywhere.
- Every gap must list the paper_ids that reveal it (what they studied / left out). Prefer 3-6 sharp gaps over many vague ones."""


def synthesis_prompt(plan: dict, digest: str) -> str:
    return (f"Topic: {plan.get('topic')}\nResearch questions from plan: {plan.get('research_questions')}\n\n"
            f"CORPUS DIGEST:\n{digest}\n\n"
            "Produce: themes (name, summary, paper_ids), consensus statements, contradictions, gaps "
            "(gap_id like G1, description, gap_type in population|method|context|theory|contradiction|other, paper_ids, confirmed=false).")


# ---------------------------------------------------------------- Research questions
RQ_SYSTEM = """You design research questions for a journal article. Each RQ must be answerable, specific, and tied to ONE confirmed gap.
Rate feasibility honestly (1-5): data availability, scope, and whether the paper type allows answering it.
Avoid yes/no questions and vague 'impact of X on Y' without context."""


def rq_prompt(plan: dict, gaps: list[dict], themes: list[dict], paper_type: str) -> str:
    return (f"Topic: {plan.get('topic')}\nPaper type: {paper_type}\n"
            f"Confirmed gaps: {json.dumps(gaps, ensure_ascii=False)}\n"
            f"Themes: {json.dumps([t['name'] for t in themes], ensure_ascii=False)}\n\n"
            "Generate 1-2 candidate research questions per gap (max 6 total) with rationale, study_design, and feasibility.")


def novelty_prompt(items: list[dict]) -> str:
    return ("For each candidate RQ below, judge NOVELTY relative to the nearest papers in the corpus (score 1-5, 5 = clearly unaddressed). "
            "Only cite closest_paper_ids from the provided neighbours. Explain overlap briefly.\n\n"
            + json.dumps(items, ensure_ascii=False, indent=1))


def model_prompt(rq: dict, themes: list[dict], digest: str) -> str:
    return (f"Selected research question: {rq['question']}\nDesign: {rq.get('study_design')}\n"
            f"Themes: {json.dumps([t['name'] for t in themes], ensure_ascii=False)}\n\nEvidence digest:\n{digest}\n\n"
            "Build a conceptual model for a quantitative study: independent, dependent, mediating, moderating and control variables "
            "(each with definition and how it is measured), and hypotheses H1..Hn. Each hypothesis needs a direction and basis_paper_ids "
            "taken ONLY from the digest. Do not propose hypotheses with no evidential basis.")


# ---------------------------------------------------------------- Style profile
def style_profile_prompt(samples: list[str]) -> str:
    body = "\n\n=====\n\n".join(s[:6000] for s in samples[:5])
    return ("Analyse the writing style of these exemplar journal excerpts (target venue). Describe: voice (person, active/passive), tense habits, "
            "typical sentence length, paragraph habits, hedging and stance, transitions, recurring terminology, other notes. Be concrete and short.\n\n" + body)


DEFAULT_STYLE = ("Formal but readable academic prose. Mix short and long sentences. Active voice where natural. "
                 "Hedge claims proportionally to the evidence (suggests, indicates, is consistent with). "
                 "Paragraphs of 4-8 sentences with one clear point each.")

# ---------------------------------------------------------------- Writer
def writer_system(language: str, venue: str | None, style: str) -> str:
    return f"""You are an experienced academic author writing one section of a journal article{f' for {venue}' if venue else ''}. Output language: {language}.

GROUNDING RULES (never break):
1. Use ONLY facts in the EVIDENCE PACK (and PROCESS DATA if given). Do not add facts from memory.
2. Every sentence reporting what prior research found, argued or measured MUST end with citation(s) in the form [W123]; for several sources write them adjacent: [W1][W2]. Cite ONLY ids that appear at the start of a pack entry.
3. Never invent numbers, sample sizes, author names, quotations, or study details. If the pack lacks support for an outline point, drop it or frame it as an open question.
4. Paraphrase. Never reproduce more than 8 consecutive words from a source.
5. Match hedging to the evidence base: abstract-only evidence => cautious wording; consistent full-text evidence across several studies => firmer wording.

CRAFT RULES:
- Synthesise by idea: group studies, compare and contrast, explain why results differ. Do not summarise papers one by one.
- Have a point of view: state what the evidence collectively suggests and how confident that reading is.
- Vary sentence length and paragraph length. Prefer concrete subjects and verbs over abstractions.
- Avoid stock phrases such as: {', '.join(BANNED[:12])}. Do not start many sentences with Moreover/Furthermore/Additionally.
- Do not repeat what earlier sections already said (see WRITTEN SO FAR); refer back briefly instead.

STYLE PROFILE: {style}"""


GUIDE = {
    "introduction": "Follow the CARS moves: (1) establish the territory — why the topic matters, what is known; (2) establish the niche — the specific gap/tension, grounded in the evidence; (3) occupy the niche — state the research question(s), what this paper does, and a one-sentence roadmap. Open with a concrete problem, not a generic claim about technology changing the world.",
    "methodology": "Describe the review procedure ONLY from PROCESS DATA (databases, queries, dates, counts, evidence base, LLM-assisted extraction). Do not invent inclusion criteria, tools, reviewers or counts. Omit any detail not present in PROCESS DATA. Disclose the LLM-assisted screening/extraction plainly.",
    "findings": "Organise by theme. For each theme: state the pattern, support it with the cited evidence, then note exceptions and contradictions. Compare designs and contexts across studies. Indicate how many studies support each pattern using only the pack.",
    "thematic_synthesis": "Organise by theme. For each theme: state the pattern, support it with cited evidence, then note exceptions and contradictions. Compare studies against each other.",
    "background": "Build the conceptual foundation: define key constructs, trace how the literature has framed them, and show where the framings conflict. Thematic, not chronological.",
    "literature_review": "Build the conceptual foundation: define key constructs, trace how the literature has framed them, and show where the framings conflict. Thematic, not chronological.",
    "conceptual_model": "Present each construct with a definition, then the propositions/hypotheses from CONCEPTUAL MODEL, each justified by the pack evidence. Describe relationships and boundary conditions. Do not add hypotheses that are not in the model.",
    "discussion": "Interpret the findings against the research question(s): what agrees, what conflicts, why. Draw implications for research and practice. Do not introduce new empirical claims without citations.",
    "limitations": "Be specific and honest: corpus limits (databases, language, date range, share of abstract-only papers), automation limits, publication bias — grounded in PROCESS DATA. Then suggest concrete future work.",
    "conclusion": "Answer each research question directly, state the contribution in plain terms, and end with one forward-looking point. No new evidence.",
    "abstract": "150-250 words of continuous prose: background, aim, method, main findings, implication. No citations and no claims that are not in the paper text provided.",
}


def section_prompt(section: dict, outline_title: str, pack: str, memory: str, rq_text: str,
                   process: str, model_text: str, target_words: int) -> str:
    pts = "\n".join(f"- {kp['point']}  (sources: {', '.join(kp['paper_ids']) or 'none'})" for kp in section["key_points"])
    parts = [f"PAPER TITLE: {outline_title}", f"SECTION: {section['heading']}  (target ~{target_words} words)",
             f"PURPOSE: {section['purpose']}", f"SECTION GUIDE: {GUIDE.get(section['key'], '')}",
             f"RESEARCH QUESTION(S): {rq_text}", f"OUTLINE POINTS:\n{pts}"]
    if model_text:
        parts.append(f"CONCEPTUAL MODEL:\n{model_text}")
    if process:
        parts.append(f"PROCESS DATA:\n{process}")
    parts.append(f"WRITTEN SO FAR:\n{memory or '(nothing yet)'}")
    parts.append(f"EVIDENCE PACK:\n{pack or '(none for this section)'}")
    parts.append("Write the section now as continuous academic prose (no headings, no bullet lists). Also return a 2-3 sentence summary of what you wrote and the list of terms you defined.")
    return "\n\n".join(parts)


def revise_prompt(section_text: str, issues: list[str], pack: str) -> str:
    return ("Revise the section below. Fix EVERY listed issue and change nothing else that is fine. Keep the grounding rules: "
            "only facts from the EVIDENCE PACK, cite with [ids], remove or soften any claim the pack does not support.\n\n"
            "ISSUES:\n" + "\n".join(f"- {i}" for i in issues) +
            f"\n\nEVIDENCE PACK:\n{pack or '(none)'}\n\nSECTION TEXT:\n{section_text}\n\n"
            "Return the full revised text, a 2-3 sentence summary, and defined_terms.")


def outline_prompt(plan: dict, rq_text: str, themes: list[dict], gaps: list[dict], template: list, ids: list[str]) -> str:
    return (f"Topic: {plan.get('topic')}\nResearch question(s): {rq_text}\nConfirmed gaps: {json.dumps(gaps, ensure_ascii=False)}\n"
            f"Themes with sources: {json.dumps(themes, ensure_ascii=False)}\nAllowed paper_ids: {ids}\n\n"
            f"Design a journal-article outline with EXACTLY these sections, in order (key -> heading): {template}.\n"
            "Give a specific, non-generic title, each section's purpose, and 2-5 key_points per section; each key point lists the "
            "paper_ids (from Allowed paper_ids only) that support it. Methodology/limitations/abstract need no paper_ids. "
            "The outline must let the paper answer the research question(s).")


# ---------------------------------------------------------------- Reviewer
VERIFIER_SYSTEM = """You verify whether cited sentences are supported by the cited papers' extracted evidence.
supported = the evidence directly backs the sentence's claim; partial = related but the sentence overstates, generalises or adds detail;
unsupported = evidence does not back it or contradicts it. Judge only from the evidence given. Be strict about numbers and causal wording."""


def claim_verify_prompt(items: list[dict]) -> str:
    return "Return a verdict for every index.\n\n" + json.dumps(items, ensure_ascii=False, indent=1)


def structure_review_prompt(draft_text: str, rq_text: str) -> str:
    return (f"Research question(s): {rq_text}\n\nYou are a critical journal reviewer. Read the draft and report: "
            "does the paper actually answer the RQ (rq_answered)? List issues: contradictions between sections, promises in the introduction "
            "not delivered, repeated content, undefined or inconsistent terminology, unsupported leaps, sections that do not fulfil their purpose. "
            "Each issue: section_key, severity (high|medium|low), issue, fix. Return only real problems.\n\nDRAFT:\n" + draft_text)
