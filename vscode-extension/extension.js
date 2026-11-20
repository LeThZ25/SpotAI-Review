// @ts-nocheck
// CommonJS source is also valid JavaScript. extension.js is the packaged copy.
const vscode = require('vscode');
const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const net = require('net');
const { spawn } = require('child_process');
const { randomBytes } = require('crypto');

let panel;
let analysisPanel;
let analysisTarget;
let analysisRequestId = 0;
let lastCodeEditor;
let backend;
let output;
let currentUrl;
let panelOnline = false;
let backendAddress;
let startupPromise;
let panelStartupPromise;

function serverUrl() {
  const configured = vscode.workspace.getConfiguration('spotai').get('serverUrl', '').trim();
  if (!configured) return undefined;
  try {
    const parsed = new URL(configured);
    if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username ||
        parsed.password || parsed.search || parsed.hash || parsed.pathname !== '/') {
      throw new Error('Invalid address');
    }
    return parsed;
  } catch {
    throw new Error('spotai.serverUrl must be a valid http(s) origin.');
  }
}

function checkHealth(address) {
  return new Promise(resolve => {
    const client = address.protocol === 'https:' ? https : http;
    const req = client.get(new URL('/api/health', address), { timeout: 2000 }, response => {
      response.resume();
      resolve(response.statusCode === 200);
    });
    req.on('error', () => resolve(false));
    req.on('timeout', () => req.destroy());
  });
}

function availablePort() {
  return new Promise((resolve, reject) => {
    const probe = net.createServer();
    probe.once('error', reject);
    probe.listen(0, '127.0.0.1', () => {
      const port = probe.address().port;
      probe.close(error => error ? reject(error) : resolve(port));
    });
  });
}

async function startBackend(context) {
  const remote = serverUrl();
  if (remote) {
    if (await checkHealth(remote)) return remote;
    throw new Error('Configured SpotAI server is offline: ' + remote.origin);
  }

  if (backend && backendAddress && await checkHealth(backendAddress)) return backendAddress;
  if (backend) backend.kill();

  const executable = path.join(context.extensionPath, 'backend', 'spotai_backend', 'spotai_backend.exe');
  if (!fs.existsSync(executable)) {
    throw new Error('Bundled SpotAI backend is missing. Reinstall the complete Windows x64 VSIX.');
  }
  const dataRoot = context.globalStorageUri.fsPath;
  fs.mkdirSync(dataRoot, { recursive: true });
  const allowedRoots = (vscode.workspace.workspaceFolders || []).map(folder => folder.uri.fsPath);
  const port = await availablePort();
  const address = new URL('http://127.0.0.1:' + port + '/');
  const environment = {
    ...process.env,
    SPOTAI_DATA_ROOT: dataRoot,
    SPOTAI_CACHE_FILE: path.join(dataRoot, '.ai_refactor_cache.json'),
    SPOTAI_ALLOWED_ROOTS: [...allowedRoots, process.env.SPOTAI_ALLOWED_ROOTS || '']
      .filter(Boolean).join(path.delimiter)
  };
  output.appendLine('Starting bundled SpotAI backend on ' + address.origin);
  const child = spawn(executable, ['--web', '--host', '127.0.0.1', '--port', String(port)], {
    cwd: dataRoot, env: environment, shell: false, windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe']
  });
  backend = child;
  backendAddress = address;
  let startupError;
  child.stdout.on('data', data => output.append(data.toString()));
  child.stderr.on('data', data => output.append(data.toString()));
  child.on('error', error => {
    startupError = error;
    output.appendLine('Startup error: ' + error.message);
  });
  child.on('exit', code => {
    output.appendLine('Backend exited: ' + code);
    if (backend === child) {
      backend = undefined;
      backendAddress = undefined;
    }
  });

  for (let attempt = 0; attempt < 80; attempt++) {
    if (startupError || child.exitCode !== null) break;
    if (await checkHealth(address)) return address;
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  if (backend === child) child.kill();
  output.show(true);
  throw new Error('Bundled SpotAI backend failed to start. See Output > SpotAI Backend.' +
    (startupError ? ' ' + startupError.message : ''));
}

async function launchBackend(context) {
  if (!startupPromise) {
    startupPromise = startBackend(context).finally(() => { startupPromise = undefined; });
  }
  return startupPromise;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, ch =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);
}

