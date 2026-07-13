/**
 * Pure HTML renderer for the sidebar control panel.
 *
 * Replaces the old chat-styled sidebar: no message bubbles, no
 * pretend conversation. The panel is a compact control surface in the
 * dashboard's design language: analyze input, last run summary,
 * recent runs (click-through to the dashboard), setup checklist and
 * quick actions. Sections are individually toggleable via the
 * redcon.views.* settings.
 */

import type { RunReport, RunHistoryEntry } from '../types';

export interface ControlSections {
  lastRun: boolean;
  recentRuns: boolean;
  setup: boolean;
  quickActions: boolean;
}

export interface ControlNotice {
  kind: 'info' | 'success' | 'error';
  text: string;
}

export interface ControlViewData {
  run: RunReport | null;
  history: RunHistoryEntry[];
  busyLabel: string | null;
  notice: ControlNotice | null;
  setup: { cliInstalled: boolean; mcpConfigured: boolean } | null;
  sections: ControlSections;
}

function esc(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function fmtK(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 100) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

/* Brand triple-chevron section marker, same as the dashboard. */
const CHEVRON_SVG =
  '<svg width="12.2" height="8" viewBox="0 14.5 69.3 45.4" fill="currentColor" aria-hidden="true">' +
  '<polygon points="0,14.5 12.25,14.5 31.05,37.2 12.25,59.9 0,59.9 18.8,37.2"></polygon>' +
  '<polygon points="19.12,14.5 31.37,14.5 50.17,37.2 31.37,59.9 19.12,59.9 37.92,37.2"></polygon>' +
  '<polygon points="38.24,14.5 50.49,14.5 69.29,37.2 50.49,59.9 38.24,59.9 57.04,37.2"></polygon>' +
  '</svg>';

export function renderControlViewHtml(data: ControlViewData, nonce: string): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Redcon</title>
  <style nonce="${nonce}">
    body {
      --panel: #FFFFFF; --border: #E2E4EA; --border2: #CFD1D6;
      --text: #24272E; --text2: #5C6069; --text3: #8D9199;
      --track: #E8EAEE; --chip: #EEF0F3; --rowHover: rgba(15,30,60,0.045);
      --good: #178A5E; --goodBg: rgba(23,138,94,0.10);
      --warn: #9A7514; --warnBg: rgba(154,117,20,0.10);
      --bad: #E51414; --badBg: rgba(229,20,20,0.10);
      --red: #E51414; --redHov: #C51111;
      --delta: #178A5E;
      --mono: ui-monospace, 'SF Mono', 'Cascadia Mono', Menlo, Consolas, monospace;
      --display: 'Telegraf', -apple-system, 'Segoe UI', sans-serif;
    }
    body.vscode-dark, body.vscode-high-contrast {
      --panel: #242529; --border: #3A3B42; --border2: #4C4D55;
      --text: #D8D8DC; --text2: #9EA0A6; --text3: #6E7076;
      --track: #3A3B42; --chip: #313136; --rowHover: rgba(255,255,255,0.05);
      --good: #3FAE87; --goodBg: rgba(63,174,135,0.14);
      --warn: #D3A83C; --warnBg: rgba(211,168,60,0.14);
      --bad: #E51414; --badBg: rgba(229,20,20,0.15);
      --delta: #3FAE87;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      font-size: 12px; line-height: 1.45;
      color: var(--text);
      background: var(--vscode-sideBar-background, transparent);
      padding: 10px 12px 16px;
      display: flex; flex-direction: column; gap: 14px;
    }
    .num { font-variant-numeric: tabular-nums; }

    .section-title {
      display: inline-flex; align-items: center; gap: 2px;
      font-family: var(--display); font-weight: 800; font-size: 11.5px;
      letter-spacing: 0.01em; text-transform: lowercase; color: var(--text);
      margin-bottom: 7px;
    }
    .section-title svg { color: var(--red); }

    textarea {
      width: 100%; resize: vertical; min-height: 54px;
      background: var(--vscode-input-background, var(--panel));
      color: var(--vscode-input-foreground, var(--text));
      border: 1px solid var(--border); border-radius: 5px;
      padding: 7px 9px; font-family: inherit; font-size: 12px;
    }
    textarea:focus { outline: 1px solid var(--red); border-color: var(--red); }

    .btn {
      display: inline-flex; align-items: center; justify-content: center; gap: 6px;
      height: 26px; padding: 0 12px; border-radius: 5px; font-size: 12px;
      cursor: pointer; font-family: inherit; border: 1px solid var(--border);
      background: var(--chip); color: var(--text); transition: background 0.15s;
    }
    .btn:hover { background: var(--rowHover); }
    .btn:disabled { opacity: 0.55; cursor: default; }
    .btn-primary {
      background: var(--red); border-color: transparent;
      color: #fff; font-weight: 700; width: 100%;
    }
    .btn-primary:hover { background: var(--redHov); }
    .analyze-actions { margin-top: 7px; }

    .notice {
      margin-top: 8px; padding: 6px 9px; border-radius: 5px; font-size: 11.5px;
      border: 1px solid var(--border); color: var(--text2); background: var(--chip);
    }
    .notice.success { border-color: var(--good); color: var(--good); background: var(--goodBg); }
    .notice.error { border-color: var(--bad); color: var(--bad); background: var(--badBg); }

    .busy { display: flex; align-items: center; gap: 8px; margin-top: 8px; color: var(--text2); font-size: 11.5px; }
    .spinner {
      width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0;
      border: 2px solid var(--track); border-top-color: var(--red);
      animation: spin 0.8s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    .card {
      background: var(--panel); border: 1px solid var(--border);
      border-radius: 6px; padding: 10px 12px;
    }
    .lastrun-value { font-family: var(--display); font-weight: 800; font-size: 22px; color: var(--delta); line-height: 1.2; }
    .lastrun-label { font-size: 10.5px; font-weight: 700; color: var(--text2); text-transform: lowercase; }
    .lastrun-sub { display: flex; align-items: center; gap: 8px; margin-top: 5px; font-size: 11px; color: var(--text2); flex-wrap: wrap; }
    .lastrun-task {
      margin-top: 5px; font-size: 11px; color: var(--text3);
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .pill {
      display: inline-flex; align-items: center; gap: 5px;
      padding: 1px 8px; border-radius: 99px; font-size: 10.5px; font-weight: 650;
    }
    .pill .dot { width: 6px; height: 6px; border-radius: 99px; background: currentColor; }
    .pill-low { background: var(--goodBg); color: var(--good); }
    .pill-medium { background: var(--warnBg); color: var(--warn); }
    .pill-high { background: var(--bad); color: #fff; }
    .card .btn { margin-top: 9px; width: 100%; }

    .run-row {
      display: flex; align-items: center; gap: 8px;
      padding: 5px 6px; border-radius: 4px; cursor: pointer;
      transition: background 0.12s;
    }
    .run-row:hover { background: var(--rowHover); }
    .run-task { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11.5px; }
    .run-saved { font-family: var(--mono); font-size: 11px; color: var(--delta); font-weight: 600; flex-shrink: 0; }
    .empty-hint { font-size: 11px; color: var(--text3); padding: 2px 6px; }

    .setup-step { display: flex; align-items: flex-start; gap: 8px; padding: 5px 0; }
    .setup-icon {
      width: 16px; height: 16px; border-radius: 99px; flex-shrink: 0;
      display: inline-flex; align-items: center; justify-content: center;
      font-size: 10px; font-weight: 700;
      background: var(--chip); color: var(--text2); border: 1px solid var(--border);
    }
    .setup-step.done .setup-icon { background: var(--goodBg); color: var(--good); border-color: transparent; }
    .setup-body { flex: 1; min-width: 0; }
    .setup-name { font-size: 11.5px; font-weight: 600; }
    .setup-step.done .setup-name { color: var(--text3); text-decoration: line-through; }
    .setup-body .btn { height: 22px; font-size: 11px; margin-top: 4px; padding: 0 9px; }
    .setup-done-line { font-size: 11px; color: var(--good); }

    .qa-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
  </style>
</head>
<body>
  ${renderAnalyze(data)}
  ${data.sections.lastRun ? renderLastRun(data.run) : ''}
  ${data.sections.recentRuns ? renderRecentRuns(data.history) : ''}
  ${data.sections.setup ? renderSetup(data.setup) : ''}
  ${data.sections.quickActions ? renderQuickActions() : ''}
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();

    // Preserve the draft task across full re-renders.
    const input = document.getElementById('task-input');
    if (input) {
      const prev = vscode.getState();
      if (prev && prev.draft && !input.value) input.value = prev.draft;
      input.addEventListener('input', () => vscode.setState({ draft: input.value }));
      input.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') submit();
      });
    }

    function submit() {
      if (!input || !input.value.trim()) return;
      vscode.postMessage({ command: 'analyze', text: input.value.trim() });
    }

    document.addEventListener('click', (e) => {
      const el = e.target.closest('[data-action]');
      if (!el) return;
      const action = el.dataset.action;
      if (action === 'analyze') submit();
      else if (action === 'open-run') vscode.postMessage({ command: 'openRun', path: el.dataset.path });
      else vscode.postMessage({ command: 'exec', action });
    });
  </script>
</body>
</html>`;
}

function renderAnalyze(data: ControlViewData): string {
  const busy = data.busyLabel
    ? `<div class="busy"><span class="spinner"></span>${esc(data.busyLabel)}</div>`
    : '';
  const notice = !data.busyLabel && data.notice
    ? `<div class="notice ${data.notice.kind}">${esc(data.notice.text)}</div>`
    : '';
  return `
    <div>
      <div class="section-title">${CHEVRON_SVG}<span>analyze</span></div>
      <textarea id="task-input" rows="3" placeholder="Describe the task, e.g. add rate limiting to auth endpoints"></textarea>
      <div class="analyze-actions">
        <button class="btn btn-primary" data-action="analyze" ${data.busyLabel ? 'disabled' : ''}>Analyze</button>
      </div>
      ${busy}${notice}
    </div>
  `;
}

function riskPill(risk: string): string {
  if (risk === 'high') return '<span class="pill pill-high">high risk</span>';
  if (risk === 'medium') return '<span class="pill pill-medium">medium risk</span>';
  return '<span class="pill pill-low"><span class="dot"></span>low risk</span>';
}

function renderLastRun(run: RunReport | null): string {
  if (!run) {
    return `
      <div>
        <div class="section-title">${CHEVRON_SVG}<span>last run</span></div>
        <div class="empty-hint">No analysis yet. Describe a task above.</div>
      </div>`;
  }
  const saved = run.budget.estimated_saved_tokens;
  const pct = run.max_tokens > 0
    ? Math.round((run.budget.estimated_input_tokens / run.max_tokens) * 100)
    : 0;
  return `
    <div>
      <div class="section-title">${CHEVRON_SVG}<span>last run</span></div>
      <div class="card">
        <div class="lastrun-label">tokens saved</div>
        <div class="lastrun-value num">${fmtK(saved)}</div>
        <div class="lastrun-sub num">
          <span>${pct}% budget</span>
          <span>${run.files_included.length} files</span>
          ${riskPill(run.budget.quality_risk_estimate)}
        </div>
        <div class="lastrun-task" title="${esc(run.task)}">${esc(run.task)}</div>
        <button class="btn" data-action="dashboard">Open Dashboard</button>
      </div>
    </div>
  `;
}

function renderRecentRuns(history: RunHistoryEntry[]): string {
  const rows = history.slice(0, 8).map((e) => `
    <div class="run-row" data-action="open-run" data-path="${esc(e.path)}" title="${esc(e.task)}">
      <span class="run-task">${esc(e.task)}</span>
      <span class="run-saved">${fmtK(e.tokensSaved ?? 0)}</span>
    </div>`);
  return `
    <div>
      <div class="section-title">${CHEVRON_SVG}<span>recent runs</span></div>
      ${rows.length ? rows.join('') : '<div class="empty-hint">Run history appears here.</div>'}
    </div>
  `;
}

function renderSetup(setup: { cliInstalled: boolean; mcpConfigured: boolean } | null): string {
  if (!setup) return '';
  if (setup.cliInstalled && setup.mcpConfigured) {
    return `
      <div>
        <div class="section-title">${CHEVRON_SVG}<span>setup</span></div>
        <div class="setup-done-line">&#10003; CLI installed &middot; MCP configured</div>
      </div>`;
  }
  return `
    <div>
      <div class="section-title">${CHEVRON_SVG}<span>setup</span></div>
      <div class="setup-step ${setup.cliInstalled ? 'done' : ''}">
        <span class="setup-icon">${setup.cliInstalled ? '&#10003;' : '1'}</span>
        <div class="setup-body">
          <div class="setup-name">Install Redcon CLI</div>
          ${setup.cliInstalled ? '' : '<button class="btn" data-action="setupInstall">Install</button>'}
        </div>
      </div>
      <div class="setup-step ${setup.mcpConfigured ? 'done' : ''}">
        <span class="setup-icon">${setup.mcpConfigured ? '&#10003;' : '2'}</span>
        <div class="setup-body">
          <div class="setup-name">Register MCP for your agents</div>
          ${setup.mcpConfigured ? '' : '<button class="btn" data-action="setupMcp">Register</button>'}
        </div>
      </div>
    </div>
  `;
}

function renderQuickActions(): string {
  return `
    <div>
      <div class="section-title">${CHEVRON_SVG}<span>quick actions</span></div>
      <div class="qa-grid">
        <button class="btn" data-action="doctor">Doctor</button>
        <button class="btn" data-action="copy">Copy Context</button>
        <button class="btn" data-action="sync">Sync Context</button>
        <button class="btn" data-action="config">Config</button>
      </div>
    </div>
  `;
}
