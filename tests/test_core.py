import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

from fewpapers.profile import ENV_PROFILE, load_profile
from fewpapers.prompt import build_prompt
from fewpapers.rank import load_library, score_landmark, score_papers
from fewpapers.sources import (Paper, abstract_from_inverted_index, newest_per_feed, parse_arxiv_atom,
                                 parse_feed, parse_hf_daily)
from fewpapers.store import dedupe, filter_unseen, render_markdown, update_seen, write_outputs

FIX = Path(__file__).parent / "fixtures"


def paper(title, abstract="", source="openalex", doi="", arxiv_id=""):
    return Paper(title=title, abstract=abstract, url="u", venue="v", published="2026-11-01",
                 source=source, doi=doi, arxiv_id=arxiv_id)


class TestSources(unittest.TestCase):
    def test_inverted_index_restores_word_order(self):
        inv = {"capacity": [1, 4], "battery": [0], "is": [2], "fading": [3]}
        self.assertEqual(abstract_from_inverted_index(inv), "battery capacity is fading capacity")
        self.assertEqual(abstract_from_inverted_index(None), "")

    def test_openalex_splits_journals_only_when_one_page_is_not_enough(self):
        from unittest import mock
        from fewpapers import sources

        def work(i):
            return {"id": f"https://openalex.org/W{i}", "title": f"T{i}", "publication_date": "2026-11-01"}

        def run(more_than_a_page):
            urls = []

            def fake_get(url, headers=None):
                urls.append(url)
                combined = "%7C" in url  # "|" joins ISSNs in the combined query
                cursor = "abc" if combined and more_than_a_page else None
                return json.dumps({"meta": {"next_cursor": cursor}, "results": [work(len(urls))]}).encode()

            env = {k: v for k, v in os.environ.items() if k != "OPENALEX_API_KEY"}
            with mock.patch.object(sources, "_get", fake_get), mock.patch.dict(os.environ, env, clear=True):
                out = sources.fetch_openalex(["1111-1111", "2222-2222"], [], 7, date(2026, 11, 3))
            return out, urls

        out, urls = run(False)
        self.assertEqual((len(out), len(urls)), (1, 1))  # one request when everything fits
        out, urls = run(True)
        self.assertEqual((len(out), len(urls)), (2, 3))  # no second page without a key: one query per journal
        self.assertTrue(all("publication_date%3Adesc" in u and "cursor=%2A" in u for u in urls))

    def test_arxiv_atom_parse(self):
        ps = parse_arxiv_atom((FIX / "arxiv.xml").read_bytes())
        self.assertEqual(len(ps), 2)
        self.assertEqual(ps[0].arxiv_id, "2611.01234")
        self.assertEqual(ps[0].doi, "10.48550/arxiv.2611.01234")
        self.assertEqual(ps[0].title, "Capacity fade from cycling data")
        self.assertEqual(ps[0].authors, ["A. Author", "B. Author"])
        self.assertEqual(ps[0].venue, "arXiv cond-mat.mtrl-sci")
        self.assertEqual(ps[0].affiliations, ["Cell Works Inc."])  # repeated affiliation kept once
        self.assertEqual(ps[1].affiliations, [])

    def test_openalex_affiliations_mark_companies_and_fill_missing(self):
        from unittest import mock
        from fewpapers import sources
        w = {"doi": "https://doi.org/10.1/x", "authorships": [
            {"institutions": [{"display_name": "Cell Works", "type": "company"}]},
            {"institutions": [{"display_name": "Some University", "type": "education"},
                              {"display_name": "Cell Works", "type": "company"}]}]}
        self.assertEqual(sources.openalex_affiliations(w), ["Cell Works (company)", "Some University"])
        a, b = paper("A", doi="10.1/x"), paper("B", doi="10.1/y")
        b.affiliations = ["Kept Lab"]
        urls = []
        def fake_get(url, headers=None):
            urls.append(url)
            return json.dumps({"results": [w]}).encode()
        with mock.patch.object(sources, "_get", fake_get):
            self.assertEqual(sources.add_affiliations([a, b]), 1)
        self.assertEqual(len(urls), 1)  # only the paper without affiliations is asked for
        self.assertIn("10.1%2Fx", urls[0])
        self.assertNotIn("10.1%2Fy", urls[0])
        self.assertEqual(a.affiliations, ["Cell Works (company)", "Some University"])
        self.assertEqual(b.affiliations, ["Kept Lab"])