function analyzeCode(address, language, code) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify({ language, code });
    const client = address.protocol === 'https:' ? https : http;
    const request = client.request(new URL('/api/analyze-snippet', address), {
      method: 'POST',
      timeout: 60000,
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload, 'utf8')
      }
    }, response => {
      const parts = [];
      let size = 0;
      response.on('data', chunk => {
        size += chunk.length;
        if (size > 8 * 1024 * 1024) {
          response.destroy(new Error('SpotAI response exceeds the 8 MB limit.'));
          return;
        }
        parts.push(chunk);
      });
      response.on('error', reject);
      response.on('end', () => {
        try {
          const result = JSON.parse(Buffer.concat(parts).toString('utf8'));
          if (response.statusCode < 200 || response.statusCode >= 300) {
            const detail = typeof result.detail === 'string' ? result.detail : result.message;
            throw new Error(detail || 'SpotAI API returned HTTP ' + response.statusCode);
          }
          resolve(result);
        } catch (error) {
          reject(error);
        }
      });
    });
    request.on('timeout', () => request.destroy(new Error('SpotAI analysis timed out.')));
    request.on('error', reject);
    request.end(payload);
  });
}

function analysisHtml(title, content) {
  const nonce = randomBytes(16).toString('hex');
  const csp = "default-src 'none'; script-src 'nonce-" + nonce +
    "'; style-src 'nonce-" + nonce + "'; base-uri 'none'; form-action 'none';";
  const style = [
    'body{margin:0;padding:24px;font-family:var(--vscode-font-family);color:var(--vscode-foreground);background:var(--vscode-editor-background);line-height:1.5}',
    'header{margin-bottom:20px}h1{font-size:21px;margin:0 0 4px}h2{font-size:17px;margin:24px 0 12px}h3{font-size:14px;margin:0}',
    '.muted{color:var(--vscode-descriptionForeground)}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(135px,1fr));gap:10px}',
    '.card,.issue,.notice{border:1px solid var(--vscode-panel-border);border-radius:7px;padding:14px;background:var(--vscode-editorWidget-background)}',
    '.card strong{display:block;font-size:21px;margin-top:3px}.issue{margin-bottom:10px}.issue summary{cursor:pointer;line-height:1.7}',
    '.issue summary strong{margin:0 6px}.issue-body{padding-top:10px}.tag{font-size:11px;font-weight:700;padding:3px 7px;border-radius:4px;background:var(--vscode-badge-background);color:var(--vscode-badge-foreground)}',
    '.pass{color:var(--vscode-testing-iconPassed, #4caf50)}.fail{color:var(--vscode-testing-iconFailed, #e57373)}',
    'pre{overflow:auto;padding:12px;background:var(--vscode-textCodeBlock-background);white-space:pre-wrap;overflow-wrap:anywhere}',
    'button{cursor:pointer;padding:5px 10px;background:var(--vscode-button-secondaryBackground);color:var(--vscode-button-secondaryForeground);border:0;border-radius:4px}',
    'table{width:100%;border-collapse:collapse}th,td{border-bottom:1px solid var(--vscode-panel-border);padding:7px;text-align:left}',
    '.table-wrap{overflow-x:auto}.notice{margin-top:15px}p{margin:8px 0}summary:focus-visible,button:focus-visible{outline:2px solid var(--vscode-focusBorder)}'
  ].join('');
  const script = [
    'const vscode = acquireVsCodeApi();',
    "document.querySelectorAll('button[data-line]').forEach(button => {",
    "  button.addEventListener('click', () => vscode.postMessage({command:'revealIssue',line:Number(button.dataset.line)}));",
    '});'
  ].join('\n');
  return '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">' +
    '<meta http-equiv="Content-Security-Policy" content="' + escapeHtml(csp) + '">' +
    '<meta name="viewport" content="width=device-width, initial-scale=1">' +
    '<title>' + escapeHtml(title) + '</title><style nonce="' + nonce + '">' + style +
    '</style></head><body>' + content + '<script nonce="' + nonce + '">' + script + '</script></body></html>';
}

