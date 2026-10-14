# -*- coding: utf-8 -*-
"""DSA 定制版 · 整盘迁移打包器（不保留历史）

用法（在部署机上）：
    python3 tools/make_migration_package.py                       # 默认小版本 +1
    python3 tools/make_migration_package.py --bump minor          # 中等变动
    python3 tools/make_migration_package.py --bump major          # 大版本变动
    python3 tools/make_migration_package.py --note "本次改动摘要"  # 同时写入 CHANGELOG
    python3 tools/make_migration_package.py --with-source         # 同时生成源码增量包

版本号规则（MAJOR.MINOR.PATCH，即 大版本.中等变动.小版本）：
    右数第一位 PATCH：小改动（改文案、修 bug、微调参数）→ 默认
    右数第二位 MINOR：中等改动（新增功能、改交互、加配置项）
    右数第三位 MAJOR：大改动（换架构、换渲染引擎、破坏性变更）
升级时高位 +1，其右侧低位全部归零。

产物（默认输出到 /opt/dsa-dist，开发产物按项目分文件夹放这里）：
    dsa-migration-v<版本>.tar.gz      ← 唯一交付物（2026-10-11 用户定）
      ├── app/                 定制版源码与配置（不含 data/logs/reports/share 历史）
      ├── update.sh            一键增量更新（备份→覆盖→load 镜像→重启，自动识别布局）
      ├── dsa-local-img.tar.gz 预构建镜像（docker save | gzip）
      └── 安装说明.txt

废弃产物（--with-source，默认不生成）：
    dsa-source-v<版本>.tar.gz         ← 2026-10-11 起不再交付；update.sh 已并入迁移包，
      源码增量升级直接用迁移包里的 update.sh 即可（它会跳过 .env 与历史数据）。
"""
from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# 部署根目录：默认 /opt/daily-stock-analysis，可用环境变量 DSA_DEPLOY_DIR 覆盖
DEFAULT_BASE = os.environ.get("DSA_DEPLOY_DIR", "/opt/daily-stock-analysis")
DEFAULT_IMAGE = "daily-stock-analysis-local:latest"
# 开发产物统一输出目录（用户约定 2026-10-10）：所有开发包都按项目分文件夹放这里
#   项目文件夹 = DEFAULT_OUT/<项目名>，本项目为 daily-stock-analysis
# 打包产物输出目录：默认 /opt/dsa-dist，可用环境变量 DSA_DIST_DIR 覆盖
DEFAULT_OUT = os.environ.get("DSA_DIST_DIR", "/opt/dsa-dist")

# 注意：项目已扁平化，下面用「裸名」匹配（tar 以项目根为 context 打包），
#       --exclude 会匹配任意层级；裸名不会误伤（如 data 只排除数据目录本身）
EXCLUDES = [
    "data",
    "logs",
    "reports",
    "share_images",
    "share",
    "longbridge_tokens",
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.bak-*",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".git",
    ".claude",
    "*.log",
]

# 源码增量包的额外排除项（不随源码泄露 .env 密钥）
SRC_EXCLUDES = EXCLUDES + [".env"]

