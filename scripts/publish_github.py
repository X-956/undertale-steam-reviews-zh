"""在用户自己的电脑上，用已登录的 GitHub CLI 建立真正的 fork 并发布。

不读取或打印令牌，不强制推送；仅发布已提交的 zh-cn 分支。
"""

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

UPSTREAM = "woctezuma/steam-reviews"


def run(args, cwd=None, check=True):
    result = subprocess.run(args, cwd=cwd, text=True, encoding="utf-8", errors="replace", capture_output=True)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "命令失败")
    return result


def verify_fork(info, target):
    if info.get("full_name", "").lower() != target.lower():
        raise RuntimeError("仓库名称与预期不一致，停止发布。")
    if not info.get("fork") or info.get("parent", {}).get("full_name") != UPSTREAM:
        raise RuntimeError("同名仓库不是指定上游的 fork，停止发布，未推送任何代码。")


def main():
    parser = argparse.ArgumentParser(description="发布 UNDERTALE 中文版 fork（使用本机 GitHub CLI 登录）")
    parser.add_argument("--owner", required=True, help="预期 GitHub 用户名，用于核验当前登录账号")
    parser.add_argument("--repo-name", default="undertale-steam-reviews-zh", help="新 fork 的仓库名")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9-]+", args.owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", args.repo_name):
        parser.error("用户名或仓库名格式不合法")
    for command in ("git", "gh"):
        if not shutil.which(command):
            parser.exit(1, f"请先安装 {command}。GitHub CLI：https://cli.github.com/\n")
    root = Path(__file__).resolve().parents[1]
    login = run(["gh", "api", "--hostname", "github.com", "user", "--jq", ".login"]).stdout.strip()
    if login.lower() != args.owner.lower():
        parser.exit(1, f"当前登录账号为 {login}，与 --owner 不一致；请先用 gh auth switch 切换。\n")
    target = f"{login}/{args.repo_name}"
    print(f"发布目标：https://github.com/{target}（公开 fork）", flush=True)
    source = root if (root / ".git").exists() else root / "repository.bundle"
    if not source.exists():
        parser.exit(1, "缺少 Git 仓库或 repository.bundle；请使用完整交付包。\n")
    if source == root and run(["git", "status", "--porcelain"], root).stdout.strip():
        parser.exit(1, "工作区存在未提交文件，请先检查并提交；脚本仅发布已提交版本。\n")
    workspace = Path(tempfile.mkdtemp(prefix="undertale-zh-publish-")) / "repo"
    run(["git", "clone", "--branch", "zh-cn", str(source), str(workspace)])
    print(f"发布工作目录：{workspace}", flush=True)
    current_sha = run(["git", "rev-parse", "HEAD"], workspace).stdout.strip()
    lookup = run(["gh", "api", "--hostname", "github.com", f"repos/{target}"], check=False)
    created = False
    if lookup.returncode:
        if "404" not in lookup.stderr:
            raise RuntimeError(lookup.stderr.strip())
        run(["gh", "repo", "fork", f"https://github.com/{UPSTREAM}", "--fork-name", args.repo_name,
             "--clone=false", "--remote=false"], workspace)
        created = True
        for _ in range(15):
            lookup = run(["gh", "api", "--hostname", "github.com", f"repos/{target}"], check=False)
            if lookup.returncode == 0:
                break
            time.sleep(2)
        else:
            raise RuntimeError("GitHub fork 尚未就绪；稍后重新运行脚本。")
    info = json.loads(lookup.stdout)
    verify_fork(info, target)
    run(["git", "remote", "rename", "origin", "source"], workspace)
    run(["git", "remote", "add", "origin", f"https://github.com/{target}.git"], workspace)
    # 仅本次命令借助 gh 获取凭据，不更改全局 Git 凭据配置。
    run(["git", "-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential",
         "push", "--set-upstream", "origin", "HEAD:refs/heads/zh-cn"], workspace)
    remote = json.loads(run(["gh", "api", "--hostname", "github.com",
                             f"repos/{target}/git/ref/heads/zh-cn"]).stdout)
    if remote["object"]["sha"] != current_sha:
        raise RuntimeError("远端提交核验不一致，请检查仓库。")
    if created:
        run(["gh", "api", "--hostname", "github.com", "--method", "PATCH", f"repos/{target}",
             "-f", "default_branch=zh-cn", "-f",
             "description=UNDERTALE 中文 Steam 评论：采集、主题聚类、玩梗候选及互动分析"])
    print(f"发布成功：https://github.com/{target}/tree/zh-cn\n提交：{current_sha}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, ValueError) as error:
        raise SystemExit(f"发布未完成：{error}")
