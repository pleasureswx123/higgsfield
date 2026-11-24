"""切换应用版本，保留服务器的环境配置、数据库卷与 NAS 项目目录。"""

import fcntl
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading

BASE = Path(sys.argv[1])
if BASE not in (Path("/opt/higgsfield"), Path("/opt/higgsfield-drill")):
    raise ValueError("无效的部署环境")
INBOX = Path(sys.argv[2]).resolve()
if INBOX.parent != BASE / "incoming" or not re.fullmatch("[0-9a-f]{32}", INBOX.name):
    raise ValueError("无效的发布目录")
LIVE = (BASE / "current").resolve(strict=True)
if LIVE.parent != BASE / "releases":
    raise ValueError("当前版本目录不在 releases 中")
DRILL = BASE.name.endswith("-drill")
PROJECT = "higgsfield-drill" if DRILL else "higgsfield-prod"
VERSIONS = BASE / "versions"
STATE = BASE / "release-state.json"
PENDING = BASE / "release-pending.json"
APPS = ("studio", "admin")
CONFIG = ("compose.yaml", "nginx.conf", "backup.sh", ".env")
MOUNT = "/mnt/higgsfield/NightmareTheatre/prod"


def run(*cmd, cwd=LIVE, capture=False, **kwargs):
    result = subprocess.run(
        list(map(str, cmd)), cwd=cwd, check=True, stdout=subprocess.PIPE if capture else None, **kwargs
    )
    return result.stdout.decode().strip() if capture else None


def compose(*cmd, cwd=LIVE, **kwargs):
    return run(
        "docker",
        "compose",
        "-p",
        PROJECT,
        "--env-file",
        cwd / ".env",
        "-f",
        cwd / "compose.yaml",
        *cmd,
        cwd=cwd,
        **kwargs,
    )


def write_json(path, data):
    tmp = path.with_suffix(".new")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf8")
    os.replace(tmp, path)


def read(path):
    return json.loads(path.read_text())


def config(path):
    return json.loads(compose("config", "--no-env-resolution", "--format", "json", cwd=path, capture=True))


def sql(query):
    return compose(
        "exec",
        "-T",
        "postgres",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-At",
        "-U",
        "higgsfield",
        "-d",
        "higgsfield_prod",
        "-c",
        query,
        capture=True,
    )


def revision():
    return sql("select version_num from alembic_version")


def manifest(name):
    return read(VERSIONS / name / "version.json")


def state():
    return read(STATE) if STATE.exists() else {"current": "baseline", "previous": None}