class TestStore(unittest.TestCase):
    def test_dedupe_prefers_journal_and_keeps_abstract(self):
        a = paper("Capacity Fade from Cycling Data", "long abstract", source="arxiv", arxiv_id="2611.01234v2")
        b = paper("Capacity fade from cycling data.", "", source="openalex", doi="10.1/x")
        out = dedupe([a, b])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].source, "openalex")
        self.assertEqual(out[0].abstract, "long abstract")

    def test_dedupe_matches_arxiv_doi(self):
        a = paper("Title one", source="arxiv", arxiv_id="2611.00001", doi="10.48550/arxiv.2611.00001")
        b = paper("Title one (preprint record)", source="openalex", doi="10.48550/arxiv.2611.00001")
        self.assertEqual(len(dedupe([a, b])), 1)

    def test_seen_filters_and_expires(self):
        p = paper("A paper", doi="10.1/a")
        seen = update_seen({}, [p], date(2026, 11, 1))
        self.assertEqual(filter_unseen([p, paper("Other", doi="10.1/b")], seen)[0].title, "Other")
        later = update_seen(seen, [], date(2027, 3, 1), keep_days=90)
        self.assertEqual(later, {})

    def test_markdown_truncates_and_reports_errors(self):
        p = paper("T", "word " * 400)
        md = render_markdown({"work": [p]}, date(2026, 11, 3), {"fetched": 1}, {"ads": "HTTPError"})
        self.assertIn("2026-11-03", md.splitlines()[0])
        self.assertIn("ads (HTTPError)", md)
        self.assertLess(len(md), 1500)

    def test_markdown_lists_companies_first_and_caps_affiliations(self):
        p = paper("T", "x")
        p.affiliations = ["U1", "U2", "Firm (company)", "U3", "U4", "U5"]
        md = render_markdown({"work": [p]}, date(2026, 11, 3), {}, {})
        self.assertIn("- affiliations: Firm (company); U1; U2; U3; +2 more", md)
        self.assertNotIn("affiliations", render_markdown({"work": [paper("T", "x")]}, date(2026, 11, 3), {}, {}))

    def test_write_outputs_prunes_archive(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out / "archive").mkdir()
            (out / "archive" / "2026-01-01.md").write_text("old")
            write_outputs(out, {"work": [paper("T", "x")]}, date(2026, 11, 3), {}, {})
            self.assertFalse((out / "archive" / "2026-01-01.md").exists())
            self.assertTrue((out / "archive" / "2026-11-03.md").exists())
            self.assertEqual(json.loads((out / "latest.json").read_text())["tracks"]["work"][0]["title"], "T")


class TestLandmark(unittest.TestCase):
    def test_hf_daily_parse(self):
        items = [{"paper": {"id": "2611.00001", "title": "A new architecture", "summary": "We propose.",
                            "upvotes": 150, "githubStars": 900, "authors": [{"name": "X"}],
                            "organization": {"name": "google", "fullname": "Google"}},
                  "publishedAt": "2026-11-02T00:00:00Z", "numComments": 4}]
        p = parse_hf_daily(items)[0]
        self.assertEqual(p.arxiv_id, "2611.00001")
        self.assertEqual(p.signals["upvotes"], 150)
        self.assertEqual(p.signals["org"], "Google")

    def test_feed_parse_reads_dates_of_childless_elements(self):
        ps = parse_feed((FIX / "feed.xml").read_bytes(), "Lab Blog")
        self.assertEqual([p.published for p in ps], ["2026-11-02", "2026-10-01"])
        self.assertEqual(ps[0].abstract, "A new model family.")

    def test_landmark_ranking(self):
        def hf(title, up, org=""):
            p = paper(title, "x", source="hf")
            p.signals = {"upvotes": up, "github_stars": 0, "org": org}
            return p
        ps = [hf("Low", 5), hf("Popular", 150), hf("Lab paper", 10, "Google DeepMind"), hf("Mid", 40)]
        out = score_landmark(ps, ["deepmind"], min_upvotes=30)
        self.assertEqual([p.title for p in out][:2], ["Popular", "Mid"])
        self.assertNotIn("Low", [p.title for p in out])
        self.assertEqual(next(p for p in out if p.title == "Lab paper").signals["watched_lab"], "deepmind")

    def test_newest_per_feed(self):
        def post(feed, day):
            p = paper(f"{feed} {day}", "x", source="feed")
            p.venue, p.published = feed, f"2026-11-0{day}"
            return p
        ps = [post("Busy", d) for d in (1, 2, 3, 4)] + [post("Quiet", 1)]
        out = newest_per_feed(ps, 2)
        self.assertEqual(sorted(p.title for p in out), ["Busy 3", "Busy 4", "Quiet 1"])


class TestPrompt(unittest.TestCase):
    def test_prompt_covers_enabled_tracks(self):
        os.environ[ENV_PROFILE] = '[profile]\ninterests = "battery capacity fade"\n[landmark]\nfield = "machine learning"\n'
        try:
            text = build_prompt(load_profile(), "https://example.org/latest.md", "ko", 5, 3)
        finally:
            del os.environ[ENV_PROFILE]
        self.assertIn("https://example.org/latest.md", text)
        self.assertIn("battery capacity fade", text)
        self.assertIn("machine learning", text)
        self.assertIn("Korean", text)
        self.assertIn("[work]", text)
        self.assertIn("[landmark]", text)
        self.assertLess(text.index("copied exactly"), text.index("[work]"))  # the reply opens with the file's own lines
        os.environ[ENV_PROFILE] = '[profile]\ninterests = "battery capacity fade"\n'
        try:
            private = build_prompt(load_profile(), repo="me/runner")
        finally:
            del os.environ[ENV_PROFILE]
        self.assertIn("GitHub app", private)
        self.assertIn("Repository me/runner, branch main, file output/latest.md", private)
        self.assertNotIn("http", private.split("\n\n")[0])
        os.environ[ENV_PROFILE] = '[profile]\ninterests = "battery capacity fade"\n[landmark]\nfield = "energy storage"\n'
        try:
            plain = build_prompt(load_profile(), "u")
            rich = build_prompt(load_profile(), "u", industry=True)
        finally:
            del os.environ[ENV_PROFILE]
        self.assertNotIn("Industry:", plain)
        self.assertIn("name no stock tickers", rich)
        self.assertLess(rich.index("   Industry: ..."), rich.rindex("   <link>"))


