"""Build the daily-pick prompt that an assistant's scheduled task runs."""
from __future__ import annotations

from .profile import Profile

T = {
    "open": "Open this file and read all of it:",
    "about": "It lists today's paper candidates in up to two tracks. Scores and signals only order "
             "the candidates; they do not decide importance.",
    "work_head": "Track work - my current work:",
    "work_rule": "From track work, pick at most {n}. Include a paper only if you can write one concrete "
                 "sentence on which part of my current work it changes, supports, or gives a comparison "
                 "for. A similar topic alone does not count.",
    "lm_head": "Track landmark - the field I follow:",
    "lm_rule": "From track landmark, pick at most {n}. Include a paper only if it plausibly changes how "
               "the field works: a new architecture, training method or paradigm, a scaling result, a "
               "clear capability jump, or a widely reusable resource. Incremental benchmark gains, "
               "surveys and product announcements do not count, whoever wrote them. For each, write one "
               "sentence on what would change if it holds up.",
    "zero": "Zero picks in a track is a valid answer. Judge only from each title, abstract and signals; "
            "do not add claims the abstract does not make.",
    "shape": "Reply in {lang} in exactly this shape and nothing else (no greeting, no recap of the list):",
    "empty": "If a track has no pick, write one line saying so under its heading. If the file cannot be "
             "opened or its first line is more than two days old, reply with one line saying so.",
    "why_work": "<one sentence: where it touches my work>",
    "why_lm": "<one sentence: what changes if it holds up>",
}

LANG_NAME = {"en": "English", "ko": "Korean", "ja": "Japanese", "zh": "Chinese", "de": "German",
             "fr": "French", "es": "Spanish"}


def build_prompt(prof: Profile, url: str, lang: str = "en", n_work: int = 5, n_landmark: int = 3) -> str:
    t = T
    lines = [t["open"], url, "", t["about"], ""]
    shape = []
    if prof.work_enabled:
        interests = prof.interests or ", ".join(prof.keywords)
        lines += [t["work_head"], interests, "", t["work_rule"].format(n=n_work), ""]
        shape += ["[work]", "1. <short title> (<venue>)", f"   {t['why_work']}", "   <link>", ""]
    if prof.landmark.enabled:
        field = prof.landmark.topic or "the fields covered by the landmark track"
        lines += [t["lm_head"], field, "", t["lm_rule"].format(n=n_landmark), ""]
        shape += ["[landmark]", "1. <short title> (<org or venue>)", f"   {t['why_lm']}", "   <link>", ""]
    lines += [t["zero"], "", t["shape"].format(lang=LANG_NAME.get(lang, lang)), ""]
    lines += shape
    lines += [t["empty"]]
    return "\n".join(lines).strip() + "\n"
