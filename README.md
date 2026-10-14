<div align="center">

# 📈 daily_stock_analysis · 定制增强版

**上游基础上的本地增强分支 —— 聚焦「移动端体验 · 通知送达 · 报告分享」**

[![Upstream](https://img.shields.io/badge/upstream-ZhuLinsen%2Fdaily__stock__analysis-blue)](https://github.com/ZhuLinsen/daily_stock_analysis)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)
[![Version](https://img.shields.io/badge/version-2.4.0-orange)](./VERSION)

</div>

---

## 📌 关于本项目

本项目是 **[ZhuLinsen/daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis)** 的**二次开发版本（Fork）**。

| 项 | 说明 |
| --- | --- |
| **原始作者** | [@ZhuLinsen](https://github.com/ZhuLinsen) |
| **上游仓库** | https://github.com/ZhuLinsen/daily_stock_analysis |
| **上游项目** | LLM 驱动的多市场股票智能分析系统：多源行情、实时新闻、决策看板、自动推送 |
| **许可证** | MIT License © 2026 ZhuLinsen（见 [LICENSE](./LICENSE)，版权声明保持原样） |
| **本仓库定位** | **保留上游全部功能**，只在一层薄薄的「工程增强」上做文章，没有删减或替换上游能力 |

> 🙏 **项目的全部核心能力均来自上游，感谢原作者 @ZhuLinsen 及所有贡献者。**
> 本项目只做锦上添花的本地化增强；如需了解完整功能、数据源清单、全部配置项，请前往上游仓库阅读。**使用或二次开发前，请先给上游点个 Star ⭐。**

本 README 只讲两件事：**① 我在上游基础上做了哪些改动 · ② 怎么把它跑起来**。

---

## 🛠 一、我做了哪些改动

> 完整逐版本日志见 [CHANGELOG.md](./CHANGELOG.md)。当前版本 **v2.4.0**。

### 改动总览

| 版本 | 主题 | 一句话概括 |
| --- | --- | --- |
| v2.0.0 | 分享图 | 分享图页脚去外部链接 / 二维码，渲染引擎换成 Playwright/Chromium |
| v2.0.1 | 移动端 · 通知 · 分享 | 手机端恢复整页滚动 + 长按禁选；Bark 通知按长度自动分段；报告生成后自动导出分享图 |
| v2.0.2 | 移动端 | 修复侧边抽屉滑不动 / 滑动穿透；「历史」tab 与其它 tab 视觉统一 |
| v2.1.0 | 工程 | 部署目录瘦身（移除 tests/docs/evals/CI 等开发残留，171M → 67M） |
| v2.2.0 | 前端 · 分享 | 手机端操作行横滑；复制按钮改用 execCommand 回退（修复内网 iOS 失效）；`share_image` → `share` 全链路改名；报告同时导出可读 HTML + Markdown；修复 `entrypoint.sh` CRLF 致启动失败 |
| v2.2.1 | 工程 | 修复前端版本号注入（构建时从 `VERSION` 读取，网页不再显示 `development`） |
| v2.3.0 | 通知 | 通知分段上限改为**界面可调**，保存即时生效、无需重启容器 |
| v2.3.1 | 通知 · 部署 | Bark 推送失败原因可见；超物理上限自动钳制；迁移包自带一键升级脚本 |
| v2.4.0 | 分享 | 报告分享方式拆成 **PNG / Markdown / HTML 三个独立开关** |

### 按主题细看

#### 1️⃣ 分享图 & 报告导出

- **分享图渲染引擎换血**：把上游默认的 `wkhtmltoimage`（旧 WebKit）换成 **Playwright / Chromium**。旧引擎对现代 CSS 支持差、固定高度卡片会被 `overflow:hidden` 截断；新引擎渲染更准。Chromium 已烘焙进镜像（`PLAYWRIGHT_BROWSERS_PATH=/app/.playwright`），无需联网。
- **分享图页脚去广告化**：去掉上游页脚里的 GitHub 仓库链接、小红书二维码/账号与底部免责声明，只保留标题与副标题 —— 适合作为纯粹的股票分析卡片直接转发。
- **报告生成后自动导出分享产物**（`src/share_export.py`）：在普通分析链路、Agent 链路、大盘复盘的保存钩子上触发，后台线程渲染落盘，不拖慢分析。
- **v2.4.0 三开关独立**：分享产物不再写死"PNG+MD+HTML 全导出"，而是拆成三个互不依赖的开关，可任意组合（只留图片也行）：

  | 开关 | 环境变量 | 默认 | 产物 |
  | --- | --- | --- | --- |
  | 分享图（PNG） | `SHARE_AUTO_EXPORT` | 开 | `<分享目录>/<日期>/<名称>-<代码>-<日期>.png` |
  | Markdown 原文 | `SHARE_EXPORT_MARKDOWN` | 开 | 同目录 `.md` |
  | 可读 HTML 网页 | `SHARE_EXPORT_HTML` | 开 | 同目录 `.html` |

  旧的总开关 `SHARE_EXPORT_READABLE=false` 仍会同时关闭 MD 与 HTML，老配置无需修改。

#### 2️⃣ 通知送达（重点：Bark）

- **超长报告自动分段**：自建 Bark（bark-server → APNs）对单条 body 有硬上限，报告一长整条推送就失败。现在非钉钉 Webhook（Bark / Slack / 通用）超过阈值时，会**按语义边界**（标题、分隔线）自动拆成多段依次推送，段尾标注 `📄 (i/n)`，不会把一行字或表格切一半。
- **分段上限界面可调**（`CUSTOM_WEBHOOK_MAX_BYTES`，设置 → 通知，默认 3000，`0` = 不分段）：保存即时生效，无需重启容器。中文 1 字 ≈ 3 字节，3000 ≈ 1000 汉字/段。
- **上界保护**：APNs / Bark 单条载荷物理上限实测约 **4.7KB**（4663 字节成功、5062 字节报 500）。取值超过 **4500** 会被自动钳制并写 warning，避免"填大了反而全部静默失败"。
- **失败可诊断**：推送失败时日志会同时记录 **响应体（截断 300 字符）** 与 **请求体字节数**，不再只给一个 HTTP 状态码。

#### 3️⃣ 移动端体验

- **首页恢复整页自然滚动**：把上游写死的高度锁与 `overflow-hidden/overflow-y-auto` 限定到 `md:` 及以上，手机端回归整页滚动（修掉"卡在一屏里、地址栏还吃掉一截"）。
- **禁用长按选中 / 长按菜单**：触摸设备下关闭长按选中与长按呼出菜单（输入框、文本域、下拉框例外）。
- **侧边抽屉滚动修复**：根因是 `.dashboard-card` 的 `position: relative` 覆盖了 Tailwind 的 `absolute`，抽屉高度退化成内容高度，导致滑不动且滑动穿透到底层页面；现已恢复绝对定位与满高，抽屉打开时锁定 body 滚动。
- **操作行横向可滑动**、**复制按钮改用 `execCommand` 回退**（修复内网/旧版 iOS 上 `navigator.clipboard` 失效）。
- **「历史」tab 与「自选/今日」视觉统一**：改为同构的 `glass-card + 标题栏 + ScrollArea` 结构。

#### 4️⃣ 工程 & 部署

- **镜像分发 + 单文件 compose**：官方镜像发布在 Docker Hub（`smi1ezz/daily-stock-analysis`，linux/amd64 + linux/arm64 双架构），`docker-compose.yml` 合并为一个文件，默认直接拉取该镜像；想源码构建取消 `build:` 注释即可。
- **GitHub Actions 自动发版**：推送 `v*` tag 会自动构建双架构镜像并推送到 Docker Hub（见 [`.github/workflows/docker-publish.yml`](./.github/workflows/docker-publish.yml)）。
- **前端版本号自动同步**：`docker/Dockerfile` 构建时从根目录 `VERSION` 读取版本号，网页不再显示占位值 `development`。
- **`share_image` → `share` 全链路改名**：目录 / 代码 / 路由 / 组件 / i18n 统一。
- **修复 `entrypoint.sh` CRLF** 导致容器启动失败；仓库提供 [`.gitattributes`](./.gitattributes) 强制 LF，Windows 检出也不会再变成 CRLF。
- **部署目录瘦身**：移除 tests/docs/evals/CI 等开发残留（171M → 67M）。

---

## 🚀 二、安装教程

### 0. 前置条件

- **Docker 24+** 与 **docker compose v2**（`docker compose version` 可验证）
- 建议 **4 GB 以上内存**（运行默认限 2G，可用 `MEM_LIMIT` 调整）
- **首次启动需要联网**：会自动从 Docker Hub 拉取镜像 `smi1ezz/daily-stock-analysis`（体积较大，请耐心等待）；拉取完成后即可离线运行

### 1. 获取代码

```bash
git clone https://github.com/Smi13zZ/daily-stock-analysis.git
cd daily-stock-analysis
```

### 2. 配置 `.env`

```bash
cp .env.example .env
```

`.env.example` 是完整模板（含上游全部配置项说明 + 本定制版新增项）。**最少需要改这几处**：

| 配置 | 说明 |
| --- | --- |
| `STOCK_LIST` | 自选股列表，逗号分隔，如 `600519,300750,002594` |
| LLM Key（任选其一） | `GEMINI_API_KEY` / `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` / `ANSPIRE_API_KEYS` 等，**不配则无法进行 AI 分析** |
| 通知渠道（可选） | 如 `CUSTOM_WEBHOOK_URLS`（Bark / Slack / 通用）、`WECHAT_WEBHOOK_URL`（企微）、`TELEGRAM_BOT_TOKEN` 等 |
| `SCHEDULE_ENABLED` | 设为 `true` 开启容器内定时分析（配合 `SCHEDULE_TIME`，默认按 `TZ` 换算） |

> ⚠️ 不要把 `.env` 作为单文件 volume 挂进容器 `/app/.env` —— 那会让设置页保存配置的原子写入失败。compose 已通过 `env_file` 读取它。

### 3. 拉取镜像并启动

```bash
docker compose pull
docker compose up -d
```

首次会从 Docker Hub 拉取 `smi1ezz/daily-stock-analysis`（linux/amd64 + linux/arm64 自动匹配），随后直接启动，无需本地构建。

> 想从源码自行构建（改过代码 / 想跑未发布的分支）：在 `docker-compose.yml` 里取消 `build:` 两行的注释，然后 `docker compose build && docker compose up -d --force-recreate`。

### 4. 打开工作台

浏览器访问：`http://<服务器IP>:8000`

（改端口：在 `.env` 里设 `API_PORT=xxxx`，同时放通防火墙。）

### 5. 验证

```bash
docker compose ps                 # stock-server 应为 healthy
curl -fsS http://127.0.0.1:8000/api/health
```

跑一次分析后，分享产物会自动落到 `./share/<YYYY-MM-DD>/`：

```
share/2026-10-14/贵州茅台-600519-20261014.png
share/2026-10-14/贵州茅台-600519-20261014.md
share/2026-10-14/贵州茅台-600519-20261014.html
```

### 6. 升级到新版本

```bash
docker compose pull                 # 拉取最新镜像（latest 跟随最新发布版）
docker compose up -d --force-recreate
```

> 想固定到某个版本，把 `docker-compose.yml` 的 `image:` 改成 `smi1ezz/daily-stock-analysis:<版本>`（如 `:2.4.0`）；想同步 compose / `.env.example` 的最新模板再补一句 `git pull`。

### 7. 可选：把「Web 服务」和「定时分析」拆成两个进程

默认由 `server` 容器内置调度器负责定时分析（推荐）。若想拆分：

```bash
# 先把 .env 里 SCHEDULE_ENABLED 改成 false（否则会重复推送）
docker compose --profile scheduler up -d
```

### 8. 常见问题

| 现象 | 排查 |
| --- | --- |
| 网页打不开 | `docker compose logs server` 看启动日志；确认 `API_PORT` 未被占用、防火墙已放通 |
| 网页版本号显示 `development` | 用的是旧构建产物，重新 `docker compose build`（源码构建模式）或 `docker compose pull`（镜像模式）即可（v2.2.1 已修） |
| `docker compose pull` 拉取失败 / 很慢 | 检查网络与 Docker 镜像加速配置；也可用环境变量 `DSA_IMAGE` 指定其它镜像源 |
| Bark 推送失败 | 报告过长看是否触发分段；`CUSTOM_WEBHOOK_MAX_BYTES` 建议 `3000`；日志会打印响应体与请求体字节数 |
| 容器启动即退出，报 `exec format error` 或脚本语法错 | `entrypoint.sh` 被改成 CRLF。本仓库 `.gitattributes` 已强制 LF；若你手动改过，请 `dos2unix docker/entrypoint.sh` |
| 分享产物没生成 | 确认 `SHARE_AUTO_EXPORT=true`；容器内可写 `/app/share`（compose 已映射 `./share`） |

---

## 🤝 三、与上游同步

- 本仓库是上游的**功能超集**：上游已有的数据源、Agent、选股、报告模板等一律保留。
- 上游合并新特性后，可 `git remote add upstream https://github.com/ZhuLinsen/daily_stock_analysis.git && git fetch upstream && git merge upstream/main` 自行跟进。
- 定制改动分散在 `src/share_export.py`、`src/notification_sender/custom_webhook_sender.py`、`src/core/config_registry.py`、`apps/dsa-web/src/**` 等处，均以少量补丁形式叠加，冲突面小。

---

## 📄 四、许可证与致谢

- 本项目遵循上游 **MIT License**，版权声明保持为 **© 2026 ZhuLinsen**（见 [LICENSE](./LICENSE)）。
- 二次开发 / 引用请注明上游来源：[ZhuLinsen/daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis)。
- 再次感谢原作者与社区贡献者 ❤️
