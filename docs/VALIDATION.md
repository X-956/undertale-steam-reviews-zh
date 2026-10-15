# 本次验证记录

初始验证：2026-10-14；发布与兼容性复核：2026-10-15。本地环境：Linux、Python 3.12.14。

| 检查 | 结果 |
|---|---|
| 安装 `pip install -e .` | 成功 |
| `unittest discover -s tests_zh -v` | 8 项测试，包含 Windows CP1252 输出回归场景 |
| 合成数据离线 demo | 30 条记录，完整生成 CSV、JSON、HTML |
| 真实 Steam 接口 | 成功连续分页采集 200 条 UNDERTALE 简体中文评论 |
| 真实评论分析 | 成功生成统计、8 个主题、玩梗候选、分层统计和 HTML |
| 单条数字短评 | 完整分析可运行，标为未聚类 |
| 本地 Chromium 检查 | 5 张图表正常生成；搜索、候选筛选、排序、加载更多可用；无脚本错误 |
| 人工标注 | 尚未完成，不报告真实分类准确率 |
| GitHub 远端发布 | 已 fork 至 [X-956/undertale-steam-reviews-zh](https://github.com/X-956/undertale-steam-reviews-zh)，默认分支 `zh-cn` |
| 远端 CI | Windows / Ubuntu × Python 3.10 / 3.12；各次结果见 [Actions](https://github.com/X-956/undertale-steam-reviews-zh/actions) |
| Windows 编码兼容 | 首轮 CI 发现 CP1252 终端不能输出中文；日志和命令行改为对无法编码的字符转义，不影响 UTF-8 数据文件 |

8 项测试覆盖：非 UTF-8 输出下的采集与离线演示、游标重复、分页续采与编号去重、末尾写入中断恢复、CSV 公式转义、短文本/小样本、HTML 外部文本转义、标注表保护，以及普通短评/中文诉求不自动视为玩梗。

真实数据采集口径为 `appid=391540`、`languages=[schinese]`、`filter=1`、`review_type=0`、`purchase_type=1`、`filter_offtopic_activity=false`。200 条是接口和流程验证样本，未采到末页，不能当作完整评论总体。原始评论、作者信息和真实报告未加入源码提交；交付演示报告仅使用合成文本。

本次直接依赖版本见 `requirements-zh-tested.txt`，每次运行也会写入 `run_metadata.json`。测试通过只说明这些场景下的实现行为正确，不证明玩梗规则或聚类已经达到研究所需的效果。
