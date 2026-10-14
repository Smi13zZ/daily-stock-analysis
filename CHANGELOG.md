# DSA 定制版 · 变更日志

版本号格式 `MAJOR.MINOR.PATCH`（大版本 . 中等变动 . 小版本），按**从右往左**数位：

| 变动级别 | 位 | 示例 | 触发场景 |
| --- | --- | --- | --- |
| 小版本 | 右数第一位（PATCH） | 2.0.1 → 2.0.2 | 文案、bug 修复、参数微调、小范围样式调整 |
| 中等变动 | 右数第二位（MINOR） | 2.0.1 → 2.1.0 | 新增功能、交互/布局变化、新增配置项、新增导出能力 |
| 大版本 | 右数第三位（MAJOR） | 2.1.0 → 3.0.0 | 架构调整、渲染/数据引擎更换、破坏性变更 |

高位 +1 时其右侧低位全部归零。

每次打包由 `tools/make_migration_package.py` 自动升级版本号并写回 `VERSION`：

```bash
python3 app/tools/make_migration_package.py                # 默认小版本 +1
python3 app/tools/make_migration_package.py --bump minor   # 中等变动
python3 app/tools/make_migration_package.py --bump major   # 大版本
python3 app/tools/make_migration_package.py --note "改动摘要"   # 同时追加本条日志
```

---

## v2.0.0（2026-10-07）

基线版本。相对上游 `ZhuLinsen/daily_stock_analysis` 的定制点：

- 分享图页脚自定义：`src/share.py` 的 `_footer()` 去掉 GitHub 仓库链接、小红书二维码/账号与底部免责声明，仅保留标题与副标题。
- 分享图渲染引擎切到 **Playwright / Chromium**：修复 wkhtmltoimage 旧 WebKit 对现代 CSS 支持差、固定高度卡片被 `overflow:hidden` 截断的问题。Chromium 已烘焙进镜像（`PLAYWRIGHT_BROWSERS_PATH=/app/.playwright`）。
- compose 合并为单文件（无 override），固定本地 tag + `pull_policy: never` + 源码构建。

## v2.0.1（2026-10-10）

三项定制改动（详见 `CUSTOM_CHANGES.md`）：

- **手机端可滚动 + 禁止长按选中**：首页高度锁与 `overflow-hidden/overflow-y-auto` 限定到 `md:` 以上，移动端回归整页自然滚动；触摸设备下禁用长按选中与长按呼出菜单，输入框/文本域/下拉框例外。
- **通知按长度自动分段**：`custom_webhook_sender.py` 新增分段发送，非钉钉 Webhook（Bark / Slack / 通用）超过 `CUSTOM_WEBHOOK_MAX_BYTES`（默认 3000 字节）时按语义边界自动拆段，段尾标注 `📄 (i/n)`。
- **报告生成后自动导出分享图**：新增 `src/share_export.py`，在 pipeline（普通 / Agent 两条链路）与大盘复盘的保存钩子上触发，后台线程渲染落盘到
  `share/<YYYY-MM-DD>/<股票名称>-<代码>-<YYYYMMDD>.png`；compose 新增卷映射，开关 `SHARE_AUTO_EXPORT` / `SHARE_EXPORT_DIR`。

## v2.0.2（2026-10-10）

修复手机端反馈的三个问题（详见 `CUSTOM_CHANGES.md`）：

- **侧边抽屉滑不动、滑动穿透到底层页面**：根因是 `.dashboard-card` 自带 `position: relative` 覆盖了 Tailwind 的 `absolute`，抽屉面板高度退化成内容高度（实测 252px，而视口是 844px），内部滚动区只剩 125px 且被 `overflow:hidden` 裁掉，手指滑动只能滚到底层页面。现已恢复绝对定位与满高（844px），抽屉打开期间锁定 body 滚动，上下两栏各自独立滚动并阻断滚动链。实测：抽屉内 `scrollTop` 0 → 660，底层 `window.scrollY` 恒为 0。
- **手机端主区无法翻动（上一版未修好）**：移动端下 `.home-stock-scroll-shell` 在 `<48rem` 被强制 `overflow: visible`，放进 fixed 抽屉后内容被裁掉、既看不到也滚不到。现于抽屉内恢复裁剪，首页主区仍保持整页自然滚动。
- **「历史」tab 与「自选 / 今日」视觉统一**：历史列表不再使用带全选 / 批量删除的独立「个股栏」骨架，改为与另两个 tab 完全同构的 `glass-card + 标题栏 + ScrollArea` 结构；行卡片改为与自选 / 今日一致的简洁卡片（名称 + 代码 + 时间 + 评分徽章），保留单行删除与选中态。

## v2.1.0（2026-10-10）

部署目录瘦身：移除 tests/docs/evals/CI 等开发残留（171M 降至 67M），恢复打包器并重新生成迁移包与源码增量包。

## v2.2.0（2026-10-10）

手机端操作行横向滑动可滚动;复制按钮改用execCommand回退修复内网iOS失效;分享图模块share_image更名为share(目录/代码/路由/组件/i18n全链路);分析报告完成同时导出可读HTML+Markdown到share目录与PNG同目录;修复entrypoint.sh CRLF致容器启动失败

## v2.2.1（2026-10-10）

修复前端版本号注入问题（bug 修复，小版本 +1，升自 v2.2.0）：

