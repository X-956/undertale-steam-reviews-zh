"""公开 Steam 评论接口；游标分页、断点续采与最少字段保存。"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .console import print_message

ENDPOINT = "https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def read_records(path):
    records = {}
    with Path(path).open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                review_id = str(record["recommendationid"])
                if not review_id or not isinstance(record.get("review"), str):
                    raise ValueError("缺少评论编号或文本")
            except (ValueError, KeyError, TypeError) as error:
                raise ValueError(f"{path} 第 {number} 行不是有效评论：{error}") from error
            records[review_id] = record
    return list(records.values())


def request_page(parameters):
    url = ENDPOINT + "?" + urlencode({"input_json": json.dumps(parameters)})
    request = Request(url, headers={"User-Agent": "steam-reviews-zh/0.1 (course research)"})
    for attempt in range(5):
        try:
            with urlopen(request, timeout=45) as response:
                payload = json.load(response)
            payload = payload.get("response", payload)
            if not isinstance(payload.get("reviews"), list):
                raise ValueError("Steam 返回结构异常，未包含 reviews；请检查接口或稍后重试。")
            return payload
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 4:
                raise
            retry = error.headers.get("Retry-After", "")
            delay = min(float(retry), 60) if retry.isdigit() else 2 ** (attempt + 1)
        except (URLError, TimeoutError):
            if attempt == 4:
                raise
            delay = 2 ** (attempt + 1)
        time.sleep(delay)
    raise RuntimeError("Steam 请求失败")


def sanitize(record, appid, captured_at):
    keys = ("recommendationid", "language", "review", "timestamp_created", "timestamp_updated",
            "voted_up", "votes_up", "votes_funny", "weighted_vote_score", "comment_count",
            "steam_purchase", "received_for_free", "written_during_early_access", "refunded")
    result = {key: record.get(key) for key in keys}
    result["recommendationid"] = str(record["recommendationid"])
    author = record.get("author") or {}
    result["author"] = {key: author.get(key) for key in
                        ("num_reviews", "playtime_forever", "playtime_at_review")}
    result.update(appid=appid, captured_at=captured_at)
    return result


def collect(output, appid=391540, language="schinese", max_reviews=1000,
            resume=False, delay=1.0, fetch=request_page):
    """max_reviews 是累计条数上限；0 表示采到末页。原始文本不改写。"""
    if max_reviews < 0 or delay < 0 or appid <= 0:
        raise ValueError("条数和请求间隔不能为负，AppID 必须为正。")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata_path = output.with_suffix(output.suffix + ".meta.json")
    parameters = dict(appid=appid, languages=[language], review_type=0, purchase_type=1,
                      filter_offtopic_activity=False, filter=1)
    if output.exists() or metadata_path.exists():
        if not resume:
            raise ValueError("输出已存在。请换文件名，或使用 --resume 继续采集。")
        if not output.exists() or not metadata_path.exists():
            raise ValueError("断点续采需要同时保留 JSONL 与 .meta.json 文件。")
        state = json.loads(metadata_path.read_text(encoding="utf-8"))
        if state["parameters"] != parameters:
            raise ValueError("续采参数与原文件不一致。")
        # 只恢复写入中断造成的最后一条不完整记录；中间损坏仍明确报错。
        raw_bytes = output.read_bytes()
        if raw_bytes and not raw_bytes.endswith(b"\n"):
            last_line = raw_bytes.rsplit(b"\n", 1)[-1]
            try:
                json.loads(last_line)
            except (ValueError, UnicodeDecodeError):
                boundary = raw_bytes.rfind(b"\n") + 1
                output.write_bytes(raw_bytes[:boundary])
        existing = read_records(output)
        if state.get("complete"):
            return state
    else:
        existing = []
        state = dict(parameters=parameters, endpoint=ENDPOINT, started_at=utc_now(),
                     cursor="*", complete=False, sampling="recent_cursor", pages=0)
        output.touch()
        write_json(metadata_path, state)
    # 如上次保存数据后、保存游标前中断，去除重放页面产生的重复编号。
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for record in existing:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    temporary.replace(output)
    seen = {str(row["recommendationid"]) for row in existing}
    cursors = set()
    state.update(complete=False, count=len(seen), max_reviews=max_reviews)
    while not max_reviews or len(seen) < max_reviews:
        cursor = state["cursor"]
        if cursor in cursors:
            state["stop_reason"] = "repeated_cursor"
            break
        cursors.add(cursor)
        page_size = min(100, max_reviews - len(seen)) if max_reviews else 100
        page = fetch(dict(parameters, cursor=cursor, num_per_page=page_size))
        capture_time = utc_now()
        rows = page["reviews"]
        if "total_matching" in page:
            state["reported_total"] = page["total_matching"]
        if page.get("query_summary"):
            state.setdefault("query_summary", {}).update(page["query_summary"])
        with output.open("a", encoding="utf-8") as stream:
            for row in rows:
                key = str(row["recommendationid"])
                if key not in seen:
                    stream.write(json.dumps(sanitize(row, appid, capture_time), ensure_ascii=False) + "\n")
                    seen.add(key)
            stream.flush()
            os.fsync(stream.fileno())
        next_cursor = page.get("cursor")
        state.update(count=len(seen), captured_at=capture_time, pages=state["pages"] + 1)
        if not rows:
            state.update(complete=True, stop_reason="empty_page")
        elif not next_cursor or next_cursor == cursor:
            state["stop_reason"] = "repeated_or_missing_cursor"
        else:
            state["cursor"] = next_cursor
            state["stop_reason"] = "limit" if max_reviews and len(seen) >= max_reviews else "in_progress"
        write_json(metadata_path, state)
        print_message(f"已采集 {len(seen)} 条评论（第 {state['pages']} 页）")
        if state["complete"] or state["stop_reason"] == "repeated_or_missing_cursor":
            break
        if not max_reviews or len(seen) < max_reviews:
            time.sleep(delay)
    else:
        state["stop_reason"] = "limit"
    write_json(metadata_path, state)
    return state
