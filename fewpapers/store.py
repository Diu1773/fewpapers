"""Merge duplicates across sources, remember what was already shown, and write the candidate files."""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

from .sources import Paper

SOURCE_RANK = {"openalex": 0, "ads": 1, "hf": 2, "arxiv": 3, "feed": 4}  # prefer the journal record when duplicates meet
ABSTRACT_CHARS = 900
AFFILIATIONS_SHOWN = 4


def norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", t.lower())[:120]


def keys(p: Paper) -> list[str]:
    k = []
    if p.doi:
        k.append("doi:" + p.doi)
    if p.arxiv_id:
        k.append("arxiv:" + re.sub(r"v\d+$", "", p.arxiv_id.lower()))
        k.append("doi:10.48550/arxiv." + re.sub(r"v\d+$", "", p.arxiv_id.lower()))
    if p.title:
        k.append("title:" + norm_title(p.title))
    return k


def dedupe(papers: list[Paper]) -> list[Paper]:
    papers = sorted(papers, key=lambda p: (SOURCE_RANK.get(p.source, 9), not p.abstract))
    seen: dict[str, Paper] = {}
    out = []
    for p in papers:
        ks = keys(p)
        hit = next((seen[k] for k in ks if k in seen), None)
        if hit:
            if not hit.abstract and p.abstract:
                hit.abstract = p.abstract
            if not hit.arxiv_id and p.arxiv_id:
                hit.arxiv_id = p.arxiv_id
            if not hit.affiliations and p.affiliations:
                hit.affiliations = p.affiliations
            for k, v in p.signals.items():
                hit.signals.setdefault(k, v)
            for k in ks:
                seen.setdefault(k, hit)
            continue
        for k in ks:
            seen[k] = p
        out.append(p)
    return out


def load_seen(path: Path) -> dict[str, str]:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def filter_unseen(papers: list[Paper], seen: dict[str, str]) -> list[Paper]:
    return [p for p in papers if not any(k in seen for k in keys(p))]


def update_seen(seen: dict[str, str], shown: list[Paper], today: date, keep_days: int = 90) -> dict[str, str]:
    for p in shown:
        for k in keys(p):
            seen[k] = today.isoformat()
    cutoff = (today - timedelta(days=keep_days)).isoformat()
    return {k: d for k, d in seen.items() if d >= cutoff}


TRACK_NOTES = {
    "work": "Ranked by text similarity to the reader's current work. Scores order candidates; they do not judge importance.",
    "landmark": "In order: recent top-journal papers already gathering citations (rising); community-tracked "
                "papers ranked by upvotes, code stars and watched labs; this week's top-journal papers ranked by "
                "similarity to the field; the newest posts of each followed feed. Signals show early attention, "
                "not lasting importance.",
}


def _signal_text(p: Paper) -> str:
    s = p.signals
    parts = []
    if s.get("upvotes"):
        parts.append(f"upvotes {s['upvotes']}")
    if s.get("github_stars"):
        parts.append(f"code stars {s['github_stars']}")
    if s.get("org"):
        parts.append(f"org {s['org']}")
    if s.get("watched_lab"):
        parts.append(f"watched lab: {s['watched_lab']}")
    if s.get("feed"):
        parts.append(f"feed: {s['feed']}")
    if s.get("kind") == "rising":
        parts.append(f"rising: cited {s.get('citations', 0)} times since publication")
    return " | ".join(parts)


def render_markdown(sections: dict[str, list[Paper]], today: date, stats: dict, errors: dict) -> str:
    lines = [
        f"# Paper candidates {today.isoformat()}",
        "",
        "Fetched {fetched}, {unique} unique, {unseen} not listed before.".format(
            fetched=stats.get("fetched", 0), unique=stats.get("unique", 0), unseen=stats.get("unseen", 0)),
    ]
    if errors:
        lines.append("Sources that failed today: " + "; ".join(f"{k} ({v})" for k, v in errors.items()))
    lines.append("")
    for track, papers in sections.items():
        lines += [f"# Track: {track} ({len(papers)} candidates)", "", TRACK_NOTES.get(track, ""), ""]
        for i, p in enumerate(papers, 1):
            ab = p.abstract if len(p.abstract) <= ABSTRACT_CHARS else p.abstract[:ABSTRACT_CHARS].rsplit(" ", 1)[0] + " ..."
            authors = ", ".join(p.authors[:3]) + (" et al." if len(p.authors) > 3 else "")
            sig = _signal_text(p)
            lines += [
                f"## {track[0].upper()}{i}. {p.title}",
                f"- venue: {p.venue} | date: {p.published} | score: {p.score}",
                f"- authors: {authors}" if authors else "- authors: (not listed)",
            ]
            if p.affiliations:
                firms = [a for a in p.affiliations if a.endswith(" (company)")]
                shown = (firms + [a for a in p.affiliations if a not in firms])[:AFFILIATIONS_SHOWN]
                more = len(p.affiliations) - len(shown)
                lines.append("- affiliations: " + "; ".join(shown) + (f"; +{more} more" if more > 0 else ""))
            if sig:
                lines.append(f"- signals: {sig}")
            lines += [f"- link: {p.url}", "", ab or "(no abstract available)", ""]
    return "\n".join(lines)


def write_outputs(out_dir: Path, sections: dict[str, list[Paper]], today: date, stats: dict, errors: dict,
                  keep_archive_days: int = 30) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    md = render_markdown(sections, today, stats, errors)
    payload = {"date": today.isoformat(), "stats": stats, "errors": errors,
               "tracks": {t: [p.to_dict() for p in ps] for t, ps in sections.items()}}
    (out_dir / "latest.md").write_text(md, encoding="utf-8")
    (out_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    arch = out_dir / "archive"
    arch.mkdir(exist_ok=True)
    (arch / f"{today.isoformat()}.md").write_text(md, encoding="utf-8")
    cutoff = (today - timedelta(days=keep_archive_days)).isoformat()
    for f in arch.glob("*.md"):
        if f.stem < cutoff:
            f.unlink()