- 根因：`docker/Dockerfile` 的 web 构建阶段原本写死 `ARG DSA_WEB_VERSION=0.0.0`，且 `docker-compose.yml` 的 `build:` 段未传该 build arg，导致前端 `build-info.json` 一直回落到占位值，网页版本号显示成 `development`（即版本号「没升上去」）。
- 修复：改为默认从根目录 `VERSION` 文件取版本 —— `COPY VERSION /app/VERSION` + `RUN DSA_WEB_VERSION="${DSA_WEB_VERSION:-$(cat /app/VERSION)}" npm run build`。今后 bump `VERSION`，前端版本号自动同步，无需再手动传 `--build-arg`。
- 本次 v2.2.1 是对已交付 v2.2.0 的版本显示修正；四项功能改动（手机端操作行横滑 / 复制按钮 execCommand 回退修复 / `share_image`→`share` 全链路改名 / 分析报告导出可读 HTML+MD）本身属于 v2.2.0。

## v2.3.0（2026-10-10）

通知分段上限改为界面可调（中等变动 · 新增配置项，升自 v2.2.1）：

- 新增界面配置项 **`CUSTOM_WEBHOOK_MAX_BYTES`**（「通知」分类，数字输入，默认 3000，`0` = 不分段）：设置自定义 Webhook（Bark / Slack / 通用）单条推送的最大字节数。此前只能在 `.env` 里改，且每台机器各自生效，容易「改了但不生效」。
- 接入四处：① `src/config.py` 新增 `custom_webhook_max_bytes` 字段 + 环境变量加载（新增 `_env_int()` 安全解析：非法值回退 3000，避免脏值导致启动失败）；② `src/services/system_config_service.py` 补 env key → Config 属性映射；③ `src/core/config_registry.py` 补界面字段定义（`integer` / `number` / 0–200000 校验 / 帮助键）；④ `apps/dsa-web/src/locales/settingsHelp.ts` 补中英帮助文案。
- 界面保存后**即时生效**：保存流程会 `setup_env(override=True)` 重灌环境变量并 `Config.reset_instance()` 重建配置，**无需重启容器**。
- 分段口径（排查「分段数和预期不符」用）：**段数 ≈ ceil(报告字节数 / (设定值 − 200))**，其中 200 字节为分页标记 `📄 (i/n)` 预留；钉钉走独立的 20000 字节分批逻辑，不受此值影响。
  实测（上限 6000）：6000 字节 → 2 段；12000 字节 → 3 段；29000 字节 → 6 段。

## v2.3.1（2026-10-11）

### 修复
- **自定义 Webhook（Bark）推送失败原因不可见**：失败时日志只记 HTTP 状态码，Bark 返回 500
  （`push failed: PayloadTooLarge`）时完全看不出原因。现在 error 日志会同时记录
  **响应体（截断 300 字符）** 与 **请求体字节数**。
- **单条推送上限填大值会静默全失败**：`CUSTOM_WEBHOOK_MAX_BYTES` 超过 APNs/Bark 单条载荷
  物理上限（实测约 4.7KB：4663 字节成功、5062 字节 500）时，每段都会推送失败。
  现在超过 **4500** 的取值会被自动钳制并写 warning 日志；界面帮助文案（中/英）
  同步补充硬上限说明，推荐值 3000。

### 变更
- **迁移包自带一键升级脚本**：`dsa-migration-vX.tar.gz` 内新增 `update.sh`
  （自动识别 nested/flat 两种部署布局、排除式备份跳过历史数据、包内有镜像时走
  `docker load` + `--no-build` 离线升级、无镜像才联网 `compose build`）。
  自此 **不再单独交付 `dsa-source` 源码包**，migration 系列为唯一交付物。
  安装说明新增「二·五、已在运行的机器升级」章节。

## v2.4.0（2026-10-11）

### 新增
- **分析报告分享方式可在系统设置分别勾选**：原先「PNG + Markdown + HTML 同时导出」是写死的
  固定行为，现拆成三个**互相独立**的开关，位于 设置 → 系统 分类：

  | 开关 | 环境变量 | 默认 | 产物 |
  |---|---|---|---|
  | 分析报告分享：图片（PNG） | `SHARE_AUTO_EXPORT` | 开 | `<分享目录>/<日期>/<名称>-<代码>-<日期>.png` |
  | 分析报告分享：Markdown 原文 | `SHARE_EXPORT_MARKDOWN` | 开 | 同目录 `<STEM>.md` |
  | 分析报告分享：可读 HTML 网页 | `SHARE_EXPORT_HTML` | 开 | 同目录 `<STEM>.html` |

  三者互不依赖，可任意组合（只留图片 / 只留 Markdown / 全开都行）；关闭 HTML 还能省掉一次
  渲染开销。保存即时生效，无需重启容器。
- 兼容：旧的总开关 `SHARE_EXPORT_READABLE=false` 仍会同时关闭 Markdown 与 HTML，老配置不用改。

### 实现
- `src/share_export.py`：新增 `_flag_env()` 布尔解析，把 `is_readable_export_enabled()`
  拆成 `is_markdown_export_enabled()` / `is_html_export_enabled()`；md 与 html 的落盘逻辑
  拆成两个独立 try（互不牵连，任一失败不影响 PNG）。
- `src/config.py`：新增 `share_auto_export` / `share_export_markdown` / `share_export_html` 三个字段及环境变量加载。
- `src/services/system_config_service.py`：补 env key → Config 属性映射（bool）。
- `src/core/config_registry.py`：补三个界面字段（system 分类，boolean/switch，display_order 56–58）。
- `apps/dsa-web/src/locales/settingsHelp.ts`：补中英帮助文案。