function renderAnalysis(result, fileName, selected, firstLine) {
  const title = (selected ? 'Selected code' : 'Entire file') + ' · ' + fileName;
  const header = '<header><h1>SpotAI Code Review</h1><div class="muted">' +
    escapeHtml(title) + '</div></header>';
  if (result.status !== 'success') {
    const line = Number(result.line);
    const location = Number.isSafeInteger(line) && line > 0 ? ' · line ' + (firstLine + line - 1) : '';
    return analysisHtml(title, header + '<div class="notice" role="alert"><strong>Analysis could not complete' +
      escapeHtml(location) + '</strong><p>' + escapeHtml(result.message || result.status || 'Unknown error') + '</p></div>');
  }

  const summary = result.summary || {};
  const values = [
    ['Issues', summary.issues_count ?? (result.issues || []).length],
    ['Lines of code', summary.total_loc ?? '—'],
    ['Maximum CC', summary.max_cc ?? '—'],
    ['Average CC', summary.average_cc ?? '—'],
    ['Maintainability', summary.average_mi ?? '—']
  ];
  const cards = values.map(([label, value]) => '<div class="card"><span class="muted">' +
    escapeHtml(label) + '</span><strong>' + escapeHtml(value) + '</strong></div>').join('');
  const gate = summary.quality_gate_passed === true ? 'PASS' : 'FAIL';
  const gateClass = gate === 'PASS' ? 'pass' : 'fail';
  const issues = Array.isArray(result.issues) ? result.issues : [];
  const issueHtml = issues.map((issue, index) => {
    const line = Number(issue.start_line);
    const actualLine = Number.isSafeInteger(line) && line > 0 ? firstLine + line - 1 : undefined;
    const jump = actualLine === undefined ? '' : '<button type="button" data-line="' + actualLine +
      '">Go to line ' + actualLine + '</button>';
    const detail = (heading, value, code = false) => value ? '<p><strong>' + heading + '</strong></p>' +
      (code ? '<pre><code>' + escapeHtml(value) + '</code></pre>' : '<p>' + escapeHtml(value) + '</p>') : '';
    return '<details class="issue"' + (index === 0 ? ' open' : '') + '><summary><span class="tag">' +
      escapeHtml(issue.severity || 'INFO') + '</span><strong>' + escapeHtml(issue.type || issue.category || 'Finding') +
      '</strong>' + escapeHtml(issue.message || '') + (actualLine ? ' · line ' + actualLine : '') +
      '</summary><div class="issue-body">' + jump +
      detail('Affected code', issue.code_snippet, true) +
      detail('Explanation · ' + (escapeHtml(issue.ai_provider || 'Static analysis')), issue.ai_explanation) +
      detail('Suggested refactoring', issue.ai_refactored_code, true) +
      detail('Limitations', issue.ai_limitations) + '</div></details>';
  }).join('');
  const metrics = (Array.isArray(result.metrics) ? result.metrics : []).map(metric =>
    '<tr><td>' + escapeHtml(metric.method_name || '—') + '</td><td>' +
    escapeHtml(metric.cyclomatic_complexity ?? '—') + '</td><td>' +
    escapeHtml(metric.cognitive_complexity ?? '—') + '</td><td>' +
    escapeHtml(metric.maintainability_index ?? '—') + '</td></tr>').join('');
  const metricSection = metrics ? '<h2>Method metrics</h2><div class="table-wrap"><table><thead><tr>' +
    '<th scope="col">Method</th><th scope="col">CC</th><th scope="col">Cognitive</th><th scope="col">MI</th>' +
    '</tr></thead><tbody>' + metrics + '</tbody></table></div>' : '';
  return analysisHtml(title, header + '<div class="cards">' + cards + '</div>' +
    '<p><strong>Quality Gate <span class="' + gateClass + '">' + gate + '</span></strong></p>' +
    '<h2>Findings (' + issues.length + ')</h2>' + (issueHtml || '<div class="notice">No issues detected.</div>') +
    metricSection);
}

