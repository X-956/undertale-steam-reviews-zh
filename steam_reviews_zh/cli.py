import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError

from .api import collect, write_json


def create_demo(path):
    """合成样本仅用于演示；没有真实玩家或真实投票。"""
    texts = [
        "战斗系统的弹幕躲避很有意思，和平线设计也很特别。", "弹幕战斗需要练习，打骨让我反复失败。",
        "和平线通关后又试了中立线，选择改变了故事。", "屠杀线战斗很难，手残玩家花了很久。",
        "剧情里的选择让我反思，角色的对白写得细腻。", "羊妈的剧情让我很难过，和平线结局很温暖。",
        "鱼姐和帕派瑞斯的故事很有趣，角色之间的关系很动人。", "剧情叙事与存档机制结合得很好。",
        "音乐非常好听，战斗曲的节奏和场景很搭。", "像素画看起来简单，音乐营造的氛围很丰富。",
        "通关后还在听原声音乐，旋律很容易记住。", "音乐和角色主题的呼应值得反复听。",
        "希望提供官方中文，英文剧情读起来比较吃力。", "我们需要中文，希望后续能加入汉化支持。",
        "中文翻译对理解对白很重要，汉化补丁安装不太方便。", "英文能力有限，期待官方中文。",
        "看到存档点，你充满了决心。", "写完作业再打开游戏，我充满了决心。",
        "我是 sans，今天来评论区上班。", "不好玩，只玩了八百小时而已。",
        "每一个赞都能喂饱这只小猫。", "┌──────────────┐\n│  一只合成示例猫  │\n└──────────────┘",
        "好玩", "神作", "好玩", "1", "good", "剧情不错，但是战斗操作有点难。",
        "羊妈让我充满了决心，角色对白很温柔。", "希望中文本地化早日完成，便于理解剧情。",
    ]
    rows = []
    for index, text in enumerate(texts):
        rows.append(dict(recommendationid=f"demo-{index:03}", review=text, language="schinese",
                         appid=391540, timestamp_created=1704067200 + index * 86400 * 12,
                         voted_up=index % 7 != 0, votes_up=(index * 7) % 13 if index % 3 == 0 else 0,
                         votes_funny=(index * 3) % 8 if index % 4 == 0 else 0,
                         author={"playtime_at_review": 120 + index * 60}))
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    write_json(path.with_suffix(path.suffix + ".meta.json"), {
        "sampling": "synthetic_demo", "captured_at": "2025-01-01T00:00:00+00:00",
        "complete": True, "warning": "人工构造数据，非真实玩家评论，非研究结果。"})


def main(argv=None):
    parser = argparse.ArgumentParser(description="UNDERTALE 中文 Steam 评论分析（Python 3.10+）")
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("fetch", help="采集公开评论，默认 UNDERTALE 简体中文")
    fetch.add_argument("--appid", type=int, default=391540, help="Steam AppID，默认 391540")
    fetch.add_argument("--language", default="schinese", help="Steam 语言标签，默认 schinese")
    fetch.add_argument("--max-reviews", type=int, default=1000, help="累计条数上限；0 表示采至末页")
    fetch.add_argument("--output", default="data/undertale-zh.jsonl", help="JSONL 输出路径")
    fetch.add_argument("--resume", action="store_true", help="从同名元数据文件继续采集")
    fetch.add_argument("--delay", type=float, default=1, help="分页请求间隔秒数，默认 1")
    analysis = commands.add_parser("analyze", help="统计、聚类、规则筛选及生成离线报告")
    analysis.add_argument("--input", required=True, help="fetch 产生的 JSONL 文件")
    analysis.add_argument("--output", default="outputs/undertale", help="分析输出目录")
    analysis.add_argument("--clusters", type=int, default=8, help="请求主题数，少量样本会自动减小")
    analysis.add_argument("--seed", type=int, default=42, help="随机种子")
    analysis.add_argument("--labels", help="人工标注 CSV，可选")
    analysis.add_argument("--as-of", help="计算评论年龄的 ISO 时间；默认采集时间")
    demo = commands.add_parser("demo", help="用合成数据运行离线示例")
    demo.add_argument("--output", default="outputs/demo", help="演示输出目录")
    args = parser.parse_args(argv)
    try:
        if args.command == "fetch":
            state = collect(args.output, args.appid, args.language, args.max_reviews, args.resume, args.delay)
            print(f"采集完成：{state['count']} 条；停止原因：{state['stop_reason']}；{args.output}")
        else:
            from .analysis import analyze
            if args.command == "demo":
                destination = Path(args.output)
                destination.mkdir(parents=True, exist_ok=True)
                source = destination / "synthetic_reviews.jsonl"
                create_demo(source)
                result = analyze(source, destination, clusters=5, demo=True)
            else:
                result = analyze(args.input, args.output, args.clusters, args.seed, args.labels, args.as_of)
            print(f"已分析 {result['reviews']} 条评论，识别 {result['meme_candidates']} 条玩梗候选。")
            print(f"离线报告：{Path(args.output).resolve() / 'report.html'}")
        return 0
    except (ValueError, OSError, HTTPError, URLError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
