"""生成无需联网的交互报告，外部评论只作为纯文本展示。"""

import html
import json

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs


def plot(figure, title):
    horizontal_legend = figure.layout.legend.orientation == "h"
    figure.update_layout(template="plotly_dark", title=title, paper_bgcolor="#151823",
                         plot_bgcolor="#151823", font=dict(family="Arial, Microsoft YaHei, Noto Sans CJK SC, sans-serif"),
                         margin=dict(l=50, r=24, t=65, b=110 if horizontal_legend else 50),
                         height=420 if horizontal_legend else 370)
    return figure.to_html(full_html=False, include_plotlyjs=False, config={"displaylogo": False})


def write_report(frame, summary, metadata, path):
    topic_names = {item["topic"]: f"主题 {item['topic']} · {' / '.join(item['keywords'][:3])}"
                   for item in summary["topics"]}
    topic_names[-1] = "未聚类 · 文本信息不足"
    display = frame.copy()
    display["topic_name"] = display["topic"].map(topic_names)
    display["topic_short"] = display["topic"].map(lambda value: f"主题 {value}")
    display["candidate_label"] = display["meme_candidate"].map({True: "疑似玩梗", False: "未命中规则"})
    counts = display.groupby("topic_name").size().reset_index(name="评论数")
    panels = [plot(px.bar(counts, x="评论数", y="topic_name", orientation="h",
                          labels={"topic_name": "主题"}, color_discrete_sequence=["#f56475"]), "评论主题分布")]
    eligible = display[display["topic"] >= 0].drop_duplicates("clean_text")
    sampled = eligible.sample(min(3000, len(eligible)), random_state=42)
    if len(sampled):
        # 图中只显示编号；原文在下方通过 textContent 安全呈现。
        scatter = px.scatter(sampled, x="x", y="y", color="topic_short", symbol="candidate_label",
                             symbol_map={"疑似玩梗": "diamond", "未命中规则": "circle"},
                             hover_data=["review_id", "topic_name"], labels={"x": "SVD 维度 1", "y": "SVD 维度 2",
                             "topic_short": "主题", "topic_name": "关键词", "candidate_label": "规则候选"})
        shown = set()
        for trace in scatter.data:
            name = trace.name.split(",")[0]
            trace.showlegend = name not in shown
            trace.name = name
            shown.add(name)
        scatter.update_layout(legend=dict(orientation="h", x=0, y=-0.25, title_text=""))
        panels.append(plot(scatter, "主题投影 · 颜色区分主题"))
    compare = display.groupby("candidate_label").agg(有帮助=("helpful", "mean"), 欢乐=("funny", "mean")).reset_index()
    panels.append(plot(px.bar(compare, x="candidate_label", y=["有帮助", "欢乐"], barmode="group",
                              labels={"candidate_label": "", "value": "平均累计票数", "variable": "投票类型"}),
                       "互动概览 · 未调整曝光与时间"))
    dates = pd.to_datetime(display["created_at"], utc=True, errors="coerce")
    monthly = dates.dt.strftime("%Y-%m").value_counts().sort_index().rename_axis("月份").reset_index(name="评论数")
    timeline = px.line(monthly, x="月份", y="评论数", markers=True)
    timeline.update_xaxes(type="category")
    panels.append(plot(timeline, "样本中的评论发布时间"))
    rules = display.loc[display["meme_types"] != "", "meme_types"].str.split("；").explode().value_counts()
    panels.append(plot(go.Figure(go.Bar(x=rules.index.tolist(), y=rules.tolist(), marker_color="#eac873")),
                       "玩梗候选类型 · 一条评论可有多个标签"))
    # 精简后的浏览器数据；不嵌入作者标识。
    rows = display[["review_id", "text", "topic", "topic_name", "candidate_label", "meme_types", "meme_evidence",
                    "helpful", "funny", "age_band", "length_band", "same_text_count"]].to_dict("records")
    payload = json.dumps(rows, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    options = "".join(f'<option value="{key}">{html.escape(value)}</option>' for key, value in sorted(topic_names.items()))
    sampling = metadata["acquisition"].get("sampling", "unknown")
    if summary["demo"]:
        notice = "演示数据：所有评论均为人工构造，用于检查流程，不能作为课程研究结果。"
    elif sampling == "recent_cursor":
        notice = "按最新顺序采集的评论样本；未采到末页时偏向近期评论，不代表全部玩家。"
    else:
        notice = "样本来源/抽样方式：" + str(sampling) + "。需结合采集元数据解释，不代表玩家总体。"
    cards = [("评论", summary["reviews"]), ("独立文本", summary["unique_texts"]),
             ("玩梗候选", summary["meme_candidates"]), ("有帮助零票占比", f'{summary["helpful_zero_share"]:.1%}')]
    card_html = "".join(f'<div class="card"><span>{name}</span><strong>{value}</strong></div>' for name, value in cards)
    evaluations = html.escape(json.dumps(summary["evaluation"], ensure_ascii=False, indent=2))
    strata_html = pd.DataFrame(summary["strata"]).round(3).rename(columns={
        "age_band": "评论年龄", "length_band": "长度", "meme_candidate": "玩梗候选", "n": "条数",
        "helpful_mean": "有帮助均值", "helpful_median": "有帮助中位数", "helpful_zero_share": "有帮助零票比例",
        "funny_mean": "欢乐均值", "funny_median": "欢乐中位数", "funny_zero_share": "欢乐零票比例",
    }).to_html(index=False, escape=True, border=0)
    page = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>UNDERTALE 中文评论观察</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#0b0d14;color:#e9edf5;font:15px/1.7 Arial,"Microsoft YaHei","Noto Sans CJK SC",sans-serif}
main{max-width:1240px;margin:auto;padding:38px 24px}h1{font-size:clamp(25px,4vw,42px);margin:6px 0 12px}h2{font-size:23px;margin-top:36px}
.eyebrow{color:#f56475;letter-spacing:3px;font-size:13px}.muted{color:#a8afc4}.notice{border-left:3px solid #eac873;padding:12px 18px;background:#1b1c24}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:24px 0}.card{padding:17px 22px;background:#151823;border:1px solid #272d3d;border-radius:9px}.card span{color:#a8afc4;display:block}.card strong{font-size:30px}
.plots{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.panel{min-width:0;background:#151823;border-radius:10px;overflow:hidden}
input,select,button{font:inherit;color:inherit;background:#1b2030;border:1px solid #434d64;border-radius:5px;padding:8px 12px}input{flex:1;min-width:180px}.filters{display:flex;gap:10px;flex-wrap:wrap}
.reviews{margin-top:20px}.review{padding:18px 20px;background:#151823;border:1px solid #292e40;border-radius:8px;margin-bottom:10px}.text{white-space:pre-wrap;overflow-wrap:anywhere;max-height:300px;overflow:auto;margin:12px 0}.badge{color:#eac873}
.tablewrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:9px;text-align:left;border-bottom:1px solid #30364a;white-space:nowrap}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#151823;padding:16px}
footer{margin-top:40px;border-top:1px solid #30364a;padding-top:16px;color:#a8afc4}@media(max-width:760px){.plots{grid-template-columns:1fr}.cards{grid-template-columns:repeat(2,1fr)}main{padding:22px 14px}}
</style><script>__PLOTLY__</script></head><body><main>
<div class="eyebrow">STEAM REVIEWS · 中文分析</div><h1>UNDERTALE 中文评论观察</h1>
<p class="muted">评论内容、社区表达与「有帮助 / 欢乐」互动。主题编号由算法生成，关键词需要人工命名。</p>
<div class="notice">__NOTICE__</div><div class="cards">__CARDS__</div>
<div class="plots">__PANELS__</div>
<p class="muted">投影合并相同文本，最多展示 3,000 点；圆点为未命中规则，菱形为玩梗候选。二维距离不能证明类别边界，未命中规则不等于不是玩梗。</p>
<h2>评论浏览与规则核验</h2><div class="filters"><input id="search" aria-label="搜索评论" placeholder="搜索评论或编号…">
<select id="topic" aria-label="筛选主题"><option value="all">所有主题</option>__OPTIONS__</select>
<select id="meme" aria-label="筛选候选"><option value="all">全部表达</option><option>疑似玩梗</option><option>未命中规则</option></select>
<select id="sort" aria-label="排序"><option value="original">原始顺序</option><option value="helpful">有帮助票数</option><option value="funny">欢乐票数</option></select></div>
<p id="count" class="muted"></p><div id="reviews" class="reviews"></div><button id="more">再显示 30 条</button>
<h2>按评论年龄和长度分层</h2><p class="muted">同一年龄、长度范围内查看组间差异。分层较粗且可能样本很少；没有曝光量，不能计算投票率或推断因果。</p>
<div class="tablewrap">__STRATA__</div><h2>人工标注评估</h2><pre>__EVALUATION__</pre>
<footer>原项目：woctezuma/steam-reviews · MIT。本报告在本地生成，交互不需要联网。<br>复现信息见 run_metadata.json；分析参考时刻：__ASOF__。</footer>
<script id="review-data" type="application/json">__DATA__</script><script>
const rows=JSON.parse(document.getElementById('review-data').textContent);
const el=id=>document.getElementById(id);let limit=30;
function render(){let q=el('search').value.trim().toLowerCase();let list=rows.filter(r=>(el('topic').value==='all'||String(r.topic)===el('topic').value)&&(el('meme').value==='all'||r.candidate_label===el('meme').value)&&(!q||r.text.toLowerCase().includes(q)||r.review_id.includes(q)));
if(el('sort').value!=='original')list.sort((a,b)=>b[el('sort').value]-a[el('sort').value]);el('reviews').replaceChildren();el('count').textContent=`共 ${list.length} 条，显示 ${Math.min(limit,list.length)} 条`;
for(const r of list.slice(0,limit)){let card=document.createElement('article');card.className='review';let head=document.createElement('div');head.className='badge';head.textContent=`${r.topic_name} · ${r.candidate_label}${r.meme_types?' / '+r.meme_types:''}`;let text=document.createElement('div');text.className='text';text.textContent=r.text;let meta=document.createElement('div');meta.className='muted';meta.textContent=`#${r.review_id} | 有帮助 ${r.helpful} · 欢乐 ${r.funny} | ${r.age_band} · ${r.length_band} | 同文 ${r.same_text_count} 条`;card.append(head,text,meta);if(r.meme_evidence){let evidence=document.createElement('div');evidence.className='muted';evidence.textContent='命中理由：'+r.meme_evidence;card.append(evidence)}el('reviews').append(card)}el('more').hidden=limit>=list.length}
for(const id of ['search','topic','meme','sort'])el(id).addEventListener(id==='search'?'input':'change',()=>{limit=30;render()});el('more').addEventListener('click',()=>{limit+=30;render()});render();
</script></main></body></html>'''
    replacements = {"__PLOTLY__": get_plotlyjs(), "__NOTICE__": html.escape(notice), "__CARDS__": card_html,
                    "__PANELS__": "".join('<section class="panel">' + p + '</section>' for p in panels),
                    "__OPTIONS__": options, "__STRATA__": strata_html, "__EVALUATION__": evaluations,
                    "__ASOF__": html.escape(metadata["analysis_as_of"]), "__DATA__": payload}
    # 单次替换，避免外部文本中的占位符在后续替换中被解释。
    import re
    page = re.sub("|".join(re.escape(key) for key in replacements), lambda match: replacements[match.group()], page)
    path.write_text(page, encoding="utf-8")