function showAnalysisPanel(context, document, viewColumn) {
  if (!analysisPanel) {
    analysisPanel = vscode.window.createWebviewPanel('spotaiAnalysis', 'SpotAI Code Review',
      vscode.ViewColumn.Beside, {
        enableScripts: true, retainContextWhenHidden: true, localResourceRoots: []
      });
    analysisPanel.webview.onDidReceiveMessage(async message => {
      if (!message || message.command !== 'revealIssue' ||
          !Number.isSafeInteger(message.line) || message.line < 1 || !analysisTarget) return;
      const target = analysisTarget;
      if (message.line > target.document.lineCount) return;
      const cursor = new vscode.Position(message.line - 1, 0);
      await vscode.window.showTextDocument(target.document, {
        viewColumn: target.viewColumn, preserveFocus: false,
        selection: new vscode.Range(cursor, cursor)
      });
    }, undefined, context.subscriptions);
    analysisPanel.onDidDispose(() => {
      analysisPanel = undefined;
      analysisTarget = undefined;
      analysisRequestId++;
    }, undefined, context.subscriptions);
  } else {
    analysisPanel.reveal(vscode.ViewColumn.Beside);
  }
  analysisTarget = { document, viewColumn };
  return analysisPanel;
}

function renderHtml(address, online, loading = false) {
  const origin = address ? address.origin : '';
  const nonce = randomBytes(16).toString('hex');
  const csp = "default-src 'none'; frame-src " + (online ? origin : "'none'") +
    "; script-src 'nonce-" + nonce + "'; style-src 'nonce-" + nonce +
    "'; img-src data:; base-uri 'none'; form-action 'none';";
  const body = online
    ? '<iframe id="spotai-frame" title="SpotAI-Review" sandbox="allow-scripts allow-same-origin allow-forms allow-downloads" referrerpolicy="no-referrer" src="' + escapeHtml(origin) + '/"></iframe>'
    : loading
      ? '<main role="status"><h2>Starting SpotAI-Review…</h2><p>Preparing the bundled analysis engine.</p></main>'
      : '<main><h2>SpotAI backend is offline</h2><p>Could not start the bundled analyzer. Check <strong>Output → SpotAI Backend</strong> for details.</p>' +
        '<button id="start">Start Local Backend</button><button id="retry">Retry</button></main>';
  const script = loading || online ? '' : [
      'const vscode = acquireVsCodeApi();',
      "document.getElementById('start').addEventListener('click', () => vscode.postMessage({command:'startServer'}));",
      "document.getElementById('retry').addEventListener('click', () => vscode.postMessage({command:'retry'}));"
    ].join('\n');
  return '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">' +
    '<meta http-equiv="Content-Security-Policy" content="' + escapeHtml(csp) + '">' +
    '<meta name="viewport" content="width=device-width, initial-scale=1">' +
    '<title>SpotAI-Review</title><style nonce="' + nonce + '">' +
    'html,body{margin:0;width:100%;height:100%;background:var(--vscode-editor-background);' +
    'color:var(--vscode-foreground);font-family:var(--vscode-font-family)}' +
    'iframe{width:100%;height:100%;border:0}main{padding:32px;line-height:1.6}' +
    'button{padding:9px 14px;margin-right:10px;background:var(--vscode-button-background);' +
    'color:var(--vscode-button-foreground);border:0;cursor:pointer}</style></head>' +
    '<body>' + body + '<script nonce="' + nonce + '">' + script + '</script></body></html>';
}

function refreshPanel(address, online, loading = false) {
  if (!panel) return;
  panelOnline = online;
  panel.webview.html = renderHtml(address, online, loading);
}

async function showPanel(context) {
  if (!panel) {
    panel = vscode.window.createWebviewPanel('spotaiReviewer', 'SpotAI Reviewer',
      vscode.ViewColumn.Beside, {
        enableScripts: true, retainContextWhenHidden: true, localResourceRoots: []
      });
    panel.webview.onDidReceiveMessage(async message => {
      if (!message || typeof message.command !== 'string') return;
      if (message.command === 'startServer' || message.command === 'retry') {
        await showPanel(context);
      }
    }, undefined, context.subscriptions);
    panel.onDidDispose(() => {
      panel = undefined;
      panelOnline = false;
    }, undefined, context.subscriptions);
  } else {
    panel.reveal(vscode.ViewColumn.Beside);
  }
  if (panelOnline && currentUrl && await checkHealth(currentUrl)) return panel;
  if (!panelStartupPromise) {
    refreshPanel(undefined, false, true);
    panelStartupPromise = launchBackend(context).then(address => {
      currentUrl = address;
      refreshPanel(address, true);
    }).catch(error => {
      refreshPanel(undefined, false);
      vscode.window.showErrorMessage(error.message);
    }).finally(() => { panelStartupPromise = undefined; });
  }
  await panelStartupPromise;
  return panel;
}

