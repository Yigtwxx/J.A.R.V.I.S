"""The only JavaScript this project ever runs in a page.

Kept as three fixed strings rather than anything composable, because the model
must not be able to influence what executes. There is no ``evaluate`` action in
``ActionKind`` for the same reason: an agent that can run arbitrary script in a
page it was sent to is not an OSINT tool, it is a browser exploit primitive.

The ordinal each element is stamped with (``data-jarvis-idx``) is what makes an
indexed click safe. Python numbers the list in the order the script returns it,
and the adapter clicks back through the attribute, so "element [7]" resolves to
the same node the screenshot labelled — even on a page that reflows in between.
"""

from __future__ import annotations

IDX_ATTRIBUTE = "data-jarvis-idx"
OVERLAY_CLASS = "jarvis-idx-label"

COLLECT_ELEMENTS_JS = f"""
() => {{
  const SELECTOR = 'a[href], button, input, select, textarea, summary,' +
    '[role=button], [role=link], [role=tab], [role=menuitem], [onclick], [contenteditable=true]';
  const seen = [];
  const nodes = Array.from(document.querySelectorAll(SELECTOR));

  const accessibleName = (el) => {{
    const aria = el.getAttribute('aria-label');
    if (aria) return aria;
    const labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy) {{
      const target = document.getElementById(labelledBy);
      if (target && target.innerText) return target.innerText;
    }}
    if (el.tagName === 'INPUT') {{
      const id = el.getAttribute('id');
      if (id) {{
        const label = document.querySelector('label[for="' + CSS.escape(id) + '"]');
        if (label && label.innerText) return label.innerText;
      }}
      return el.getAttribute('placeholder') || el.getAttribute('name') || el.getAttribute('value') || '';
    }}
    if (el.tagName === 'IMG') return el.getAttribute('alt') || '';
    return (el.innerText || el.getAttribute('title') || '').trim();
  }};

  // A node sharing a <form> with a password field is a credential control even
  // when its label says nothing of the sort. The guard refuses on this flag.
  const inPasswordForm = (el) => {{
    const form = el.closest('form');
    return !!(form && form.querySelector('input[type=password]'));
  }};

  let ordinal = 0;
  for (const el of nodes) {{
    const rect = el.getBoundingClientRect();
    if (rect.width < 4 || rect.height < 4) continue;
    if (rect.bottom < 0 || rect.top > window.innerHeight) continue;
    if (rect.right < 0 || rect.left > window.innerWidth) continue;
    const style = window.getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none' || style.opacity === '0') continue;

    el.setAttribute('{IDX_ATTRIBUTE}', String(ordinal));
    seen.push({{
      idx: ordinal,
      tag: el.tagName,
      role: el.getAttribute('role') || '',
      name: accessibleName(el).slice(0, 200),
      href: el.getAttribute('href') || '',
      type: el.getAttribute('type') || '',
      autocomplete: el.getAttribute('autocomplete') || '',
      disabled: !!(el.disabled || el.getAttribute('aria-disabled') === 'true'),
      in_password_form: inPasswordForm(el),
      box: [rect.left, rect.top, rect.width, rect.height],
    }});
    ordinal += 1;
    if (ordinal >= 60) break;
  }}
  return seen;
}}
"""

DRAW_OVERLAY_JS = f"""
() => {{
  document.querySelectorAll('.{OVERLAY_CLASS}').forEach((n) => n.remove());
  const marked = document.querySelectorAll('[{IDX_ATTRIBUTE}]');
  marked.forEach((el) => {{
    const rect = el.getBoundingClientRect();
    if (rect.width < 4 || rect.height < 4) return;
    const tag = document.createElement('div');
    tag.className = '{OVERLAY_CLASS}';
    tag.textContent = el.getAttribute('{IDX_ATTRIBUTE}');
    tag.style.cssText = [
      'position:fixed',
      'left:' + Math.max(0, rect.left) + 'px',
      'top:' + Math.max(0, rect.top) + 'px',
      'z-index:2147483647',
      'background:#00e5ff',
      'color:#001018',
      'font:700 11px/1.1 monospace',
      'padding:1px 3px',
      'border-radius:3px',
      'pointer-events:none',
    ].join(';');
    document.body.appendChild(tag);

    const ring = document.createElement('div');
    ring.className = '{OVERLAY_CLASS}';
    ring.style.cssText = [
      'position:fixed',
      'left:' + rect.left + 'px',
      'top:' + rect.top + 'px',
      'width:' + rect.width + 'px',
      'height:' + rect.height + 'px',
      'z-index:2147483646',
      'border:1px solid rgba(0,229,255,0.75)',
      'border-radius:2px',
      'pointer-events:none',
    ].join(';');
    document.body.appendChild(ring);
  }});
  return marked.length;
}}
"""

CLEAR_OVERLAY_JS = f"""
() => {{
  document.querySelectorAll('.{OVERLAY_CLASS}').forEach((n) => n.remove());
  return true;
}}
"""

PAGE_CONTEXT_JS = """
() => ({
  title: document.title || '',
  url: location.href,
  scrollY: Math.round(window.scrollY || 0),
  scrollHeight: Math.round(document.documentElement.scrollHeight || 0),
  innerHeight: Math.round(window.innerHeight || 0),
  text: (document.body ? document.body.innerText : '').slice(0, 4000),
  hasPassword: !!document.querySelector('input[type=password]'),
})
"""
