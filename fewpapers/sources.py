"""Fetch recent papers from arXiv, OpenAlex, NASA ADS, Hugging Face daily papers and RSS feeds."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime

USER_AGENT = "Mozilla/5.0 (compatible; fewpapers/0.2)"
TIMEOUT = 60


@dataclass
class Paper:
    title: str
    abstract: str
    url: str
    venue: str
    published: str
    source: str
    doi: str = ""
    arxiv_id: str = ""
    authors: list[str] = field(default_factory=list)
    affiliations: list[str] = field(default_factory=list)  # institutions, companies marked " (company)"
    score: float = 0.0
    signals: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _get(url: str, headers: dict | None = None) -> bytes:
    h = {"User-Agent": USER_AGENT}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500 and e.code != 429:  # the same request would fail again
                raise
            last = e
            time.sleep(3 * (attempt + 1))
        except Exception as e:  # retried, then re-raised for the caller to record
            last = e
            time.sleep(3 * (attempt + 1))
    raise last


def _clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _unique(items) -> list[str]:
    return list(dict.fromkeys(i for i in items if i))


# arXiv ----------------------------------------------------------------------

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"


def parse_arxiv_atom(xml_bytes: bytes) -> list[Paper]:
    root = ET.fromstring(xml_bytes)
    out = []
    for e in root.findall(f"{ATOM}entry"):
        raw_id = _clean(e.findtext(f"{ATOM}id"))
        m = re.search(r"abs/([^v]+?)(v\d+)?$", raw_id)
        aid = m.group(1) if m else raw_id
        cats = [c.get("term") for c in e.findall(f"{ATOM}category")]
        out.append(Paper(
            title=_clean(e.findtext(f"{ATOM}title")),
            abstract=_clean(e.findtext(f"{ATOM}summary")),
            url=f"https://arxiv.org/abs/{aid}",
            venue="arXiv " + (cats[0] if cats else ""),
            published=_clean(e.findtext(f"{ATOM}published"))[:10],
            source="arxiv",
            arxiv_id=aid,
            doi=f"10.48550/arxiv.{aid}".lower(),
            authors=[_clean(a.findtext(f"{ATOM}name")) for a in e.findall(f"{ATOM}author")],
            affiliations=_unique(_clean(x.text) for a in e.findall(f"{ATOM}author")
                                 for x in a.findall(f"{ARXIV}affiliation")),
        ))
    return out


def fetch_arxiv(categories: list[str], lookback_days: int, today: date) -> list[Paper]:
    start = (today - timedelta(days=lookback_days)).strftime("%Y%m%d0000")
    end = (today + timedelta(days=1)).strftime("%Y%m%d0000")
    papers: list[Paper] = []
    for i, cat in enumerate(categories):
        if i:
            time.sleep(3)  # the export API asks for a pause between calls
        q = f"cat:{cat} AND submittedDate:[{start} TO {end}]"
        url = ("http://export.arxiv.org/api/query?" + urllib.parse.urlencode({
            "search_query": q, "start": 0, "max_results": 300,
            "sortBy": "submittedDate", "sortOrder": "descending",
        }))
        papers.extend(parse_arxiv_atom(_get(url)))
    return papers


# OpenAlex -------------------------------------------------------------------

def abstract_from_inverted_index(inv: dict | None) -> str:
    if not inv:
        return ""
    slots: dict[int, str] = {}
    for word, positions in inv.items():
        for p in positions:
            slots[p] = word
    return " ".join(slots[i] for i in sorted(slots))


def openalex_affiliations(w: dict) -> list[str]:
    """Institutions of all authors in author order; companies are marked so they can be told apart."""
    return _unique(i.get("display_name", "") + (" (company)" if i.get("type") == "company" else "")
                   for a in (w.get("authorships") or []) for i in (a.get("institutions") or []))


def _openalex_paper(w: dict) -> Paper:
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    doi = (w.get("doi") or "").replace("https://doi.org/", "").lower()
    return Paper(
        title=_clean(w.get("title") or w.get("display_name")),
        abstract=_clean(abstract_from_inverted_index(w.get("abstract_inverted_index"))),
        url=w.get("doi") or loc.get("landing_page_url") or w.get("id", ""),
        venue=src.get("display_name") or "",
        published=w.get("publication_date") or "",
        source="openalex",
        doi=doi,
        authors=[(a.get("author") or {}).get("display_name", "") for a in (w.get("authorships") or [])][:12],
        affiliations=openalex_affiliations(w),
        signals={"citations": w["cited_by_count"]} if "cited_by_count" in w else {},
    )


def _openalex_fetch(filter_: str, mailto: str, cap: int) -> tuple[list[Paper], bool]:
    """Newest first. Returns the works and whether more matched than could be read.
    Without OPENALEX_API_KEY only the first page (200 works) is reachable."""
    select = "id,doi,title,display_name,publication_date,abstract_inverted_index,primary_location,authorships,type"
    api_key = os.environ.get("OPENALEX_API_KEY", "")
    cursor, out = "*", []
    while cursor and len(out) < cap:
        if cursor != "*" and not api_key:
            return out[:cap], True
        params = {"filter": filter_, "sort": "publication_date:desc", "per-page": 200, "cursor": cursor,
                  "select": select}
        if mailto:
            params["mailto"] = mailto
        if api_key:
            params["api_key"] = api_key
        try:
            data = json.loads(_get("https://api.openalex.org/works?" + urllib.parse.urlencode(params)))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403) and cursor != "*":
                return out[:cap], True
            raise
        out.extend(_openalex_paper(w) for w in data.get("results", []))
        cursor = data.get("meta", {}).get("next_cursor")
        if not data.get("results"):
            break
    return out[:cap], False


def _openalex_query(filter_: str, mailto: str, cap: int) -> list[Paper]:
    return _openalex_fetch(filter_, mailto, cap)[0]


def fetch_openalex(issns: list[str], queries: list[str], lookback_days: int, today: date,
                   mailto: str = "", cap: int = 600) -> list[Paper]:
    window = (f"from_publication_date:{(today - timedelta(days=lookback_days)).isoformat()},"
              f"to_publication_date:{today.isoformat()}")
    papers: list[Paper] = []
    if issns:
        found, cut = _openalex_fetch(f"primary_location.source.issn:{'|'.join(issns)},{window}", mailto, cap)
        if cut and len(issns) > 1:  # too many for one page: one query per journal instead
            found = []
            for issn in issns:
                found.extend(_openalex_query(f"primary_location.source.issn:{issn},{window}", mailto, cap))
        papers.extend(found)
    for q in queries:
        safe = q.replace(",", " ")
        papers.extend(_openalex_query(f"title_and_abstract.search:{safe},{window}", mailto, cap // 3))
    return papers


def fetch_openalex_rising(issns: list[str], days: int, today: date, min_citations: int,
                          cap: int = 50, mailto: str = "") -> list[Paper]:
    """Recent papers in the given journals that already collect citations, most cited first.
    Citation counts are as of the request, so this source cannot be replayed for past dates."""
    filt = (f"primary_location.source.issn:{'|'.join(issns)},"
            f"from_publication_date:{(today - timedelta(days=days)).isoformat()},to_publication_date:{today.isoformat()},"
            f"type:article,cited_by_count:>{max(min_citations - 1, 0)}")
    params = {"filter": filt, "sort": "cited_by_count:desc", "per-page": min(cap, 200),
              "select": "id,doi,title,display_name,publication_date,abstract_inverted_index,primary_location,"
                        "authorships,type,cited_by_count"}
    if mailto:
        params["mailto"] = mailto
    if os.environ.get("OPENALEX_API_KEY"):
        params["api_key"] = os.environ["OPENALEX_API_KEY"]
    data = json.loads(_get("https://api.openalex.org/works?" + urllib.parse.urlencode(params)))
    return [_openalex_paper(w) for w in data.get("results", [])][:cap]


def add_affiliations(papers: list[Paper], mailto: str = "", chunk: int = 50) -> int:
    """Fill missing affiliations from OpenAlex by DOI, in a few batched requests.
    Recent preprints are often not indexed yet or carry partial affiliations. Returns how many were filled."""
    todo = [p for p in papers if not p.affiliations and p.doi]
    filled = 0
    for i in range(0, len(todo), chunk):
        part = todo[i:i + chunk]
        params = {"filter": "doi:" + "|".join(p.doi for p in part), "per-page": chunk, "select": "doi,authorships"}
        if mailto:
            params["mailto"] = mailto
        if os.environ.get("OPENALEX_API_KEY"):
            params["api_key"] = os.environ["OPENALEX_API_KEY"]
        data = json.loads(_get("https://api.openalex.org/works?" + urllib.parse.urlencode(params)))
        by_doi = {(w.get("doi") or "").replace("https://doi.org/", "").lower(): w for w in data.get("results", [])}
        for p in part:
            aff = openalex_affiliations(by_doi.get(p.doi, {}))
            if aff:
                p.affiliations, filled = aff, filled + 1
    return filled


# NASA ADS -------------------------------------------------------------------

def fetch_ads(query: str, lookback_days: int, token: str | None = None, rows: int = 200) -> list[Paper]:
    token = token or os.environ.get("ADS_TOKEN", "")
    if not token or not query:
        return []
    params = {
        "q": query,
        "fq": f"entdate:[NOW-{lookback_days}DAYS TO NOW]",
        "fl": "bibcode,title,abstract,doi,pub,pubdate,author,identifier",
        "rows": rows,
        "sort": "entry_date desc",
    }
    url = "https://api.adsabs.harvard.edu/v1/search/query?" + urllib.parse.urlencode(params)
    data = json.loads(_get(url, {"Authorization": f"Bearer {token}"}))
    out = []
    for d in data.get("response", {}).get("docs", []):
        doi = (d.get("doi") or [""])[0].lower()
        aid = next((i.split(":", 1)[1] for i in d.get("identifier", []) if i.lower().startswith("arxiv:")), "")
        out.append(Paper(
            title=_clean((d.get("title") or [""])[0]),
            abstract=_clean(d.get("abstract")),
            url=f"https://ui.adsabs.harvard.edu/abs/{d.get('bibcode', '')}",
            venue=d.get("pub", ""),
            published=(d.get("pubdate") or "")[:10],
            source="ads",
            doi=doi,
            arxiv_id=aid,
            authors=(d.get("author") or [])[:12],
        ))
    return out


# Hugging Face daily papers ---------------------------------------------------

def parse_hf_daily(items: list[dict]) -> list[Paper]:
    out = []
    for e in items:
        p = e.get("paper") or {}
        aid = p.get("id", "")
        org = (p.get("organization") or e.get("organization") or {})
        out.append(Paper(
            title=_clean(p.get("title") or e.get("title")),
            abstract=_clean(p.get("summary") or e.get("summary")),
            url=f"https://arxiv.org/abs/{aid}" if aid else "",
            venue="arXiv (Hugging Face daily papers)",
            published=(p.get("publishedAt") or e.get("publishedAt") or "")[:10],
            source="hf",
            arxiv_id=aid,
            doi=f"10.48550/arxiv.{aid}".lower() if aid else "",
            authors=[a.get("name", "") for a in (p.get("authors") or [])][:12],
            signals={
                "upvotes": int(p.get("upvotes") or 0),
                "github_stars": int(p.get("githubStars") or 0),
                "org": (org.get("fullname") or org.get("name") or "") if isinstance(org, dict) else "",
                "comments": int(e.get("numComments") or 0),
            },
        ))
    return out


def fetch_hf_daily(days: int, today: date) -> list[Paper]:
    """Daily lists for the last `days` days; re-reading older days lets late risers surface."""
    papers: list[Paper] = []
    for i in range(days):
        d = (today - timedelta(days=i)).isoformat()
        try:
            items = json.loads(_get(f"https://huggingface.co/api/daily_papers?date={d}"))
        except Exception:
            if i == 0:
                continue  # today's list may not exist yet
            raise
        papers.extend(parse_hf_daily(items))
    return papers


# RSS / Atom feeds ------------------------------------------------------------

def _feed_date(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return parsedate_to_datetime(s).date()
    except Exception:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except Exception:
        return None


def parse_feed(xml_bytes: bytes, feed_name: str) -> list[Paper]:
    root = ET.fromstring(xml_bytes)
    out = []
    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        def get(*names):
            # Elements without children are falsy, so compare with None explicitly.
            for name in names:
                el = next((c for c in it if c.tag.split("}")[-1] == name), None)
                if el is not None:
                    return el
            return None

        title = get("title")
        link = get("link")
        href = (link.get("href") or link.text) if link is not None else ""
        summary = get("description", "summary", "content")
        when = get("pubDate", "published", "updated")
        d = _feed_date(when.text if when is not None else "")
        text = re.sub(r"<[^>]+>", " ", summary.text or "") if summary is not None else ""
        out.append(Paper(
            title=_clean(title.text if title is not None else ""),
            abstract=_clean(text)[:1500],
            url=_clean(href),
            venue=feed_name,
            published=d.isoformat() if d else "",
            source="feed",
            signals={"feed": feed_name},
        ))
    return out


def fetch_feeds(feeds: list[dict], lookback_days: int, today: date) -> list[Paper]:
    cutoff = (today - timedelta(days=lookback_days)).isoformat()
    out = []
    for f in feeds:
        items = parse_feed(_get(f["url"]), f.get("name") or f["url"])
        out.extend(p for p in items if p.published and cutoff <= p.published <= today.isoformat())
    return out


def newest_per_feed(posts: list[Paper], per_feed: int) -> list[Paper]:
    """Keep the newest few posts of each feed so a busy feed cannot crowd out the others."""
    by_feed: dict[str, list[Paper]] = {}
    for p in sorted(posts, key=lambda p: p.published, reverse=True):
        by_feed.setdefault(p.venue, []).append(p)
    return [p for ps in by_feed.values() for p in ps[:per_feed]]