# 源码增量更新脚本模板；__DSA_VERSION__ 在打包时替换为真实版本号
UPDATE_SH_TEMPLATE = """#!/bin/sh
# ============================================================
# DSA 增量更新 → v__DSA_VERSION__
#
# 用法：把本包解压到任意目录，然后
#     sudo sh update.sh <部署根目录>
# 例：sudo sh update.sh /opt/daily-stock-analysis
#
# 脚本会：备份现有代码 → 覆盖源码（保留 .env / data / 分享图 / 历史）
#        → 载入镜像（包内自带则离线 load，否则联网 build）→ 重启容器
#
# 部署布局自动识别：
#   nested 旧布局：<部署根>/app/ 下才是代码
#   flat   扁平布局：部署根本身就是代码目录（本项目现用）
# ============================================================
set -eu

TARGET="${1:-}"
if [ -z "$TARGET" ]; then
    echo "用法: sudo sh update.sh <部署根目录>"
    exit 1
fi

PKG_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$PKG_DIR/app"
IMG_TAR="$PKG_DIR/dsa-local-img.tar.gz"
STAMP="$(date +%Y%m%d-%H%M%S)"

[ -d "$SRC" ] || { echo "错误：找不到源目录 $SRC"; exit 1; }
[ -d "$TARGET" ] || { echo "错误：目标目录不存在 -> $TARGET"; exit 1; }

# ---- 布局探测 ----
if [ -d "$TARGET/app" ]; then
    LAYOUT="nested"
    DEST="$TARGET/app"
    BAK="$TARGET/app.bak-$STAMP"
else
    LAYOUT="flat"
    DEST="$TARGET"
    BAK="$TARGET.bak-$STAMP"
fi
echo "部署布局：$LAYOUT    代码目录：$DEST"

echo "[1/4] 备份现有代码  ->  $BAK"
mkdir -p "$BAK"
# 注意：GNU tar 的 --exclude 必须写在源路径参数之前，否则不生效
tar -cf - -C "$DEST" \\
    --exclude=./data \\
    --exclude=./logs \\
    --exclude=./reports \\
    --exclude=./share_images \\
    --exclude=./share \\
    --exclude=./longbridge_tokens \\
    --exclude='./*.bak-*' \\
    --exclude='*/__pycache__' \\
    --exclude='*/node_modules' \\
    . | tar -C "$BAK" -xf -

echo "[2/4] 覆盖源码（保留 .env / data / logs / reports / share / longbridge_tokens）"
tar -cf - -C "$SRC" \\
    --exclude=./.env \\
    --exclude=./data \\
    --exclude=./logs \\
    --exclude=./reports \\
    --exclude=./share_images \\
    --exclude=./share \\
    --exclude=./longbridge_tokens \\
    --exclude='./*.bak-*' \\
    --exclude='*/__pycache__' \\
    --exclude='*/node_modules' \\
    . | tar -C "$DEST" -xf -

cd "$DEST"
if [ -f "$IMG_TAR" ]; then
    echo "[3/4] 载入自带镜像（离线，无需联网）"
    docker load -i "$IMG_TAR"
    echo "[4/4] 重启容器（--no-build，直接用载入的镜像）"
    docker compose up -d --no-build --force-recreate
else
    echo "[3/4] 包内无镜像，联网重建（需联网装依赖与 Chromium）"
    docker compose build
    echo "[4/4] 重启容器"
    docker compose up -d --force-recreate
fi

echo
echo "完成。若需回滚："
echo "  rm -rf $DEST && mv $BAK $DEST"
echo "  然后：cd $DEST && docker compose up -d --force-recreate"
"""

# 排除项（update.sh 备份/覆盖两处共用，生成文本用）
UPDATE_EXCLUDES = [
    "./.env",
    "./data",
    "./logs",
    "./reports",
    "./share_images",
    "./share",
    "./longbridge_tokens",
    "./*.bak-*",
    "*/__pycache__",
    "*/node_modules",
]


def build_update_sh(version: str) -> str:
    return UPDATE_SH_TEMPLATE.replace("__DSA_VERSION__", version)