def sha(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def seal(target):
    files = [target / name for name in ("compose.yaml", "nginx.conf", "backup.sh")]
    for app in APPS:
        files.extend(p for p in (target / app).rglob("*") if p.is_file())
    with (target / "release-files.sha256").open("w") as out:
        for file in sorted(files):
            print(sha(file), file.relative_to(target), sep="  ", file=out)


def atomic_copy(src, dst):
    tmp = dst.with_name("." + dst.name + ".release-next")
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def baseline():
    if STATE.exists():
        return
    if not (VERSIONS / "baseline").exists():
        with tempfile.TemporaryDirectory(dir=VERSIONS) as work:
            snapshot = Path(work) / "baseline"
            snapshot.mkdir()
            for name in APPS:
                shutil.copytree(LIVE / name, snapshot / name)
            for name in CONFIG:
                shutil.copy2(LIVE / name, snapshot / name)
            image = config(LIVE)["services"]["api"]["image"]
            live_id = run("docker", "inspect", "-f", "{{.Image}}", PROJECT + "-api-1", capture=True)
            if live_id != run("docker", "image", "inspect", "-f", "{{.Id}}", image, capture=True):
                raise ValueError("运行中的后端与 Compose 镜像不同，无法记录回退基线")
            write_json(
                snapshot / "version.json",
                {
                    "keys": {},
                    "schema": revision(),
                    "image": image,
                    "image_id": run("docker", "image", "inspect", "-f", "{{.Id}}", image, capture=True),
                },
            )
            seal(snapshot)
            snapshot.rename(VERSIONS / "baseline")
    write_json(STATE, state())


def render_compose(source):
    text = source.read_text()
    if not DRILL:
        return text
    # 演练使用独立网络、数据目录、凭据及环回端口，服务名仍与正式环境相同。
    nas = drill_nas()
    return (
        text.replace("higgsfield-prod", "higgsfield-drill")
        .replace("/etc/higgsfield/", str(BASE / "etc") + "/")
        .replace("/mnt/data/higgsfield", str(BASE / "data"))
        .replace(MOUNT, str(nas))
        .replace("192.168.1.100:80:80", "127.0.0.1:18080:80")
        .replace("192.168.1.100:8080:8080", "127.0.0.1:18081:8080")
        + "\nnetworks:\n  default:\n    internal: true\n"
    )


def drill_nas():
    volumes = config(LIVE)["services"]["api"]["volumes"]
    nas = Path(next(v["source"] for v in volumes if v["target"] == "/nas/prod")).resolve()
    if (
        nas.parent.parent != Path(MOUNT) / ".platform"
        or nas.name != "prod"
        or not nas.parent.name.startswith("drill-release-")
    ):
        raise ValueError("演练 NAS 必须位于独立的受限子目录")
    return nas


def image_build(src, image):
    # 解包目录继承发布进程的私有权限，镜像内的应用以普通用户运行。
    for item in [src, *src.rglob("*")]:
        if not item.is_symlink():
            item.chmod(0o755 if item.is_dir() or item.stat().st_mode & 0o100 else 0o644)
    args = ["docker", "build", "-f", "Dockerfile.prod", "-t", image]
    # 复用服务器已有的首发依赖包；依赖变化后使用 Dockerfile 的常规安装路径。
    wheels = Path("/opt/higgsfield/releases/20261124-1/wheels")
    original = wheels.parent / "build"
    shutil.copy2(src / "Dockerfile.prod.dockerignore", src / ".dockerignore")
    if wheels.is_dir() and all(
        (src / n).read_bytes().splitlines() == (original / n).read_bytes().splitlines()
        for n in ("requirements-pg.txt", "pyproject.toml")
    ):
        with ThreadingHTTPServer(
            ("127.0.0.1", 49181), partial(SimpleHTTPRequestHandler, directory=str(wheels))
        ) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                run(
                    *args,
                    "--network=host",
                    "--build-arg",
                    "PIP_FIND_LINKS=http://127.0.0.1:49181/",
                    "--build-arg",
                    "PIP_NO_INDEX=1",
                    ".",
                    cwd=src,
                )
                return
            except subprocess.CalledProcessError:
                print("离线依赖未命中，使用常规构建", flush=True)
            finally:
                server.shutdown()
    run(*args, ".", cwd=src)


def prepare(request, old):
    name = request["commit"]
    if not re.fullmatch("[0-9a-f]{40}", name):
        raise ValueError("提交号无效")
    if (VERSIONS / name).exists():
        return name
    for file, digest in request["hashes"].items():
        if file not in ("source.tar", "studio.tgz", "admin.tgz") or sha(INBOX / file) != digest:
            raise ValueError("发布包校验失败")
    src = INBOX / "src"
    with tarfile.open(INBOX / "source.tar") as tar:
        tar.extractall(src, filter="data")
    settings = src / "deploy/intranet"
    prior = manifest(old)
    with tempfile.TemporaryDirectory(dir=VERSIONS) as work:
        target = Path(work) / name
        target.mkdir()
        for app in APPS:
            if (INBOX / (app + ".tgz")).exists():
                with tarfile.open(INBOX / (app + ".tgz")) as tar:
                    tar.extractall(target / app, filter="data")
                for item in (target / app).rglob("*"):
                    item.chmod(0o755 if item.is_dir() else 0o644)
                (target / app).chmod(0o755)
            elif request["keys"][app] == prior["keys"].get(app):
                shutil.copytree(VERSIONS / old / app, target / app, copy_function=os.link)
            else:
                raise ValueError("缺少前端包 " + app)
            if not (target / app / "index.html").is_file():
                raise ValueError("缺少前端入口")
        image = prior["image"]
        if request["keys"]["backend"] != prior["keys"].get("backend"):
            image = PROJECT + "-release:" + name
            image_build(src / "ruoyi-fastapi-backend", image)
        (target / ".env").write_text("HF_IMAGE=" + image + "\n")
        (target / "compose.yaml").write_text(render_compose(settings / "compose.yaml"))
        for file in ("backup.sh", "nginx.conf"):
            shutil.copy2(settings / file, target / file)
        # 宿主机单元的变更须单独维护；常规发布不可静默跳过或改写挂载与自启设置。
        for file in (
            "higgsfield.service",
            "mnt-higgsfield.mount",
            "higgsfield-backup.service",
            "higgsfield-backup.timer",
        ):
            if (settings / file).read_text().strip() != Path("/etc/systemd/system", file).read_text().strip():
                raise ValueError(file + " 与已安装版本不同，请先安排宿主机配置更新")
        services = config(target)["services"]
        existing = config(LIVE)["services"]
        for dep in ("postgres", "redis"):
            if services[dep] != existing[dep]:
                raise ValueError(dep + " 的基础设施配置变化，需要单独维护")
        expected_nas = str(drill_nas()) if DRILL else MOUNT
        for service, cfg in services.items():
            if service == "api" or service.startswith("worker-"):
                mounts = {v["target"]: v.get("source") for v in cfg.get("volumes", [])}
                if mounts.get("/nas/prod") != expected_nas or cfg.get("env_file") != existing["api"].get(
                    "env_file"
                ):
                    raise ValueError(service + " 的存储或环境文件与当前部署不匹配")
            elif service not in ("postgres", "redis", "web"):
                raise ValueError("新增基础服务需要单独验证：" + service)
        compose("run", "--no-deps", "--rm", "-T", "--entrypoint", "nginx", "web", "-t", cwd=target)
        heads = run(
            "docker", "run", "--rm", "--network", "none", "--entrypoint", "alembic", image, "heads", capture=True
        )
        match = re.fullmatch(r"([A-Za-z0-9_]+) \(head\)", heads)
        if not match:
            raise ValueError("目标镜像必须只有一个可识别的 Alembic head")
        compat = settings / "compatible-migrations.json"
        write_json(
            target / "version.json",
            {
                "keys": request["keys"],
                "schema": match[1],
                "image": image,
                "image_id": run("docker", "image", "inspect", "-f", "{{.Id}}", image, capture=True),
                "compatibility": read(compat) if compat.exists() else [],
            },
        )
        seal(target)
        target.rename(VERSIONS / name)
    return name


def frontend(app, target):
    src = target / app
    dest = LIVE / app
    # 页面入口最后切换；保留旧的带哈希资源供仍然打开的旧页面继续使用。
    run("rsync", "-a", "--checksum", "--delay-updates", "--exclude=/index.html", str(src) + "/", str(dest) + "/")
    atomic_copy(src / "index.html", dest / "index.html")


def verify(target):
    compose("up", "-d", "--no-recreate", "--wait", "--wait-timeout", "180")
    expected = read(target / "version.json")["image_id"]
    app_services = ["api", *workers(target)]
    container_ids = compose("ps", "-q", *app_services, capture=True).splitlines()
    if len(container_ids) != len(app_services) or any(
        image != expected
        for image in run("docker", "inspect", "-f", "{{.Image}}", *container_ids, capture=True).splitlines()
    ):
        raise RuntimeError("后端或工作器正在运行其他镜像")
    for app, port in [("studio", 80), ("admin", 8080)]:
        page = subprocess.check_output(
            ["docker", "exec", PROJECT + "-web-1", "wget", "-qO-", f"http://127.0.0.1:{port}/index.html"]
        )
        if hashlib.sha256(page).hexdigest() != sha(target / app / "index.html"):
            raise RuntimeError(app + " 页面与发布包不一致")
    compose(
        "exec", "-T", "web", "wget", "-qO", "/dev/null", "http://127.0.0.1/dev-api/transport/crypto/frontend-config"
    )


def workers(target):
    return [s for s in config(target)["services"] if s.startswith("worker-")]


def busy():
    return sql("select count(*) from hf_creation_job where finished_time is null") != "0"


def backup():
    if DRILL:
        with (BASE / "before-migration.dump").open("wb") as dump:
            run(
                "docker",
                "exec",
                PROJECT + "-postgres-1",
                "pg_dump",
                "-U",
                "higgsfield",
                "-Fc",
                "higgsfield_prod",
                stdout=dump,
            )
    else:
        run("systemctl", "start", "higgsfield-backup.service")


def install(old, new, *, rollback=False, recovery=False):
    before, after = VERSIONS / old, VERSIONS / new
    a, b = manifest(old), manifest(new)
    run("sha256sum", "--quiet", "-c", after / "release-files.sha256", cwd=after)
    if run("docker", "image", "inspect", "-f", "{{.Id}}", b["image"], capture=True) != b["image_id"]:
        raise RuntimeError("目标镜像标签内容已改变")
    db = revision()
    migrate = False
    if db != b["schema"]:
        if rollback:
            if [b["schema"], db] not in a.get("compatibility", []):
                raise RuntimeError("数据库版本与回退目标不兼容")
        elif db == a["schema"] and [db, b["schema"]] in b.get("compatibility", []):
            migrate = True
        else:
            raise RuntimeError("数据库版本变化需要已验证的向后兼容迁移声明")
    changed_cfg = sha(before / "compose.yaml") != sha(after / "compose.yaml")
    backend = changed_cfg or a["image_id"] != b["image_id"] or migrate
    if backend and not recovery and busy():
        raise RuntimeError("仍有在途生成任务；请在任务完成后重新发布")
    if migrate:
        backup()
    if not recovery:
        write_json(PENDING, {"old": old, "new": new})
    if backend:
        compose("stop", "web", "api")
        if not recovery and busy():
            compose("up", "-d", "--no-deps", "--wait", "api", "web")
            PENDING.unlink()
            raise RuntimeError("切换前有新任务提交，恢复原版")
        old_workers = workers(before)
        if old_workers:
            compose("stop", *old_workers)
    for f in CONFIG:
        atomic_copy(after / f, LIVE / f)
    if migrate:
        compose("run", "--no-deps", "--rm", "-T", "api", "alembic", "upgrade", "head")
        if revision() != b["schema"]:
            raise RuntimeError("数据库迁移未到目标版本")
    for app in APPS:
        if recovery or a["keys"].get(app) != b["keys"].get(app) or not a["keys"] or not b["keys"]:
            frontend(app, after)
    if backend:
        # 删除旧版本专有的工作器；只处理已停机的应用容器，不处理卷。
        removed = set(workers(before)) - set(workers(after))
        for service in removed:
            container = PROJECT + "-" + service + "-1"
            if run("docker", "ps", "-aq", "--filter", "name=^/" + re.escape(container) + "$", capture=True):
                run("docker", "rm", container)
        compose("up", "-d", "--no-deps", "--wait", "--wait-timeout", "240", "api", *workers(after))
    if backend or sha(before / "nginx.conf") != sha(after / "nginx.conf"):
        compose("up", "-d", "--no-deps", "--force-recreate", "--wait", "--wait-timeout", "90", "web")
    verify(after)
    run("sha256sum", "--quiet", "-c", after / "release-files.sha256", cwd=LIVE)
    atomic_copy(after / "release-files.sha256", LIVE / "release-files.sha256")
    (LIVE / "release-image.sha256").write_text(b["image_id"] + "\n")


def main(action):
    if action == "plan":
        current = state()["current"]
        requested = sys.argv[4] if len(sys.argv) > 4 else ""
        cached = bool(re.fullmatch("[0-9a-f]{40}", requested) and (VERSIONS / requested / "version.json").is_file())
        print(
            json.dumps(
                {"current": current, "cached": cached, "keys": manifest(current)["keys"] if STATE.exists() else {}}
            )
        )
        return
    if action not in ("publish", "rollback"):
        raise ValueError("未知操作")
    os.umask(0o077)
    (INBOX / "started").touch()
    VERSIONS.mkdir(mode=0o700, exist_ok=True)
    with (BASE / "release.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for path in ("/mnt/data", "/mnt/higgsfield"):
            run("mountpoint", "-q", path)
        baseline()
        if PENDING.exists():
            pending = read(PENDING)
            if state()["current"] == pending["old"]:
                install(pending["new"], pending["old"], rollback=True, recovery=True)
            PENDING.unlink()
        prior = state()
        old = prior["current"]
        request = read(INBOX / "request.json")
        if old != request["expected"]:
            raise RuntimeError("准备期间已有其他发布，请重新运行")
        new = prepare(request, old) if action == "publish" else prior["previous"]
        if not new:
            raise RuntimeError("尚无上一个成功版本")
        if old == new:
            verify(VERSIONS / old)
            print("该版本已在运行，健康检查通过")
            return
        try:
            install(old, new, rollback=action == "rollback")
        except Exception:
            if PENDING.exists():
                print("切换失败，正在恢复原版", flush=True)
                install(new, old, rollback=True, recovery=True)
                PENDING.unlink()
                print("原版已恢复，健康检查通过：", old, flush=True)
            raise
        history = prior.get("history", [prior["previous"]] if prior["previous"] else [])
        history = history + [old] if action == "publish" else history[:-1]
        previous = history[-1] if history else None
        write_json(STATE, {"current": new, "previous": previous, "history": history})
        PENDING.unlink()
        print("当前版本", new, "；上一版", previous or "无", flush=True)


if __name__ == "__main__":
    try:
        main(sys.argv[3])
    finally:
        if sys.argv[3] in ("publish", "rollback"):
            shutil.rmtree(INBOX)
