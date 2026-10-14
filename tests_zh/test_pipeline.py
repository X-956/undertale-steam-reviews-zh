import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from steam_reviews_zh.analysis import analyze, cluster_topics, evaluate_labels, export_csv
from steam_reviews_zh.api import collect, read_records
from steam_reviews_zh.cli import create_demo
from steam_reviews_zh.features import make_features, meme_candidates


def review(number, text="音乐很好听", **extra):
    return dict(recommendationid=str(number), review=text, language="schinese", votes_up=0,
                votes_funny=0, author={"steamid": "private-author-id", "playtime_at_review": 60}, **extra)


class AcquisitionTests(unittest.TestCase):
    def test_resume_replays_page_without_losing_same_text_reviews(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reviews.jsonl"
            calls = []

            def page(parameters):
                calls.append(parameters)
                if parameters["cursor"] == "*":
                    return {"reviews": [review(1), review(2)], "cursor": "next", "total_matching": 3}
                if parameters["cursor"] == "next":
                    return {"reviews": [review(2), review(3)], "cursor": "end"}
                return {"reviews": [], "cursor": "end"}

            collect(path, max_reviews=2, delay=0, fetch=page)
            self.assertEqual(len(read_records(path)), 2)
            state = collect(path, max_reviews=0, resume=True, delay=0, fetch=page)
            records = read_records(path)
            self.assertEqual([r["recommendationid"] for r in records], ["1", "2", "3"])
            self.assertNotIn("steamid", records[0]["author"])
            self.assertTrue(state["complete"])
            self.assertEqual(calls[0]["num_per_page"], 2)
            with self.assertRaises(ValueError):
                collect(path, max_reviews=2, fetch=page)
            with self.assertRaises(ValueError):
                collect(path, language="english", resume=True, fetch=page)

    def test_repeated_cursor_is_not_claimed_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            state = collect(Path(directory) / "r.jsonl", max_reviews=0, delay=0,
                            fetch=lambda _: {"reviews": [review(1)], "cursor": "*"})
            self.assertFalse(state["complete"])
            self.assertEqual(state["stop_reason"], "repeated_or_missing_cursor")

    def test_truncated_last_line_recovers_from_saved_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "r.jsonl"
            collect(path, max_reviews=1, delay=0, fetch=lambda _: {"reviews": [review(1)], "cursor": "next"})
            with path.open("ab") as stream:
                stream.write(b'{"recommendationid": "2", "review": "')
            collect(path, max_reviews=2, resume=True, delay=0,
                    fetch=lambda _: {"reviews": [review(2)], "cursor": "last"})
            self.assertEqual(len(read_records(path)), 2)


class AnalysisTests(unittest.TestCase):
    def test_short_text_votes_and_localization_do_not_imply_meme(self):
        self.assertFalse(meme_candidates("好玩"))
        self.assertFalse(meme_candidates("我们需要中文，期待官方汉化。"))
        self.assertFalse(meme_candidates("Sans 这场战斗的设计很有挑战性。"))
        self.assertTrue(meme_candidates("你充满了决心。"))
        self.assertTrue(meme_candidates("不好玩，只玩了八百小时。"))
        first = review(1, "音乐不错")
        second = dict(first, recommendationid="2", votes_funny=99999)
        frame, _ = make_features([first, second], "2025-01-01")
        self.assertEqual(frame["meme_candidate"].tolist(), [False, False])
        self.assertEqual(frame["same_text_count"].tolist(), [2, 2])
        self.assertEqual(frame["annotation_split"].nunique(), 1)

    def test_empty_and_tiny_texts_do_not_crash(self):
        for texts in (["", "1", "好玩"], ["音乐很好听"], ["音乐很好听", "剧情让人感动"]):
            frame, _ = make_features([review(i, t) for i, t in enumerate(texts)], "2025-01-01")
            clustered, _, metrics = cluster_topics(frame, clusters=8)
            self.assertEqual(len(clustered), len(texts))
            self.assertLessEqual(metrics["actual_clusters"], len(set(texts)))

    def test_report_exports_and_blind_labels_survive_rerun(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "demo.jsonl"
            create_demo(source)
            hostile = review("html", '</script><script>alert("unsafe")</script> 音乐剧情')
            with source.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(hostile, ensure_ascii=False) + "\n")
            out = directory / "out"
            summary = analyze(source, out, clusters=4, demo=True)
            self.assertEqual(summary["reviews"], 31)
            self.assertGreater(summary["duplicate_text_excess"], 0)
            self.assertNotIn("precision", summary["evaluation"])
            report = (out / "report.html").read_text(encoding="utf-8")
            self.assertNotIn(hostile["review"], report)
            self.assertIn("\\u003c/script\\u003e", report)
            self.assertIn("人工构造", report)
            annotation_path = out / "annotation_blind.csv"
            annotation = pd.read_csv(annotation_path, keep_default_na=False)
            self.assertFalse({"helpful", "funny", "meme_candidate", "meme_evidence"} & set(annotation.columns))
            annotation.loc[0, "label"] = "non_meme"
            annotation.to_csv(annotation_path, index=False, encoding="utf-8-sig")
            analyze(source, out, clusters=4, demo=True)
            self.assertEqual(pd.read_csv(annotation_path).loc[0, "label"], "non_meme")

    def test_csv_formula_escape_and_missing_human_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.csv"
            export_csv(pd.DataFrame({"text": ["=1+1", "普通评论", "@SUM(1)"]}), path)
            saved = pd.read_csv(path)
            self.assertEqual(saved.loc[0, "text"], "'=1+1")
            self.assertEqual(saved.loc[2, "text"], "'@SUM(1)")
            frame, _ = make_features([review(1)], "2025-01-01")
            labels = Path(directory) / "labels.csv"
            pd.DataFrame({"review_id": ["1"], "label": [""]}).to_csv(labels, index=False)
            result = evaluate_labels(frame, labels)
            self.assertEqual(result["labeled"], 0)
            self.assertNotIn("f1", result["splits"]["test"])


if __name__ == "__main__":
    unittest.main()
