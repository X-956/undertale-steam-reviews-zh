import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from importlib.resources import files

import jieba
import pandas as pd

ASSETS = files("steam_reviews_zh").joinpath("assets")
RULES = json.loads(ASSETS.joinpath("meme_rules.json").read_text(encoding="utf-8"))
STOPWORDS = set(ASSETS.joinpath("stopwords.txt").read_text(encoding="utf-8").splitlines())
TOKENIZER = jieba.Tokenizer()
jieba.setLogLevel(30)
TOKENIZER.load_userdict(str(ASSETS.joinpath("userdict.txt")))
ALIASES = {"sans": "杉斯", "衫斯": "杉斯", "papyrus": "帕派瑞斯", "帕皮瑞斯": "帕派瑞斯",
           "toriel": "羊妈", "undyne": "鱼姐", "alphys": "艾菲斯"}


def normalize(text):
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[\u200b-\u200d\ufeff]", "", text)
    text = re.sub(r"\[/?(?:b|i|u|s|h[1-6]|spoiler|quote|list|olist|code|url|img)(?:=[^\]]*)?\]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text):
    tokens = []
    for token in TOKENIZER.cut(text):
        token = ALIASES.get(token.strip(), token.strip())
        if token and token not in STOPWORDS and re.search(r"[a-z\u4e00-\u9fff]", token):
            tokens.append(token)
    return tokens


def meme_candidates(text):
    hits = [{"rule": rule["id"], "category": rule["category"], "evidence": match.group(0)}
            for rule in RULES if (match := re.search(rule["pattern"], text, re.I | re.S))]
    # 字符画是形式候选；重复短句或单个表情不触发。
    art = sum(1 for character in text if "\u2800" <= character <= "\u28ff" or "\u2500" <= character <= "\u259f")
    if art >= 12:
        hits.append({"rule": "ascii_art", "category": "字符画", "evidence": f"框线/盲文图形字符 {art} 个"})
    return hits


def numeric(value, default=0):
    try:
        result = float(value)
        return result if pd.notna(result) and abs(result) != float("inf") else default
    except (ValueError, TypeError):
        return default


def make_features(records, as_of=None):
    now = pd.Timestamp(as_of or datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    rows = []
    for record in records:
        raw = record["review"]
        clean = normalize(raw)
        tokens = tokenize(clean)
        hits = meme_candidates(raw)
        author = record.get("author") or {}
        created = pd.to_datetime(numeric(record.get("timestamp_created"), None), unit="s", utc=True, errors="coerce")
        age = max(0, (now - created).total_seconds() / 86400) if pd.notna(created) else None
        chars = len(clean)
        digest = hashlib.sha256(clean.encode()).hexdigest()
        rows.append(dict(
            review_id=str(record["recommendationid"]), text=raw, clean_text=clean,
            tokens=" ".join(tokens), token_count=len(tokens), char_count=chars,
            chinese_ratio=round(len(re.findall(r"[\u4e00-\u9fff]", clean)) / max(1, chars), 4),
            language=record.get("language", "unknown"), voted_up=record.get("voted_up"),
            helpful=max(0, int(numeric(record.get("votes_up")))),
            funny=max(0, int(numeric(record.get("votes_funny")))),
            playtime_at_review_minutes=numeric(author.get("playtime_at_review"), None),
            created_at=created.isoformat() if pd.notna(created) else None, age_days=age,
            age_band="未知" if age is None else "≤30天" if age <= 30 else "31–365天" if age <= 365 else ">365天",
            length_band="≤20字" if chars <= 20 else "21–100字" if chars <= 100 else ">100字",
            meme_candidate=bool(hits), meme_types="；".join(sorted({hit["category"] for hit in hits})),
            meme_evidence="；".join(hit["rule"] + ":" + hit["evidence"] for hit in hits),
            localization_request=bool(re.search(r"汉化|中文|chinese|locali[sz]ation", clean)),
            template_group=digest[:16], annotation_split="test" if int(digest[:8], 16) % 5 == 0 else "dev",
        ))
    frame = pd.DataFrame(rows)
    if not frame.empty:
        repeats = Counter(frame["clean_text"])
        frame["same_text_count"] = frame["clean_text"].map(repeats)
    return frame, now.isoformat()
