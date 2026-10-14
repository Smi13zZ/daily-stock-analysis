// 跨浏览器复制工具：优先使用 navigator.clipboard，在非安全上下文（如内网 http）、
// iOS Safari 等 navigator.clipboard 不可用或被禁用的环境下，回退到
// 临时 textarea + document.execCommand('copy')，保证手机端也能复制成功。
export async function copyToClipboard(text: string): Promise<boolean> {
  if (text === '') {
    return false;
  }

  // 1) 现代 API：navigator.clipboard 仅在安全上下文存在，非安全上下文（http 内网）为 undefined，
  //    此时落到下方 execCommand 回退。若 writeText 抛错也回退。
  try {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // 落到下方回退路径
  }

  // 2) 回退：execCommand('copy')。必须在用户手势（点击）回调内同步调用才有效。
  try {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.contentEditable = 'true';
    textarea.style.position = 'fixed';
    textarea.style.top = '-9999px';
    textarea.style.left = '-9999px';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    const range = document.createRange();
    range.selectNodeContents(textarea);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    textarea.setSelectionRange(0, text.length);
    const successful = document.execCommand('copy');
    document.body.removeChild(textarea);
    return successful;
  } catch {
    return false;
  }
}
