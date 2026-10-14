# UNDERTALE 中文 Steam 评论分析

基于 [woctezuma/steam-reviews](https://github.com/woctezuma/steam-reviews) 的中文扩展，聚焦《UNDERTALE》玩家评价、社区表达及“有帮助 / 欢乐”互动。保留上游 Git 历史、MIT 许可证与[原英文说明](README.upstream.md)。

> 当前是可运行的研究基线。玩梗检测输出规则候选，尚未建立人工标注测试集；离线 demo 使用合成数据，不代表研究结果。

## 功能

| 环节 | 本版本实现 |
|---|---|
| 数据采集 | Steam 官方接口，默认 UNDERTALE / 简体中文，分页、重试、续采、采集元数据 |
| 预处理 | 原文保留、编号去重、中文分词、角色别名、停用词及同文频次 |
| 主题挖掘 | TF-IDF + K-means，关键词、代表评论与二维主题投影 |
| 玩梗分析 | 文本规则、命中理由、独立多标签、盲标注表及人工标签评估 |
| 互动分析 | 各组投票均值 / 中位数 / 零票比例，评论年龄与长度分层 |
| 可视化 | 可离线打开的 HTML：搜索、主题筛选、候选筛选、投票排序 |

## 快速运行（Windows PowerShell）

需要 Python 3.10+。在项目根目录执行，无需激活虚拟环境：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m steam_reviews_zh demo
```

用浏览器打开 `outputs/demo/report.html`。首次安装依赖需要联网，生成后的 HTML 自带图表脚本，可离线查看。

Linux / macOS：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m steam_reviews_zh demo
```

以下命令中的 `python` 请换成自己的虚拟环境解释器，或先激活环境。

## 采集真实评论

```bash
# 默认按最新顺序取 1,000 条简体中文评论
python -m steam_reviews_zh fetch --output data/undertale-zh.jsonl

# 中断后继续；--max-reviews 是累计条数，不是追加条数
python -m steam_reviews_zh fetch --output data/undertale-zh.jsonl --resume --max-reviews 3000

# 需要完整历史时，采到空页为止
python -m steam_reviews_zh fetch --output data/undertale-zh.jsonl --resume --max-reviews 0
```

AppID 默认 `391540`，语言默认 `schinese`。公开接口不需要 API key。采集器保留原始文本及评论编号，默认不保存作者 SteamID；不会覆盖已有数据文件。

数据旁的 `.meta.json` 保存参数、抓取时间、游标、条数和结束原因。`complete=false` 表示尚不能视为完整采集。语言标签不保证正文一定是中文；同文不同编号的评论会保留。

## 分析与人工标注

```bash
python -m steam_reviews_zh analyze --input data/undertale-zh.jsonl --output outputs/undertale --clusters 8

# 在 annotation_blind.csv 中填 label，保存后重新分析
python -m steam_reviews_zh analyze --input data/undertale-zh.jsonl --output outputs/undertale --labels outputs/undertale/annotation_blind.csv
```

| 输出文件 | 用途 |
|---|---|
| `report.html` | 离线交互报告 |
| `reviews.csv` | 原文、文本特征、主题与玩梗候选 |
| `interactions.csv` | 主题 × 候选组的投票统计 |
| `age_length_strata.csv` | 评论年龄 × 长度 × 候选组的投票统计 |
| `annotation_blind.csv` | 无投票、无预测提示的人工标注表；重跑不覆盖 |
| `summary.json` | 主题关键词、代表评论、聚类诊断与人工标签评估 |
| `run_metadata.json` | 输入哈希、参数、采集口径与依赖版本 |

人工标签填写 `meme`、`non_meme` 或 `uncertain`。同文按哈希放入同一 dev/test 组；只用 dev 修改规则，冻结后在 test 评估。未提供人工标签时不会生成虚构准确率。

CSV 使用 UTF-8 BOM，方便 Windows Excel；可能被解释为公式的文本会加单引号，原始 JSONL 不改写。更多口径见[方法与标注说明](docs/METHODS.md)。

## 项目结构

- `steam_reviews_zh/`：新版中文采集、处理、聚类、规则分析及报告。
- `steam_reviews_zh/assets/`：可修改的停用词、UNDERTALE 词典与玩梗规则。
- `tests_zh/`：离线自动测试，无须 Steam 网络或 GitHub 账号。
- `docs/`：方法、标注、发布与验证说明。
- 根目录原有 Python 脚本：上游旧版，保留作参考；使用独立的 `requirements.txt`，不要与新版混装。

```bash
python -m unittest discover -s tests_zh -v
```

新版工作流覆盖 Windows / Ubuntu、Python 3.10 / 3.12；原上游网络测试改为手动触发。CI 配置存在不等于已在远端执行成功。

## 与原项目的关系

上游提供了 Steam 评论分析、聚类、玩笑评论识别等思路。其玩笑检测使用英文 TextBlob 特征，原聚类也不等同于中文文本主题聚类。本版本新增独立中文流程，保留旧脚本及英文说明，不声称原作者实现了这些新增功能。

源码沿用 [MIT 许可证](LICENSE)，原作者版权声明保持不变。采集的评论文本及游戏名称不因源码许可证而改变其各自权利归属。本项目未使用游戏图像或音乐资源。

## 发布

用本机 GitHub CLI 创建真正的 fork 并发布，见[发布说明](docs/PUBLISH.md)。源码中不包含个人令牌。`data/`、`outputs/` 和虚拟环境已忽略，不会随正常 Git 提交上传。

## 解读边界

- 短评、重复评论、欢乐票多不自动等于玩梗；中文诉求独立记录。
- 主题与玩梗标签可以重叠；主题关键词需要人工审阅命名。
- 最近 N 条与投票排名前 N 条都不是随机样本。前者偏近期，后者还按结果变量筛选。
- 票数是累计互动，没有曝光分母；年龄和长度分层也不能支持因果结论。

数据接口：[Steamworks IUserReviewsService](https://partner.steamgames.com/doc/webapi/IUserReviewsService?l=english)。
