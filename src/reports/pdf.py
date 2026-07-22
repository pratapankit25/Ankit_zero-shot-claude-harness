"""Bilingual briefing PDFs (fpdf2 + bundled Noto fonts — Devanagari renders
without system fonts). Numbers are carried verbatim from the audited run;
translation touches prose only, and falls back to source-language on any
mismatch. (spec/capabilities/bilingual-reports.md)"""
import re
from datetime import datetime, timezone
from pathlib import Path

from fpdf import FPDF

from observability.events import get_logger

log = get_logger("reports.pdf")
_FONTS = Path(__file__).parent.parent / "assets" / "fonts"

NAVY = (15, 23, 42)
AMBER = (217, 119, 6)
INK = (51, 65, 85)
MUTED = (100, 116, 139)


def _digits(text: str) -> set[str]:
    return set(re.findall(r"\d[\d,\.]*", (text or "").replace(",", "")))


def translate_answer(text: str, target: str) -> str | None:
    """LLM translation with numbers preserved verbatim; None on failure/mismatch."""
    from llm.client import LLMClient, LLMError

    lang_name = "Hindi (Devanagari script)" if target == "hi" else "English"
    try:
        result = LLMClient().generate(
            f"Translate this analyst answer to {lang_name}. Keep EVERY number exactly as-is "
            f"(digits, not words). Keep markdown. Return only the translation.\n\n{text}"
        )
        translated = result.text.strip()
        if not translated or not _digits(text) <= _digits(translated):
            log.info("pdf.translation_rejected", reason="number mismatch")
            return None
        return translated
    except LLMError as exc:
        log.info("pdf.translation_failed", error=str(exc))
        return None


class _BriefPDF(FPDF):
    def __init__(self) -> None:
        super().__init__()
        self.add_font("noto", style="", fname=str(_FONTS / "NotoSans-Regular.ttf"))
        self.add_font("notodev", style="", fname=str(_FONTS / "NotoSansDevanagari-Regular.ttf"))
        self.set_auto_page_break(True, margin=18)

    def use(self, size: int, color=INK, hindi: bool = False) -> None:
        self.set_font("notodev" if hindi else "noto", size=size)
        self.set_text_color(*color)

    def text_block(self, text: str, size: int = 10, color=INK) -> None:
        # pick the Devanagari-capable font whenever the text contains it
        hindi = bool(re.search(r"[ऀ-ॿ]", text))
        self.use(size, color, hindi=hindi)
        clean = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # strip bold markers
        clean = re.sub(r"^#+\s*", "", clean, flags=re.M)
        self.multi_cell(0, 5.6, clean)
        self.ln(1.5)


def _header(pdf: _BriefPDF, title: str) -> None:
    pdf.add_page()
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, 210, 22, style="F")
    pdf.set_xy(12, 6)
    pdf.use(13, (255, 255, 255))
    pdf.cell(0, 8, "UP Police Data Analyst")
    pdf.set_xy(12, 13)
    pdf.use(8, (245, 158, 11))
    pdf.cell(0, 5, datetime.now(timezone.utc).strftime("Generated %d %b %Y, %H:%M UTC"))
    pdf.set_xy(12, 28)
    pdf.text_block(title, size=15, color=NAVY)
    pdf.set_draw_color(*AMBER)
    pdf.set_line_width(0.8)
    pdf.line(12, pdf.get_y(), 80, pdf.get_y())
    pdf.ln(4)
    pdf.set_x(12)


def _table(pdf: _BriefPDF, columns: list, rows: list, cap: int = 12) -> None:
    if not columns or not rows:
        return
    pdf.use(8, MUTED)
    widths = [max(18.0, min(60.0, 186 / len(columns)))] * len(columns)
    pdf.set_fill_color(*NAVY)
    pdf.set_text_color(255, 255, 255)
    pdf.set_x(12)
    for w, c in zip(widths, columns):
        pdf.cell(w, 6, str(c)[:28], fill=True)
    pdf.ln()
    pdf.set_text_color(*INK)
    for i, row in enumerate(rows[:cap]):
        pdf.set_fill_color(248, 250, 252) if i % 2 else pdf.set_fill_color(255, 255, 255)
        pdf.set_x(12)
        for w, v in zip(widths, row):
            pdf.cell(w, 6, ("" if v is None else str(v))[:28], fill=True)
        pdf.ln()
    if len(rows) > cap:
        pdf.set_x(12)
        pdf.use(8, MUTED)
        pdf.cell(0, 5, f"… {len(rows) - cap} more rows in the app")
        pdf.ln(6)
    pdf.ln(2)


def _answer_sections(run: dict, lang: str) -> list[tuple[str, str]]:
    """[(language_tag, text)] respecting the requested mode with honest fallback."""
    answer = run.get("answer") or ""
    src_is_hindi = bool(re.search(r"[ऀ-ॿ]", answer))
    src_tag = "hi" if src_is_hindi else "en"
    if lang in ("both", "hi", "en"):
        targets = ["en", "hi"] if lang == "both" else [lang]
        sections = []
        for t in targets:
            if t == src_tag:
                sections.append((t, answer))
            else:
                translated = translate_answer(answer, t)
                if translated:
                    sections.append((t, translated))
                elif lang != "both":
                    sections.append((src_tag, answer + "\n\n(Translation unavailable — source language shown.)"))
        return sections or [(src_tag, answer)]
    return [(src_tag, answer)]


def build_run_pdf(run: dict, lang: str = "both") -> bytes:
    pdf = _BriefPDF()
    _header(pdf, run.get("question") or "Analyst answer")
    for tag, text in _answer_sections(run, lang):
        pdf.set_x(12)
        pdf.text_block("— हिन्दी —" if tag == "hi" else "— English —", size=9, color=MUTED)
        pdf.set_x(12)
        pdf.text_block(text, size=10)
    result = run.get("result") or {}
    _table(pdf, result.get("columns", []), result.get("rows", []))
    footer = []
    if run.get("freshness"):
        footer.append(run["freshness"])
    footer.extend(run.get("caveats") or [])
    if run.get("sql"):
        footer.append(f"SQL: {run['sql'][:300]}")
    if footer:
        pdf.set_x(12)
        pdf.text_block("\n".join(f"• {f}" for f in footer), size=8, color=MUTED)
    return bytes(pdf.output())


def build_report_pdf(title: str, content_md: str) -> bytes:
    pdf = _BriefPDF()
    _header(pdf, title)
    for block in content_md.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        pdf.set_x(12)
        if block.startswith("|"):
            lines = [ln for ln in block.splitlines() if ln.strip().startswith("|")]
            if len(lines) >= 2:
                parse = lambda ln: [c.strip() for c in ln.strip().strip("|").split("|")]
                cols = parse(lines[0])
                rows = [parse(ln) for ln in lines[2:]]
                _table(pdf, cols, rows)
                continue
        size = 12 if block.startswith("## ") else 10
        pdf.text_block(block, size=size, color=NAVY if block.startswith("#") else INK)
    return bytes(pdf.output())
