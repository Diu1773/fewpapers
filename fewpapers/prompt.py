"""Build the daily-pick prompt that an assistant's scheduled task runs."""
from __future__ import annotations

from .profile import Profile

T = {
    "open": "Open this file and read all of it:",
    "open_repo": "Use the GitHub app to read this file in full. It is in a private repository, so do not use "
                 "web search, the browser or code downloads for it. If the GitHub app cannot open it, try once "
                 "more before reporting the error.",
    "repo_file": "Repository {repo}, branch main, file output/latest.md",
    "about": "It lists today's paper candidates in up to two tracks. Scores and signals only order "
             "the candidates; they do not decide importance.",
    "work_head": "My current work:",
    "field_head": "The fields I follow:",
    "scale": "Score every candidate from 1 to 5 for how much it matters to me. Report only those that score 3 "
             "or more, at most {n} a day, highest first. Most days nothing reaches 3; never raise a score to "
             "fill the reply.",
    "s5": "5 - It will be general news outside science within weeks and changes what people think AI or "
          "science can do; a few a year worldwide. Give 5 only when broad attention is already visible (very "
          "high Hacker News points, major news outlets) or the abstract shows a first of its kind on that "
          "scale. Examples: AlphaFold2, GPT-3, CRISPR-Cas9 genome editing, the first detection of "
          "gravitational waves.",
    "s4": "4 - People outside its field will still talk about it and cite it in a few years; the kind of "
          "result that ends up in a field's list of results of the year. At most about one a month across "
          "everything. Examples: Diffusion Policy, 3D Gaussian Splatting, GraphCast, LoRA.",
    "s3": "3 - Either it would change what I do in my current work soon (a method, dataset or code I would "
          "adopt, a result that contradicts or overtakes my approach, another group solving the same problem "
          "with the same kind of data), or it is a result that people outside its subfield are already "
          "talking about. Being a possible comparison or reference, or sharing a topic, is not enough; "
          "neither are incremental benchmark gains, surveys or product announcements, whoever wrote them.",
    "s12": "1-2 - Leave out.",
    "claims": "A result many people are already discussing (high Hacker News points) can score even before it "
              "is a reviewed paper; then say it is a claim not yet checked by others. Judge only from each "
              "title, abstract and signals; do not add claims the abstract does not make.",
    "shape": "Reply in {lang}, in exactly this shape and nothing else (no greeting, no recap):",
    "headline": "<one line for the phone notification: each reported paper as [score] and a short title of at "
                "most 25 characters, joined by \" · \", for example \"[4] Nuclear clock realized · [3] Cn2 "
                "profiles by stability\". If nothing scores 3 or more, write that there is nothing today and "
                "skip to the last two lines.>",
    "item": "[<score>] <short title> (<venue or org>) - <my work or the world>",
    "why": "   <one sentence: for my work, what I would do differently; for the world, what changes if it holds "
           "up. Say it is a claim not yet checked for results that are not reviewed papers.>",
    "industry": "   <for scores 4 and 5 only, four short lines starting with \"Industry:\", \"Made by:\", "
                "\"Stage:\", \"News:\". Industry: the industry and part of its value chain it touches. Made by: "
                "companies marked \"(company)\" in the affiliations line or named in the org signal, or none. "
                "Stage: lab result, code or model released, trial phase, or product. News: use web search only "
                "for this line; the first major outlet and date, or none yet. This is information about "
                "industries, not investment advice: no stock tickers, no buy or sell views.>",
    "link": "   <link>",
    "echo": ["<the file's first line, copied exactly>", "<the file's line that starts with \"Fetched\", copied exactly>"],
    "stale": "If the file cannot be opened or its first line is more than two days old, reply with one line "
             "saying so.",
}

LANG_NAME = {"en": "English", "ko": "Korean", "ja": "Japanese", "zh": "Chinese", "de": "German",
             "fr": "French", "es": "Spanish"}


def build_prompt(prof: Profile, url: str = "", lang: str = "en", max_picks: int = 3,
                 repo: str = "", industry: bool = False) -> str:
    """url: address of output/latest.md. repo: the repository that holds it, such as me/runner, opened
    with the assistant's GitHub app. The reply opens with one notification line and lists only
    candidates scored 3 or more on a 1-5 scale."""
    t = T
    head = [t["open_repo"], t["repo_file"].format(repo=repo)] if repo else [t["open"], url]
    lines = head + ["", t["about"], ""]
    if prof.work_enabled:
        lines += [t["work_head"], prof.interests or ", ".join(prof.keywords), ""]
    if prof.landmark.enabled:
        lines += [t["field_head"], prof.landmark.topic or "the fields covered by the landmark track", ""]
    lines += [t["scale"].format(n=max_picks), "", t["s5"], t["s4"], t["s3"], t["s12"], "", t["claims"], ""]
    lines += [t["shape"].format(lang=LANG_NAME.get(lang, lang)), "", t["headline"], "", t["item"], t["why"]]
    if industry:
        lines.append(t["industry"])
    lines += [t["link"], ""] + t["echo"] + ["", t["stale"]]
    return "\n".join(lines).strip() + "\n"
