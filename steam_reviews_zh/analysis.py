"""可复现的文本基线及描述性互动统计。"""

import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import precision_recall_fscore_support, silhouette_score

from . import __version__
from .api import read_records, write_json
from .features import ASSETS, make_features


def cluster_topics(frame, clusters=8, seed=42):
    if clusters < 1:
        raise ValueError("聚类数必须大于 0。")
    frame = frame.copy()
    frame["topic"] = -1
    frame["x"] = 0.0
    frame["y"] = 0.0
    frame["topic_distance"] = np.nan
    usable = frame[frame["token_count"] >= 2].drop_duplicates("clean_text")
    metrics = {"requested_clusters": clusters, "unique_fit_texts": len(usable),
               "actual_clusters": 0, "silhouette_cosine": None}
    if usable.empty:
        return frame, [], metrics
    vectorizer = TfidfVectorizer(tokenizer=str.split, token_pattern=None, lowercase=False,
                                 ngram_range=(1, 2), min_df=2 if len(usable) >= 100 else 1,
                                 max_features=12000, sublinear_tf=True)
    try:
        matrix = vectorizer.fit_transform(usable["tokens"])
        # 稀疏词表可能让少数样本成为全零向量；保留单次出现词后重试。
        if np.any(matrix.getnnz(axis=1) == 0):
            vectorizer.set_params(min_df=1)
            matrix = vectorizer.fit_transform(usable["tokens"])
    except ValueError:
        vectorizer.set_params(min_df=1)
        matrix = vectorizer.fit_transform(usable["tokens"])
    n_clusters = min(clusters, max(1, len(usable) // 3))
    model = KMeans(n_clusters=n_clusters, random_state=seed, n_init=10)
    labels = model.fit_predict(matrix)
    distances = model.transform(matrix)[np.arange(len(usable)), labels]
    if matrix.shape[0] >= 2 and matrix.shape[1] >= 2:
        projected = TruncatedSVD(n_components=2, random_state=seed).fit_transform(matrix)
    else:
        projected = np.zeros((len(usable), 2))
    mapping = {text: (int(label), float(xy[0]), float(xy[1]), float(distance))
               for text, label, xy, distance in zip(usable["clean_text"], labels, projected, distances)}
    for index in frame.index:
        if frame.at[index, "clean_text"] in mapping:
            frame.loc[index, ["topic", "x", "y", "topic_distance"]] = mapping[frame.at[index, "clean_text"]]
    frame["topic"] = frame["topic"].astype(int)
    actual = len(set(labels))
    metrics["actual_clusters"] = actual
    if 1 < actual < matrix.shape[0]:
        try:
            metrics["silhouette_cosine"] = float(silhouette_score(
                matrix, labels, metric="cosine", sample_size=min(1000, len(labels)), random_state=seed))
        except ValueError:
            pass
    features = vectorizer.get_feature_names_out()
    topics = []
    for topic in sorted(set(labels)):
        members = frame[frame["topic"] == topic]
        keywords = features[model.cluster_centers_[topic].argsort()[-8:][::-1]].tolist()
        representatives = members.sort_values("topic_distance").drop_duplicates("clean_text").head(3)
        topics.append(dict(topic=int(topic), count=len(members), keywords=keywords,
                           examples=representatives[["review_id", "text"]].to_dict("records")))
    metrics["unclustered_reviews"] = int((frame["topic"] < 0).sum())
    return frame, topics, metrics


def interaction_table(frame, groups):
    return frame.groupby(groups, dropna=False).agg(
        n=("review_id", "size"), helpful_mean=("helpful", "mean"), helpful_median=("helpful", "median"),
        helpful_zero_share=("helpful", lambda values: float((values == 0).mean())),
        funny_mean=("funny", "mean"), funny_median=("funny", "median"),
        funny_zero_share=("funny", lambda values: float((values == 0).mean())),
    ).reset_index()


def csv_safe(value):
    # 防止打开外部评论 CSV 时被 Excel 当作公式；JSONL 始终保留原文。
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def export_csv(frame, path):
    safe = frame.copy()
    for column in safe.select_dtypes(include=["object", "string"]).columns:
        safe[column] = safe[column].map(csv_safe)
    safe.to_csv(path, index=False, encoding="utf-8-sig")


def evaluate_labels(frame, path):
    if path is None:
        return {"status": "未提供人工标签，未计算分类准确性。"}
    labels = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    if not {"review_id", "label"}.issubset(labels.columns):
        raise ValueError("标签文件必须包含 review_id、label 列。")
    if labels["review_id"].duplicated().any():
        raise ValueError("标签文件中存在重复 review_id，请先处理冲突。")
    allowed = {"", "meme", "non_meme", "uncertain"}
    if not set(labels["label"]).issubset(allowed):
        raise ValueError("label 只支持 meme / non_meme / uncertain / 空白。")
    unknown = set(labels["review_id"]) - set(frame["review_id"])
    joined = frame.merge(labels[["review_id", "label"]], on="review_id", how="inner")
    result = {"status": "以人工标签为参照；dev 用于修改规则，test 留作评估。",
              "unknown_ids": len(unknown), "labeled": int(joined["label"].isin(["meme", "non_meme"]).sum()),
              "uncertain": int((joined["label"] == "uncertain").sum()), "splits": {}}
    for split in ("dev", "test"):
        subset = joined[(joined["annotation_split"] == split) & joined["label"].isin(["meme", "non_meme"])]
        stats = {"n": len(subset), "positive_labels": int((subset["label"] == "meme").sum())}
        if len(subset):
            precision, recall, f1, _ = precision_recall_fscore_support(
                subset["label"] == "meme", subset["meme_candidate"], average="binary", zero_division=0)
            stats.update(precision=float(precision), recall=float(recall), f1=float(f1))
            if not stats["positive_labels"]:
                stats["warning"] = "没有人工正例，召回率与 F1 的 0 值没有评估意义。"
        result["splits"][split] = stats
    return result


def analyze(input_path, output, clusters=8, seed=42, labels=None, as_of=None, demo=False):
    input_path, output = Path(input_path), Path(output)
    records = read_records(input_path)
    if not records:
        raise ValueError("输入没有有效评论。")
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = input_path.with_suffix(input_path.suffix + ".meta.json")
    acquisition = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {
        "sampling": "unknown", "warning": "缺少采集元数据，不能判断样本是否完整。"}
    as_of = as_of or acquisition.get("captured_at")
    frame, reference_date = make_features(records, as_of=as_of)
    frame, topics, metrics = cluster_topics(frame, clusters, seed)
    interactions = interaction_table(frame, ["topic", "meme_candidate"])
    strata = interaction_table(frame, ["age_band", "length_band", "meme_candidate"])
    summary = dict(
        demo=demo, reviews=len(frame), unique_texts=frame["clean_text"].nunique(),
        duplicate_text_excess=len(frame) - frame["clean_text"].nunique(),
        meme_candidates=int(frame["meme_candidate"].sum()),
        localization_requests=int(frame["localization_request"].sum()),
        helpful_zero_share=float((frame["helpful"] == 0).mean()),
        funny_zero_share=float((frame["funny"] == 0).mean()),
        clustering=metrics, topics=topics, evaluation=evaluate_labels(frame, labels),
        interactions=interactions.to_dict("records"), strata=strata.to_dict("records"),
    )
    assets_hash = hashlib.sha256(b"".join(ASSETS.joinpath(name).read_bytes() for name in
                                          ("stopwords.txt", "userdict.txt", "meme_rules.json"))).hexdigest()
    metadata = dict(version=__version__, input_sha256=hashlib.sha256(input_path.read_bytes()).hexdigest(),
                    assets_sha256=assets_hash, seed=seed, requested_clusters=clusters,
                    analysis_as_of=reference_date, acquisition=acquisition,
                    dependencies={name: importlib.metadata.version(name) for name in
                                  ("numpy", "pandas", "scikit-learn", "jieba", "plotly")})
    export_csv(frame, output / "reviews.csv")
    export_csv(interactions, output / "interactions.csv")
    export_csv(strata, output / "age_length_strata.csv")
    # 不显示预测结果、投票或游玩时长，避免标注者受分析结论引导。
    annotation = frame[["review_id", "text", "template_group", "annotation_split"]].copy()
    annotation["label"] = ""
    annotation["meme_type"] = ""
    annotation["notes"] = ""
    annotation_path = output / "annotation_blind.csv"
    # 分析重跑不能覆盖用户已经标注的表格。
    if not annotation_path.exists():
        export_csv(annotation, annotation_path)
    write_json(output / "summary.json", summary)
    write_json(output / "run_metadata.json", metadata)
    from .report import write_report
    write_report(frame, summary, metadata, output / "report.html")
    return summary