def build_source_notes(version: str, generated: str) -> str:
    return f"""==============================================================
DSA 定制版 · 源码增量更新包（路线 B）
版本：v{version}
生成日期：{generated}
==============================================================

本包用于「已在运行 DSA 的机器」上做源码级增量更新，不带镜像（体积小）。
  dsa-source-v{version}/
  ├── app/       定制版源码（已排除 .env / data / logs / reports / share_images 等）
  ├── update.sh  一键增量更新脚本（备份 → 覆盖 → 重建镜像 → 重启）
  └── 安装说明-源码版.txt  本文件

适用场景：
  目标机已在跑 DSA，只想把源码改动推过去，不想传 ~1.6GB 的完整镜像包。
  目标机必须有已构建好的镜像环境（docker compose build 会联网重装依赖/烘焙 Chromium，
  若目标机离线请勿用此包，改用路线 A 完整迁移包）。

--------------------------------------------------------------
更新步骤
--------------------------------------------------------------
1. 把本包解压到任意目录：
      tar xzf dsa-source-v{version}.tar.gz -C /tmp
2. 执行增量更新（目标机需 sudo 可跑 docker）：
      sudo sh /tmp/dsa-source-v{version}/update.sh /opt/daily-stock-analysis
   其中最后一个参数是「部署根目录」（即包含 app/ 的那一层）。
3. 观察 4 个步骤输出，全部 OK 即完成；容器会自动重建重启。
4. 回滚（若更新后异常）：
      rm -rf /opt/daily-stock-analysis/app
      mv /opt/daily-stock-analysis/app.bak-<时间戳> \\
         /opt/daily-stock-analysis/app
   然后 docker compose up -d --force-recreate 拉起旧版。

--------------------------------------------------------------
与路线 A（完整迁移包）的区别
--------------------------------------------------------------
  - 路线 A（dsa-migration-vX.tar.gz）：含预构建镜像，离线可用，适合新机器/整盘搬迁。
  - 路线 B（本包）：仅源码 + update.sh，需联网重建镜像，适合已在跑的机器做小版本推送。
==============================================================
"""


def emit_source_package(version, base, out_dir, work, generated):
    """生成 dsa-source-v<version>.tar.gz（不含镜像，含 update.sh）"""
    pkg_name = "dsa-source-v%s" % version
    src_stage = work / pkg_name
    src_stage.mkdir(parents=True)
    # 重新打包项目，额外排除 .env；解包进 src_stage/app 保持 app/ 前缀
    print("打包源码（额外排除 .env）…")
    tar_src = ["tar", "-czf", str(work / "app-src.tar.gz"), "-C", str(base)]
    for pattern in SRC_EXCLUDES:
        tar_src.append("--exclude=" + pattern)
    tar_src.append(".")
    run(tar_src)
    src_app = src_stage / "app"
    src_app.mkdir(parents=True, exist_ok=True)
    run(["tar", "-xzf", str(work / "app-src.tar.gz"), "-C", str(src_app)])
    # update.sh（版本号已替换）
    update_sh = src_stage / "update.sh"
    update_sh.write_text(build_update_sh(version), encoding="utf-8")
    os.chmod(str(update_sh), 0o755)
    # 说明
    (src_stage / "安装说明-源码版.txt").write_text(
        build_source_notes(version, generated), encoding="utf-8"
    )
    # 组合
    final = out_dir / (pkg_name + ".tar.gz")
    print("组合源码包:", final)
    run(["tar", "-czf", str(final), "-C", str(work), pkg_name])
    size_mb = final.stat().st_size / 1024 / 1024
    print("完成(源码): %s  (%.1f MB)" % (final, size_mb))


def run(cmd, cwd=None, check=True, capture=False):
    print("  $ " + " ".join(str(c) for c in cmd))
    if capture:
        out = subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)
        return out.stdout.strip()
    subprocess.run(cmd, cwd=cwd, check=check)
    return ""


def read_version(path: Path) -> str:
    if path.exists():
        raw = path.read_text(encoding="utf-8").strip()
        if re.fullmatch(r"\d+\.\d+\.\d+", raw):
            return raw
        print("WARN: VERSION 内容非法 (%r)，按 0.0.0 处理" % raw)
    return "0.0.0"


def bump(version: str, level: str) -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def latest_changelog_entry(path: Path) -> str:
    if not path.exists():
        return "（无 CHANGELOG.md）"
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^## ", text)
    if len(parts) < 2:
        return "（CHANGELOG.md 中暂无版本条目）"
    return "## " + parts[-1].strip()


