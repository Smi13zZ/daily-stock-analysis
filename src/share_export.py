# -*- coding: utf-8 -*-
"""分享图自动导出。

报告生成并写入分析历史后，自动调用与「分享按钮」完全相同的确定性海报渲染链路
（build_share_html + Playwright Chromium 全页截图），把 PNG 落到宿主机映射目录：

    <SHARE_EXPORT_DIR>/<YYYY-MM-DD>/<股票名称>-<代码>-<YYYYMMDD>.png

并在同一目录下额外生成两份「可阅读」产物（受 SHARE_EXPORT_READABLE 控制）：
    <STEM>.md    原始 Markdown 源文件
    <STEM>.html  由 build_share_html 生成的完整可读网页（与 PNG 同源）

例：/app/share/2026-05-07/盛合晶微-688820-20260507.png(.md/.html)

配置（环境变量，改 .env 后重启容器生效）：
  SHARE_AUTO_EXPORT       是否开启自动导出，默认 true（false/0/no/off 关闭）
  SHARE_EXPORT_DIR        容器内输出目录，默认 /app/share
  SHARE_EXPORT_READABLE   是否额外导出 .md/.html 可读报告，默认 true（同上关闭）

设计约束：
- 任何异常都不向上抛，导出失败绝不影响分析、落库与推送主流程。
- 实际渲染在后台 daemon 线程执行，避免拖慢分析流程；并发渲染用锁串行化，
  防止多只股票同时启动 Chromium 打爆容器内存。
- 渲染引擎/长度上限沿用 config.md2img_engine 与 markdown_to_image_max_chars，
  与前端「分享」按钮产出的图片完全一致。
"""
from __future__ import annotations

import logging
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)

DEFAULT_EXPORT_DIR = "/app/share"
DEFAULT_MAX_CHARS = 15000
DISABLED_VALUES = {"0", "false", "no", "off", "disable", "disabled"}

# Chromium 逐张渲染，同一时间只允许一个导出任务，避免内存峰值叠加
_RENDER_LOCK = threading.Lock()
_INFLIGHT: set = set()
_INFLIGHT_GUARD = threading.Lock()


def _flag_env(name: str, default: bool = True) -> bool:
    """读取布尔型环境变量；未设置或为空时回退默认值，false/0/no/off 等视为关闭。"""
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() not in DISABLED_VALUES


def is_auto_export_enabled() -> bool:
    """是否自动导出分享**图片**（PNG）。可在系统设置「分享图片（PNG）」勾选，默认开启。"""
    return _flag_env("SHARE_AUTO_EXPORT", True)


def get_export_dir() -> Path:
    configured = (os.getenv("SHARE_EXPORT_DIR") or "").strip()
    return Path(configured or DEFAULT_EXPORT_DIR)


def is_readable_export_enabled() -> bool:
    """旧版总开关：是否允许导出可读报告（.md/.html）。默认开启。

    保留仅为向后兼容；细粒度控制请用 SHARE_EXPORT_MARKDOWN / SHARE_EXPORT_HTML。
    """
    return _flag_env("SHARE_EXPORT_READABLE", True)


def is_markdown_export_enabled() -> bool:
    """是否导出 .md 原始 Markdown 报告（系统设置可勾选，默认开启）。"""
    return is_readable_export_enabled() and _flag_env("SHARE_EXPORT_MARKDOWN", True)


def is_html_export_enabled() -> bool:
    """是否导出 .html 可读网页（系统设置可勾选，默认开启）。"""
    return is_readable_export_enabled() and _flag_env("SHARE_EXPORT_HTML", True)


def _sanitize_filename_part(value: Any) -> str:
    text = str(value if value is not None else "").strip()
    text = re.sub(r'[\\/:*?"<>|\r\n\t\s]+', "", text)
    text = text.strip(".-")
    return text


