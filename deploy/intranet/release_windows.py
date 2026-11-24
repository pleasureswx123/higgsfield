"""从 Windows 将远端 main 的指定提交发布至内网服务器，或切回上一版。"""

import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HOST = "root@192.168.1.100"
FRONTS = {"studio": ("higgsfield-frontend", "build"), "admin": ("ruoyi-fastapi-frontend/vue3/web", "build:prod")}


def run(*args, cwd=ROOT, capture=False, env=None):
    result = subprocess.run(
        list(map(str, args)), cwd=cwd, env=env, check=True, stdout=subprocess.PIPE if capture else None
    )
    return result.stdout.decode("utf-8").strip() if capture else None


def ssh(command, capture=False):
    return run("ssh", "-o", "BatchMode=yes", HOST, command, capture=capture)


def switch(remote, action, unit):
    print("服务器发布任务 " + unit, flush=True)
    try:
        ssh(f"systemd-run --wait --collect --unit={unit} {remote} {action}")
    finally:
        ssh(f"journalctl -u {unit} --no-pager -o cat -n 20")


def archive(commit, paths, dest):
    # git archive 只读取提交对象，不会带入工作区环境文件或未提交修改。
    run("git", "archive", "--format=tar", "-o", dest, commit, "--", *paths)


def package_ui(name, source, bundle):
    folder, script = FRONTS[name]
    pnpm = shutil.which("pnpm.cmd") or shutil.which("pnpm")
    if not pnpm:
        raise RuntimeError("请在开发电脑安装项目所需的 pnpm")
    work = source / folder
    # 只让目标提交的 Vite 配置进入前端包，避免开发终端中的地址覆盖正式配置。
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("VITE_") and k.upper() != "NODE_ENV"}
    run(pnpm, "install", "--frozen-lockfile", "--prefer-offline", cwd=work, env=env)
    run(pnpm, "run", script, cwd=work, env=env)
    with tarfile.open(bundle, "w:gz", compresslevel=2) as tar:
        for item in (work / "dist").iterdir():
            tar.add(item, arcname=item.name)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=["publish", "rollback"])
    ap.add_argument("version", nargs="?")
    ap.add_argument("--drill", action="store_true", help="使用隔离演练项目")
    args = ap.parse_args()
    base = "/opt/higgsfield-drill" if args.drill else "/opt/higgsfield"
    if args.action == "publish":
        version = args.version or input("请输入 main 的提交号（或 main）: ").strip()
        if version != "main" and not re.fullmatch("[0-9a-fA-F]{7,40}", version):
            raise ValueError("版本必须为提交号或 main")
        run("git", "fetch", "origin", "+refs/heads/main:refs/remotes/origin/main")
        commit = run(
            "git",
            "rev-parse",
            "--verify",
            ("origin/main" if version == "main" else version) + "^{commit}",
            capture=True,
        )
        run("git", "merge-base", "--is-ancestor", commit, "origin/main")
    elif args.version:
        raise ValueError("回退自动选取上一成功版本，无需指定提交号")

    upload = base + "/incoming/" + uuid.uuid4().hex
    ssh(f"umask 077 && mkdir -p {upload}")
    dispatched = False
    try:
        run("scp", "-q", HERE / "release_server.py", HOST + ":" + upload + "/release_server.py")
        remote = f"/usr/bin/python3 {upload}/release_server.py {base} {upload}"
        plan = json.loads(ssh(remote + " plan" + (" " + commit if args.action == "publish" else ""), capture=True))
        # 与项目同盘，pnpm 能复用开发电脑已有的内容缓存并创建硬链接。
        scratch = ROOT / "output"
        scratch.mkdir(exist_ok=True)
        with (
            concurrent.futures.ThreadPoolExecutor(1) as runner,
            tempfile.TemporaryDirectory(prefix="hf-rel-", dir=scratch) as tmp,
        ):
            temp = Path(tmp)
            meta = {"expected": plan["current"]}
            if args.action == "publish":
                meta["commit"] = commit
            if args.action == "publish" and not plan["cached"]:
                paths = [
                    "deploy/intranet",
                    "ruoyi-fastapi-backend",
                    *[v[0] for v in FRONTS.values()],
                    "shared/browser",
                ]
                trees = {p: run("git", "rev-parse", f"{commit}:{p}", capture=True) for p in paths}
                meta.update(
                    commit=commit, keys={k: trees[v[0]] + "-" + trees["shared/browser"] for k, v in FRONTS.items()}
                )
                meta["keys"]["backend"] = trees["ruoyi-fastapi-backend"]
                need = [n for n in FRONTS if meta["keys"][n] != plan["keys"].get(n)]
                ui_source = temp / "ui"
                if need:
                    archive(commit, [FRONTS[n][0] for n in need] + ["shared/browser"], temp / "ui.tar")
                    with tarfile.open(temp / "ui.tar") as tar:
                        tar.extractall(ui_source, filter="data")
                    with concurrent.futures.ThreadPoolExecutor(2) as pool:
                        list(pool.map(lambda n: package_ui(n, ui_source, temp / (n + ".tgz")), need))
                src = ["deploy/intranet"]
                if meta["keys"]["backend"] != plan["keys"].get("backend"):
                    src.append("ruoyi-fastapi-backend")
                archive(commit, src, temp / "source.tar")
                files = [temp / "source.tar", *[temp / (n + ".tgz") for n in need]]
                meta["hashes"] = {}
                for file in files:
                    with file.open("rb") as stream:
                        meta["hashes"][file.name] = hashlib.file_digest(stream, "sha256").hexdigest()
                run("scp", "-q", *files, HOST + ":" + upload + "/")
            (temp / "request.json").write_text(json.dumps(meta), encoding="utf-8")
            run("scp", "-q", temp / "request.json", HOST + ":" + upload + "/")
            # 上传完即可切换，本机同时清理前端构建目录。
            unit = "hf-release-" + upload.rsplit("/", 1)[1]
            job = runner.submit(switch, remote, args.action, unit)
            dispatched = True
        job.result()
    finally:
        # 切换进程可能仍在读取上传目录；由服务器负责切换阶段的清理。
        if not dispatched:
            ssh(f"rm -rf -- {upload}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as e:
        sys.exit("发布工具退出：" + str(e))