def build_notes(version: str, changelog: str, image: str, generated: str) -> str:
    return f"""==============================================================
DSA 定制版 · 整盘迁移安装说明（路线 A · 不保留历史）
版本：v{version}
生成日期：{generated}
==============================================================

本包内容：
  dsa-migration-v{version}/
  ├── app/                 定制版源码与配置（已排除 data / logs / reports / share_images 历史）
  │   ├── src/             应用源码
  │   ├── docker/          Dockerfile（已烘焙 Playwright / Chromium 截图引擎）
  │   ├── docker-compose.yml  本地构建版
  │   │                      （image: {image}, pull_policy: never）
  │   ├── tools/           本打包器（升级后重新打迁移包用）
  │   ├── VERSION          当前版本号
  │   ├── CHANGELOG.md     版本变更日志
  │   ├── CUSTOM_CHANGES.md  定制改动明细（相对上游）
  │   └── .env             运行配置（已随包提供，含 API Key / 通知等，勿外泄）
  ├── update.sh            一键增量更新脚本（已在运行的机器升级用，自动识别部署布局）
  ├── dsa-local-img.tar.gz 预构建镜像（docker save 导出，离线即可 load）
  └── 安装说明.txt         本文件

适用场景：
  ① 新机器 / 整盘搬迁：把定制版原样搬过去，不迁移历史报告 / 数据库 / 导出图片。
  ② 已在运行的机器升级：解压后直接跑 update.sh，源码覆盖 + 镜像 load，全程离线。
  两种场景全程均可无需联网（镜像已内置 Chromium 截图引擎）。

本次版本改动（详见 CHANGELOG.md / CUSTOM_CHANGES.md）：
{changelog}

--------------------------------------------------------------
一、新机器前置条件
--------------------------------------------------------------
1. 已安装 Docker 与 docker compose 插件（Docker 24+，compose v2）。
2. 能 SSH 登录，且当前用户能用 sudo 执行 docker（加入 docker 组，或每次 sudo）。
3. 准备一个部署目录，下面以 /opt/daily-stock-analysis/ 为例（可自定）。
4. 若遗留目录出现 mode 000，先 chmod 或 rm -rf 再写。

--------------------------------------------------------------
二、解包
--------------------------------------------------------------
    tar xzf dsa-migration-v{version}.tar.gz -C /tmp
  解压后得到：
    /tmp/dsa-migration-v{version}/{{app, update.sh, dsa-local-img.tar.gz, 安装说明.txt}}

--------------------------------------------------------------
二·五、已在运行的机器升级（推荐，一条命令搞定）
--------------------------------------------------------------
  目标机已经在跑 DSA，只想升到本版本 → 不必走下面第三~五步，直接：

    sudo sh /tmp/dsa-migration-v{version}/update.sh <部署根目录>

  其中 <部署根目录> 是包含 docker-compose.yml 的那一层，例如
    /opt/daily-stock-analysis      （扁平布局：代码就在这一层）
    /opt/daily-stock-analysis      （旧布局：代码在下面的 app/，脚本自动识别）

  update.sh 会依次做：
    [1/4] 备份现有代码 -> <代码目录>.bak-<时间戳>（跳过 data/logs/reports/share 等历史）
    [2/4] 覆盖源码（保留目标机自己的 .env / data / logs / reports / share / longbridge_tokens）
    [3/4] 载入包内镜像 docker load（离线，无需联网重建）
    [4/4] docker compose up -d --no-build --force-recreate 重启
  失败回滚：
    rm -rf <代码目录> && mv <代码目录>.bak-<时间戳> <代码目录>
    cd <代码目录> && docker compose up -d --force-recreate

  提示：升级只覆盖代码，不会动你机器上的数据库和历史报告；界面里改过的配置
  （含 .env 里的 LLM / 通知渠道）也会原样保留。

--------------------------------------------------------------
三、放置 app（定制源码 + 配置）  ← 仅新机器需要
--------------------------------------------------------------
  若目标已有旧 app，先处理「000 权限坑」再覆盖：
    chmod -R u+rwx <部署目录>/app 2>/dev/null
    rm -rf <部署目录>/app
  然后整体拷入：
    cp -a /tmp/dsa-migration-v{version}/app <部署目录>/app
  权限修正（确保 docker 可读、设置页可写）：
    chown -R <你的用户>:<你的组> <部署目录>/app
    chmod -R a+rX <部署目录>/app

--------------------------------------------------------------
四、加载镜像（无需联网）
--------------------------------------------------------------
    docker load -i /tmp/dsa-migration-v{version}/dsa-local-img.tar.gz
  加载后本地出现镜像：{image}
  确认：docker images daily-stock-analysis-local

--------------------------------------------------------------
五、启动（用已加载的镜像，不重建 → 真正离线）
--------------------------------------------------------------
    cd <部署目录>/app
    docker compose up -d --no-build
  说明：本包 compose 带 build 段（方便日后改代码重建）。首次离线启动务必加
  --no-build，否则 compose 会按 build 段重新构建（需联网下载 pip 包与 Chromium）。
  若日后确实要重建：docker compose build && docker compose up -d --force-recreate
  （需联网；构建会把 Chromium 重新烘焙进镜像）。

--------------------------------------------------------------
六、首次启动后必须做
--------------------------------------------------------------
  本包不含历史数据，data/ 为空 → 需重新配置：
   1. 网页打开 http://<机器IP>:8000 → 设置 → 填 LLM 渠道（分析必需）
   2. 设置 → 填通知渠道（Bark 等，走 CUSTOM_WEBHOOK_*，推送必需）
  配置会写回 app/.env，改完重启容器生效。

--------------------------------------------------------------
七、验证
--------------------------------------------------------------
    docker ps                     # 看 stock-server 状态为 healthy
    curl -fsS http://127.0.0.1:8000/api/health
  浏览器访问 http://<机器IP>:8000 打开工作台；跑一次分析确认：
   - 分享图自动落到 <部署目录>/app/share_images/<YYYY-MM-DD>/<名称>-<代码>-<YYYYMMDD>.png
   - 超长报告在通知端按 CUSTOM_WEBHOOK_MAX_BYTES 自动分段推送

--------------------------------------------------------------
八、维护与注意事项
--------------------------------------------------------------
  - .env 已随包提供，含全部配置与密钥；不要把 .env 当单文件 volume 挂进
    /app/.env（会破坏设置页的原子保存）。
  - 数据库 / 历史报告在 data/，本包未包含（不保留历史）；首次启动会重新生成。
  - 仅需 Web/API 或单股轻量场景可调低 MEM_LIMIT（默认 2G）。
  - 后续升级：改完源码后执行
        python3 app/tools/make_migration_package.py [--bump minor|major]
    会自动升级版本号（默认小版本 +1）、写回 VERSION、更新 CHANGELOG 并打新包。
==============================================================
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="DSA 定制版整盘迁移打包器")
    ap.add_argument("--base", default=DEFAULT_BASE, help="项目根目录（扁平化后即为部署目录）")
    ap.add_argument("--image", default=DEFAULT_IMAGE, help="要导出的镜像 tag")
    ap.add_argument("--out", default=None,
                    help="迁移包输出目录（默认 %s）" % DEFAULT_OUT)
    ap.add_argument("--bump", default="patch", choices=["patch", "minor", "major"])
    ap.add_argument("--version", default=None, help="手动指定版本号（覆盖 --bump，仍会写回 VERSION）")
    ap.add_argument("--note", default=None, help="本次改动摘要，追加写入 CHANGELOG.md")
    ap.add_argument("--no-changelog", action="store_true", help="不改动 CHANGELOG")
    ap.add_argument("--with-source", action="store_true",
                    help="（已废弃，默认不出）额外生成 dsa-source-v<版本>.tar.gz；"
                         "update.sh 现已默认并入迁移包，不再需要单独的源码包")
    args = ap.parse_args()

    base = Path(args.base)
    # 项目已扁平化：项目根即 base 本身（不再套 app/ 子目录）
    app_dir = base
    out_dir = Path(args.out) if args.out else Path(DEFAULT_OUT)
    version_file = app_dir / "VERSION"
    changelog_file = app_dir / "CHANGELOG.md"

    if not app_dir.is_dir():
        print("ERROR: 找不到项目目录:", app_dir)
        return 2

    today = datetime.now().strftime("%Y-%m-%d")
    old_version = read_version(version_file)
    new_version = args.version or bump(old_version, args.bump)
    print("版本: %s  ->  %s  (bump=%s)" % (old_version, new_version, args.bump))

    # 1. CHANGELOG
    if args.note and not args.no_changelog:
        entry = "\n## v%s（%s）\n\n%s\n" % (new_version, today, args.note.strip())
        with io.open(str(changelog_file), "a", encoding="utf-8") as fh:
            fh.write(entry)
        print("已写入 CHANGELOG:", changelog_file)
    elif not changelog_file.exists():
        print("WARN: 缺少 CHANGELOG.md")

    # 2. VERSION
    version_file.write_text(new_version + "\n", encoding="utf-8")
    print("已写入 VERSION:", new_version)

    pkg_name = "dsa-migration-v%s" % new_version
    work = Path(tempfile.mkdtemp(prefix="dsa-pkg-"))
    stage = work / pkg_name
    stage.mkdir(parents=True)
    try:
        # 3. 打包项目（排除历史与缓存）。项目已扁平化，以 base 为 context 打 `.`，
        #    再解包进 stage/app，使包内仍保持 app/ 前缀（目标机 <部署目录>/app 解包流程不变）
        print("打包项目源码（排除历史数据/缓存）…")
        # GNU tar：--exclude 必须写在源路径参数之前，否则不生效
        tar_cmd = ["tar", "-czf", str(work / "app.tar.gz"), "-C", str(base)]
        for pattern in EXCLUDES:
            tar_cmd.append("--exclude=" + pattern)
        tar_cmd.append(".")
        run(tar_cmd)
        (stage / "app").mkdir(parents=True, exist_ok=True)
        run(["tar", "-xzf", str(work / "app.tar.gz"), "-C", str(stage / "app")])

        # 4. 导出镜像
        print("导出镜像 %s（可能需要几分钟）…" % args.image)
        img_path = stage / "dsa-local-img.tar.gz"
        with io.open(str(img_path), "wb") as fh:
            save = subprocess.Popen(["docker", "save", args.image], stdout=subprocess.PIPE)
            gzip = subprocess.Popen(["gzip", "-1"], stdin=save.stdout, stdout=fh)
            save.stdout.close()
            gzip.communicate()
            if save.wait() != 0:
                print("ERROR: docker save 失败")
                return 3

        # 5. 安装说明
        notes = build_notes(
            version=new_version,
            changelog=latest_changelog_entry(changelog_file),
            image=args.image,
            generated=today,
        )
        (stage / "安装说明.txt").write_text(notes, encoding="utf-8")

        # 5.1 update.sh：一键增量更新（已并入迁移包，以后不再单独出源码包）
        upd = stage / "update.sh"
        upd.write_text(build_update_sh(new_version), encoding="utf-8")
        os.chmod(str(upd), 0o755)
        print("已写入 update.sh（含于迁移包）")

        # 6. 组合最终包
        out_dir.mkdir(parents=True, exist_ok=True)
        final = out_dir / (pkg_name + ".tar.gz")
        print("组合最终包:", final)
        run(["tar", "-czf", str(final), "-C", str(work), pkg_name])

        size_gb = final.stat().st_size / 1024 / 1024 / 1024
        print()
        print("完成: %s  (%.2f GB)" % (final, size_gb))
        print("包内结构:")
        for line in run(
            ["tar", "-tzf", str(final)], capture=True
        ).splitlines()[:3]:
            print("  " + line)
        print("  …")

        # 7. 源码增量包（可选）
        if args.with_source:
            print()
            emit_source_package(
                version=new_version,
                base=base,
                out_dir=out_dir,
                work=work,
                generated=today,
            )

        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