def _share_payload(result: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    """与 api/v1/endpoints/history.py 的 _history_share_payload 保持一致。"""
    if result.get("report_type") == "market_review":
        snapshot = result.get("context_snapshot")
        if isinstance(snapshot, Mapping):
            market_payload = snapshot.get("market_review_payload")
            if isinstance(market_payload, Mapping):
                return market_payload
    raw = result.get("raw_result")
    return raw if isinstance(raw, Mapping) else None


def _pick(result: Mapping[str, Any], keys: tuple, fallback: Any = None) -> Any:
    for key in keys:
        value = result.get(key)
        if value not in (None, ""):
            return value
    return fallback


def export_history_share(
    db_manager: Any,
    record_id: Any,
    *,
    fallback_code: Any = None,
    fallback_name: Any = None,
    config: Any = None,
) -> Optional[str]:
    """渲染并保存一条历史记录的分享图，返回落盘路径；任何失败返回 None。"""
    try:
        if not is_auto_export_enabled():
            logger.debug("分享图自动导出已关闭，跳过 record_id=%s", record_id)
            return None

        # 延迟导入：避免与 src.core.pipeline / storage 形成循环依赖
        from src.config import get_config
        from src.md2img import markdown_to_image
        from src.services.history_service import HistoryService

        config = config or get_config()
        service = HistoryService(db_manager)
        result = service.resolve_and_get_detail(str(record_id))
        if not isinstance(result, Mapping):
            logger.warning("分享图导出跳过：未找到历史记录 %s", record_id)
            return None

        markdown_content = service.get_markdown_report(str(record_id))
        if not markdown_content:
            logger.warning("分享图导出跳过：历史记录 %s 无 Markdown 报告", record_id)
            return None

        max_chars = int(
            getattr(config, "markdown_to_image_max_chars", DEFAULT_MAX_CHARS)
            or DEFAULT_MAX_CHARS
        )
        if len(markdown_content) > max_chars:
            logger.warning(
                "分享图导出跳过：报告 %s 长度 %d 超过上限 %d",
                record_id, len(markdown_content), max_chars,
            )
            return None

        report_type = str(result.get("report_type") or "")
        code = _sanitize_filename_part(
            _pick(result, ("stock_code", "code", "display_code"), fallback_code)
        )
        name = _sanitize_filename_part(
            _pick(result, ("stock_name", "name", "display_name"), fallback_name)
        )
        if report_type == "market_review":
            code = code or "market"
            name = name or "大盘复盘"
        if not name and not code:
            name = f"report-{record_id}"

        now = datetime.now()
        day_dir = now.strftime("%Y-%m-%d")
        stem = "-".join(
            part for part in (name, code, now.strftime("%Y%m%d")) if part
        )

        with _RENDER_LOCK:
            image_bytes = markdown_to_image(
                markdown_content,
                max_chars=max_chars,
                structured_payload=_share_payload(result),
            )
        if not image_bytes:
            logger.warning("分享图导出失败：渲染器未返回图片 (record_id=%s)", record_id)
            return None

        out_dir = get_export_dir() / day_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{stem}.png"
        tmp_path = out_dir / f".{stem}.png.tmp"
        tmp_path.write_bytes(image_bytes)
        os.replace(tmp_path, out_path)
        try:
            os.chmod(out_path, 0o664)
        except OSError:
            pass

        # 可读报告：原始 Markdown 源 + 完整 HTML 网页，与 PNG 同目录
        # 两项各自独立开关（系统设置里可分别勾选），任一失败都不影响 PNG
        if is_markdown_export_enabled():
            try:
                md_path = out_dir / f"{stem}.md"
                md_path.write_text(markdown_content, encoding="utf-8")
                try:
                    os.chmod(md_path, 0o664)
                except OSError:
                    pass
                logger.info("分享 Markdown 已导出：%s", md_path)
            except Exception as md_exc:  # noqa: BLE001 - 不影响 PNG
                logger.warning(
                    "分享 Markdown 导出异常 (record_id=%s): %s", record_id, md_exc, exc_info=True
                )

        if is_html_export_enabled():
            try:
                from src.share import build_share_html

                html = build_share_html(
                    markdown_content,
                    structured_payload=_share_payload(result),
                )
                html_path = out_dir / f"{stem}.html"
                html_path.write_text(html, encoding="utf-8")
                try:
                    os.chmod(html_path, 0o664)
                except OSError:
                    pass
                logger.info("分享 HTML 已导出：%s", html_path)
            except Exception as html_exc:  # noqa: BLE001 - 不影响 PNG
                logger.warning(
                    "分享 HTML 导出异常 (record_id=%s): %s", record_id, html_exc, exc_info=True
                )

        logger.info("分享图已导出：%s (%d KB)", out_path, len(image_bytes) // 1024)
        return str(out_path)
    except Exception as exc:  # noqa: BLE001 - 导出失败不得影响主流程
        logger.warning("分享图导出异常 (record_id=%s): %s", record_id, exc, exc_info=True)
        return None


def auto_export_share_async(
    db_manager: Any,
    record_id: Any,
    *,
    fallback_code: Any = None,
    fallback_name: Any = None,
) -> None:
    """后台线程触发导出，立即返回，不阻塞分析与推送。"""
    try:
        if not is_auto_export_enabled():
            return
        if record_id in (None, "", 0):
            return

        key = str(record_id)
        with _INFLIGHT_GUARD:
            if key in _INFLIGHT:
                return
            _INFLIGHT.add(key)

        def _run() -> None:
            try:
                export_history_share(
                    db_manager,
                    record_id,
                    fallback_code=fallback_code,
                    fallback_name=fallback_name,
                )
            finally:
                with _INFLIGHT_GUARD:
                    _INFLIGHT.discard(key)

        threading.Thread(
            target=_run,
            name=f"share-export-{key}",
            daemon=True,
        ).start()
    except Exception as exc:  # noqa: BLE001
        logger.debug("分享图异步导出调度失败: %s", exc)


__all__ = [
    "DEFAULT_EXPORT_DIR",
    "auto_export_share_async",
    "export_history_share",
    "get_export_dir",
    "is_auto_export_enabled",
    "is_html_export_enabled",
    "is_markdown_export_enabled",
    "is_readable_export_enabled",
]