class TestRank(unittest.TestCase):
    def test_relevant_ranks_first_and_noise_dropped(self):
        ps = [
            paper("High-altitude wind energy assessment", "wind turbines and energy markets"),
            paper("Predicting battery capacity fade from early cycles", "lithium-ion capacity fade state of health prediction"),
            paper("Correction to: Capacity fade models", "capacity fade"),
            paper("Solar cell passivation", "capacity fade mention"),
        ]
        out = score_papers(ps, "predicting lithium-ion battery capacity fade",
                           ["capacity fade", "state of health"], ["solar cell"], [])
        titles = [p.title for p in out]
        self.assertEqual(titles[0], "Predicting battery capacity fade from early cycles")
        self.assertNotIn("Correction to: Capacity fade models", titles)
        self.assertNotIn("Solar cell passivation", titles)

    def test_library_formats(self):
        with tempfile.TemporaryDirectory() as d:
            bib = Path(d) / "lib.bib"
            bib.write_text("@article{a,\n  title = {Fade at high temperature},\n  abstract = {cycling data},\n}\n", encoding="utf-8")
            self.assertEqual(load_library(bib), ["Fade at high temperature cycling data"])
            js = Path(d) / "lib.jsonl"
            js.write_text('{"title": "T", "abstract": "A"}\n', encoding="utf-8")
            self.assertEqual(load_library(js), ["T A"])


class TestProfile(unittest.TestCase):
    def test_env_overrides_files(self):
        os.environ[ENV_PROFILE] = '[profile]\nkeywords = ["capacity fade"]\n[sources.arxiv]\ncategories = ["cond-mat.mtrl-sci"]\n'
        try:
            p = load_profile()
            self.assertEqual(p.keywords, ["capacity fade"])
            self.assertEqual(p.arxiv_categories, ["cond-mat.mtrl-sci"])
        finally:
            del os.environ[ENV_PROFILE]

    def test_empty_profile_rejected(self):
        os.environ[ENV_PROFILE] = "[profile]\n"
        try:
            with self.assertRaises(ValueError):
                load_profile()
        finally:
            del os.environ[ENV_PROFILE]

    def test_collect_fails_when_a_whole_track_fails_but_still_writes(self):
        from unittest import mock
        from fewpapers import __main__ as cli

        def down(*a, **k):
            raise OSError("HTTP Error 429")

        lm = [("feeds", lambda: [paper("A lab post")], lambda ps: ps, 5)]
        os.environ[ENV_PROFILE] = ('[profile]\nkeywords = ["capacity fade"]\n[sources.arxiv]\n'
                                   'categories = ["cond-mat.mtrl-sci"]\n[landmark]\nenabled = true\n')
        try:
            with tempfile.TemporaryDirectory() as d, mock.patch.object(cli, "_landmark_jobs", lambda p, t: lm):
                with mock.patch.object(cli, "fetch_arxiv", down):
                    code = cli.main(["collect", "--out", d, "--no-state"])
                    md = (Path(d) / "latest.md").read_text(encoding="utf-8")
                self.assertEqual(code, 1)
                self.assertIn("arxiv (OSError)", md)
                self.assertIn("A lab post", md)  # the track that worked is still listed
                with mock.patch.object(cli, "fetch_arxiv", lambda *a, **k: []):
                    self.assertEqual(cli.main(["collect", "--out", d, "--no-state"]), 0)
        finally:
            del os.environ[ENV_PROFILE]

    def test_landmark_attention_lists_follow_the_field(self):
        from fewpapers import __main__ as cli
        from fewpapers.profile import Landmark
        lm = Landmark(enabled=True, topic="lithium-ion battery energy storage", keywords=["battery"])
        a, b = paper("Speech recognition at scale", "audio transcription model"), paper(
            "Solid-state battery with long cycle life", "energy storage cells")
        a.score, b.score = 0.9, 0.2
        out = cli._by_field([a, b], lm)
        self.assertEqual([p.title for p in out][0], "Solid-state battery with long cycle life")
        self.assertEqual(b.signals["attention"], 0.2)  # the attention score is kept as a signal
        self.assertEqual(cli._by_field([a], Landmark()), [a])  # no field: order unchanged

    def test_example_profile_loads(self):
        p = load_profile(str(Path(__file__).parent.parent / "profile.example.toml"))
        self.assertTrue(p.interests and p.arxiv_categories and p.openalex_issns)


if __name__ == "__main__":
    unittest.main()
