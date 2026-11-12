"""Load the reader profile that drives collection and pre-filtering.

A profile has up to two tracks:
- work: papers that touch the reader's current work (text similarity to `profile.interests`);
- landmark: papers that may change a field (community attention, watched labs, lab blogs).
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ENV_PROFILE = "FEWPAPERS_PROFILE"


@dataclass
class Landmark:
    enabled: bool = False
    topic: str = ""
    labs: list[str] = field(default_factory=list)
    feeds: list[dict] = field(default_factory=list)
    hf_days: int = 7
    lookback_days: int = 3
    min_upvotes: int = 20
    candidates: int = 10
    feed_max: int = 2
    keywords: list[str] = field(default_factory=list)
    journals: list[str] = field(default_factory=list)
    journal_lookback_days: int = 7
    journal_candidates: int = 8
    rising: bool = True
    rising_days: int = 90
    rising_min_citations: int = 5
    rising_candidates: int = 5
    follow_field: bool = False  # order rising and community papers by similarity to `field` too


@dataclass
class Profile:
    interests: str = ""
    keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    library: str | None = None
    candidates: int = 30
    lookback_days: int = 7
    arxiv_lookback_days: int = 3
    arxiv_categories: list[str] = field(default_factory=list)
    openalex_issns: list[str] = field(default_factory=list)
    openalex_queries: list[str] = field(default_factory=list)
    openalex_mailto: str = ""
    ads_query: str = ""
    landmark: Landmark = field(default_factory=Landmark)
    base_dir: Path = Path(".")

    @property
    def work_enabled(self) -> bool:
        return bool(self.interests or self.keywords)


def _from_dict(d: dict, base_dir: Path) -> Profile:
    p = d.get("profile", {})
    lim = d.get("limits", {})
    src = d.get("sources", {})
    ax = src.get("arxiv", {})
    oa = src.get("openalex", {})
    ads = src.get("ads", {})
    lm = d.get("landmark", {})
    prof = Profile(
        interests=p.get("interests", "").strip(),
        keywords=list(p.get("keywords", [])),
        exclude_keywords=list(p.get("exclude_keywords", [])),
        library=p.get("library") or None,
        candidates=int(lim.get("candidates", 30)),
        lookback_days=int(lim.get("lookback_days", 7)),
        arxiv_lookback_days=int(lim.get("arxiv_lookback_days", 3)),
        arxiv_categories=list(ax.get("categories", [])),
        openalex_issns=list(oa.get("issns", [])),
        openalex_queries=list(oa.get("queries", [])),
        openalex_mailto=oa.get("mailto", "") or os.environ.get("OPENALEX_MAILTO", ""),
        ads_query=ads.get("query", ""),
        landmark=Landmark(
            enabled=bool(lm.get("enabled", bool(lm))),
            topic=lm.get("field", "").strip(),
            labs=list(lm.get("labs", [])),
            feeds=[f if isinstance(f, dict) else {"url": f} for f in lm.get("feeds", [])],
            hf_days=int(lm.get("hf_days", 7)),
            lookback_days=int(lm.get("lookback_days", 3)),
            min_upvotes=int(lm.get("min_upvotes", 20)),
            candidates=int(lm.get("candidates", 10)),
            feed_max=int(lm.get("feed_max", 2)),
            keywords=list(lm.get("keywords", [])),
            journals=list(lm.get("journals", [])),
            journal_lookback_days=int(lm.get("journal_lookback_days", 7)),
            journal_candidates=int(lm.get("journal_candidates", 8)),
            rising=bool(lm.get("rising", True)),
            rising_days=int(lm.get("rising_days", 90)),
            rising_min_citations=int(lm.get("rising_min_citations", 5)),
            rising_candidates=int(lm.get("rising_candidates", 5)),
            follow_field=bool(lm.get("follow_field", False)),
        ),
        base_dir=base_dir,
    )
    if not prof.work_enabled and not prof.landmark.enabled:
        raise ValueError("profile needs 'profile.interests'/'profile.keywords' or an enabled [landmark] section")
    return prof


def load_profile(path: str | None = None) -> Profile:
    """Read the profile from the environment, an explicit path, or profile.local.toml / profile.toml."""
    text = os.environ.get(ENV_PROFILE, "").strip()
    if text:
        return _from_dict(tomllib.loads(text), Path("."))
    candidates = [path] if path else ["profile.local.toml", "profile.toml"]
    for c in candidates:
        if c and Path(c).is_file():
            f = Path(c)
            return _from_dict(tomllib.loads(f.read_text(encoding="utf-8")), f.parent)
    raise FileNotFoundError(
        f"no profile found: set {ENV_PROFILE}, pass --profile, or copy profile.example.toml to profile.toml"
    )
