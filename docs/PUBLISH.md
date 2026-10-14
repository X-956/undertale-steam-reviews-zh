# 发布到自己的 GitHub

此脚本使用本机 GitHub CLI，不需要 ChatGPT 插件。需要已经安装 Git、Python 3.10+ 和 [GitHub CLI](https://cli.github.com/)。

在项目根目录运行：

```powershell
gh auth login --hostname github.com --web --git-protocol https
python scripts/publish_github.py --owner X-956
```

`--owner` 必须与实际登录用户名相同。不要向聊天窗口发送令牌。

脚本会：

1. 核验登录账号，只使用已提交的 `zh-cn` 分支。
2. 在临时目录复制 Git 仓库；下载包没有 `.git` 时从 `repository.bundle` 恢复完整历史。
3. 为 `woctezuma/steam-reviews` 建立公开 fork，默认名称 `undertale-steam-reviews-zh`。
4. 验证同名仓库确实是对应上游的 fork，再以普通推送发布 `zh-cn`，不强制覆盖远端。
5. 核验远端提交；新建的 fork 将 `zh-cn` 设为默认分支。已有 fork 不改默认分支。

完成后终端会输出真实仓库链接与提交编号。若已在同一 fork 网络中存在其他名称的 fork，先使用 `--repo-name` 指定已有名称；脚本不会自动重命名已有仓库。

Windows 安装 GitHub CLI 可用 `winget install --id GitHub.cli`，安装后重新打开终端。分析功能无需安装 GitHub CLI。

## 手动方式

若希望自己控制每一步，先在 GitHub 上 fork 上游，然后在包含 `.git` 的本地工作副本中执行：

```powershell
git remote add my-fork https://github.com/你的用户名/你的仓库名.git
git push my-fork zh-cn
```

交付包若只有 `repository.bundle`，先执行 `git clone -b zh-cn repository.bundle publish-copy`，再进入 `publish-copy` 操作。不要直接将全部工作目录上传：`data/` 和 `outputs/` 包含采集数据与本地报告，不应混入源码提交。

参考：[GitHub CLI fork 文档](https://cli.github.com/manual/gh_repo_fork)。