function languageOf(document) {
  if (document.languageId === 'python' || document.fileName.toLowerCase().endsWith('.py')) return 'python';
  if (document.languageId === 'java' || document.fileName.toLowerCase().endsWith('.java')) return 'java';
  return undefined;
}

async function review(context, selected) {
  try {
    output.appendLine('Review invoked, selected=' + selected + ', editor=' +
      (vscode.window.activeTextEditor?.document.fileName || lastCodeEditor?.document.fileName || 'none'));
    const editor = vscode.window.activeTextEditor || lastCodeEditor;
    if (!editor) { vscode.window.showWarningMessage('Open a Java or Python file.'); return; }
    const language = languageOf(editor.document);
    if (!language) { vscode.window.showWarningMessage('Only Python and Java are supported.'); return; }
    const code = editor.document.getText(selected ? editor.selection : undefined);
    if (!code.trim()) { vscode.window.showWarningMessage('Select code to review.'); return; }
    if (Buffer.byteLength(code, 'utf8') > 1024 * 1024) {
      vscode.window.showWarningMessage('Code exceeds the 1 MB snippet limit.');
      return;
    }
    const current = showAnalysisPanel(context, editor.document, editor.viewColumn);
    output.appendLine('Review results panel created');
    const requestId = ++analysisRequestId;
    const fileName = path.basename(editor.document.fileName);
    const firstLine = selected ? editor.selection.start.line + 1 : 1;
    current.webview.html = analysisHtml('SpotAI Code Review',
      '<header><h1>SpotAI Code Review</h1><div class="muted">' + escapeHtml(fileName) +
      '</div></header><div class="notice" role="status">Analyzing code…</div>');
    try {
      const address = await launchBackend(context);
      const result = await analyzeCode(address, language, code);
      output.appendLine('Analysis completed: ' + result.status +
        ', issues=' + (Array.isArray(result.issues) ? result.issues.length : 0));
      if (analysisPanel === current && requestId === analysisRequestId) {
        current.webview.html = renderAnalysis(result, fileName, selected, firstLine);
      }
    } catch (error) {
      if (analysisPanel === current && requestId === analysisRequestId) {
        current.webview.html = analysisHtml('SpotAI Code Review',
          '<header><h1>SpotAI Code Review</h1></header><div class="notice" role="alert">' +
          '<strong>Analysis failed</strong><p>' + escapeHtml(error.message) + '</p></div>');
        output.appendLine('Analysis failed: ' + error.message);
        vscode.window.showErrorMessage('SpotAI analysis failed: ' + error.message);
      }
    }
  } catch (error) {
    output.appendLine('Review command failed: ' + (error.stack || error.message));
    vscode.window.showErrorMessage(error.message);
  }
}

function activate(context) {
  output = vscode.window.createOutputChannel('SpotAI Backend');
  context.subscriptions.push(output);
  lastCodeEditor = vscode.window.activeTextEditor;
  context.subscriptions.push(vscode.window.onDidChangeActiveTextEditor(editor => {
    if (editor && languageOf(editor.document)) lastCodeEditor = editor;
  }));
  context.subscriptions.push(vscode.commands.registerCommand('spotai.openDashboard', async () => {
    try { await showPanel(context); } catch (error) { vscode.window.showErrorMessage(error.message); }
  }));
  context.subscriptions.push(vscode.commands.registerCommand('spotai.reviewSelection', () => review(context, true)));
  context.subscriptions.push(vscode.commands.registerCommand('spotai.reviewCurrentFile', () => review(context, false)));
  context.subscriptions.push(vscode.commands.registerCommand('spotai.startServer', async () => {
    try {
      const address = await launchBackend(context);
      currentUrl = address;
      vscode.window.showInformationMessage('SpotAI backend is running.');
      if (panel && !panelOnline) refreshPanel(address, true);
    } catch (error) { vscode.window.showErrorMessage(error.message); }
  }));
}

function deactivate() {
  if (backend && backend.exitCode === null) backend.kill();
  if (panel) panel.dispose();
  if (analysisPanel) analysisPanel.dispose();
}

module.exports = { activate, deactivate };
