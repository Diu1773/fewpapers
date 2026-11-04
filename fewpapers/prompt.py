"""Build the daily-pick prompt that an assistant's scheduled task runs."""
from __future__ import annotations

from .profile import Profile

T = {
    "open": "Open this file and read all of it:",
    "about": "It lists today's paper candidates in up to two tracks. Scores and signals only order "
             "the candidates; they do not decide importance.",
    "work_head": "Track work - my current work:",
    "work_rule": "From track work, pick at most {n}. A paper qualifies only if it would change what I do "
                 "in my current work soon: a method, dataset or code I could adopt directly; a result that "
                 "contradicts, overtakes or invalidates my approach; or another group solving the same "
                 "problem with the same kind of data. Being a possible comparison, reference or background, "
                 "or sharing a topic, does not qualify; nor does a software or data deposit I would not use "
                 "myself. Write the sentence as what I would do differently. If the honest sentence is "
                 "\"it could be compared with\" or \"it could serve as a reference\", leave the paper out.",
    "lm_head": "Track landmark - the field I follow:",
    "lm_rule": "From track landmark, pick at most {n}, and expect zero on most days. Include a paper only "
               "if people outside its subfield would still be talking about it a year from now: a new "
               "architecture, training method or paradigm, a scaling result or clear capability jump, a "
               "first demonstration that changes what is possible, or a resource a whole field will use. "
               "A solid result within one subfield, a single theorem, a single device or disease-model "
               "result, incremental benchmark gains, surveys and product announcements do not count, "
               "whoever wrote them. For each, write one sentence on what would change if it holds up.",
    "zero": "Most days the right answer is zero or one paper per track; never fill the slots for their own "
            "sake. Judge only from each title, abstract and signals; do not add claims the abstract does "
            "not make.",
    "shape": "Reply in {lang} in exactly this shape and nothing else (no greeting, no recap of the list):",
    "empty": "If a track has no pick, write one line saying so under its heading. If the file cannot be "
             "opened or its first line is more than two days old, reply with one line saying so.",
    "why_work": "<one sentence: where it touches my work>",
    "why_lm": "<one sentence: what changes if it holds up>",
}

LANG_NAME = {"en": "English", "ko": "Korean", "ja": "Japanese", "zh": "Chinese", "de": "German",
             "fr": "French", "es": "Spanish"}


def build_prompt(prof: Profile, url: str, lang: str = "en", n_work: int = 3, n_landmark: int = 3) -> str:
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
