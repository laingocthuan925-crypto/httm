"""[W123] -> (Author, Year) và danh mục tài liệu tham khảo (kiểu APA rút gọn)."""
import re

GROUP_RE = re.compile(r"((?:\[[A-Za-z0-9_\-:.]+\])+)")
ONE_RE = re.compile(r"\[([A-Za-z0-9_\-:.]+)\]")


def surname(name: str) -> str:
    name = name.strip()
    if "," in name:
        return name.split(",")[0].strip()
    return name.split()[-1] if name.split() else name


def inline_cite(p: dict) -> str:
    a, y = p.get("authors") or [], p.get("year") or "n.d."
    if not a:
        return f"{(p.get('title') or '?')[:30]}..., {y}"
    if len(a) == 1:
        return f"{surname(a[0])}, {y}"
    if len(a) == 2:
        return f"{surname(a[0])} & {surname(a[1])}, {y}"
    return f"{surname(a[0])} et al., {y}"


def _initials(name: str) -> str:
    parts = name.replace(",", " ").split()
    if len(parts) < 2:
        return name
    return f"{parts[-1]}, " + " ".join(x[0] + "." for x in parts[:-1])


def format_reference(p: dict) -> str:
    authors = p.get("authors") or []
    au = "; ".join(_initials(a) for a in authors[:6]) + (" et al." if len(authors) > 6 else "") if authors else p["title"]
    ref = f"{au} ({p.get('year') or 'n.d.'}). {p['title']}."
    if p.get("venue"):
        ref += f" {p['venue']}."
    if p.get("doi"):
        ref += f" https://doi.org/{p['doi']}"
    return ref


def render_citations(text: str, index: dict) -> tuple[str, list[str]]:
    """Thay [ID][ID] bằng (A, 2020; B, 2021). Trả (text, danh sách id đã dùng theo thứ tự xuất hiện)."""
    used: list[str] = []

    def repl(m):
        ids = ONE_RE.findall(m.group(1))
        parts = []
        for i in ids:
            if i in index:
                parts.append(inline_cite(index[i]))
                if i not in used:
                    used.append(i)
            else:
                parts.append(f"?{i}")
        return "(" + "; ".join(parts) + ")"

    return GROUP_RE.sub(repl, text), used
