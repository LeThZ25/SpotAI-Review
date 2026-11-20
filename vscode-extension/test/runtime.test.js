const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const vm = require('node:vm');
const { EventEmitter } = require('node:events');

function harness(initialOnline, apiResponse) {
  const commands = new Map();
  const requests = [];
  const errors = [];
  const spawns = [];
  const navigations = [];
  const panels = new Map();
  const handlers = new Map();
  let activeEditor;
  let online = initialOnline;
  const root = path.resolve(__dirname, '../..');
  const code = fs.readFileSync(path.resolve(__dirname, '../extension.js'), 'utf8');
  const config = {
    serverUrl: initialOnline ? 'http://127.0.0.1:8000' : ''
  };
  const vscode = {
    ViewColumn: { Beside: 2 },
    Position: class { constructor(line, character) { this.line = line; this.character = character; } },
    Range: class { constructor(start, end) { this.start = start; this.end = end; } },
    workspace: {
      workspaceFolders: [{ uri: { fsPath: 'C:\\another-project' } }],
      getConfiguration: () => ({ get: (key, defaultValue) => config[key] ?? defaultValue })
    },
    window: {
      onDidChangeActiveTextEditor: () => ({ dispose() {} }),
      activeTextEditor: {
        selection: { start: { line: 5 }, end: { line: 7 } },
        viewColumn: 1,
        document: {
          languageId: 'python',
          fileName: 'C:\\another-project\\example.py',
          lineCount: 20,
          getText: selection => selection ? 'def x():\n  pass' : 'def complete():\n  return 3'
        }
      },
      createOutputChannel: () => ({ append() {}, appendLine() {}, show() {}, dispose() {} }),
      createWebviewPanel: kind => {
        const panel = {
          webview: {
            html: '',
            onDidReceiveMessage: handler => { handlers.set(kind, handler); },
            postMessage: async () => true
          },
          reveal() {},
          onDidDispose() {},
          dispose() {}
        };
        panels.set(kind, panel);
        return panel;
      },
      showTextDocument: async (_document, options) => { navigations.push(options); },
      showErrorMessage: text => errors.push(text),
      showWarningMessage: text => errors.push(text),
      showInformationMessage() {}
    },
    commands: { registerCommand: (name, fn) => {
      commands.set(name, fn);
      return { dispose() {} };
    }}
  };
  const mockHttp = {
    get(address, options, callback) {
      const request = new EventEmitter();
      request.destroy = () => request.emit('error', new Error('timeout'));
      setImmediate(() => {
        if (online) callback({ statusCode: 200, resume() {} });
        else request.emit('error', new Error('offline'));
      });
      return request;
    },
    request(_address, options, callback) {
      const request = new EventEmitter();
      request.end = body => {
        requests.push({ options, body: JSON.parse(body) });
        setImmediate(() => {
          const response = new EventEmitter();
          response.statusCode = apiResponse && apiResponse.httpStatus || 200;
          callback(response);
          response.emit('data', Buffer.from(JSON.stringify(apiResponse && apiResponse.data || {
            status: 'success',
            summary: { issues_count: 1, total_loc: 5, max_cc: 12, average_cc: 6,
              average_mi: 60, quality_gate_passed: false },
            issues: [{ severity: 'HIGH', type: 'Complex Method',
              message: '<img src=x onerror=alert(1)>', start_line: 3,
              code_snippet: '<script>alert(1)</script>', ai_provider: 'Offline fallback',
              ai_explanation: 'Split the function.', ai_refactored_code: 'def safe():\n    pass' }],
            metrics: [{ method_name: 'foo', cyclomatic_complexity: 12,
              cognitive_complexity: 10, maintainability_index: 60 }]
          })));
          response.emit('end');
        });
      };
      request.destroy = error => request.emit('error', error);
      return request;
    }
  };
  const fakeSpawn = (executable, args, options) => {
    spawns.push({ executable, args, options });
    online = true;
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.exitCode = null;
    child.kill = () => { child.exitCode = 0; };
    return child;
  };
  const mockFs = {
    ...fs,
    existsSync: filename => String(filename).endsWith('spotai_backend.exe') || fs.existsSync(filename),
    mkdirSync: () => undefined
  };
  const mockNet = {
    createServer: () => {
      const server = new EventEmitter();
      server.listen = (_port, _host, callback) => setImmediate(callback);
      server.address = () => ({ port: 53081 });
      server.close = callback => callback();
      return server;
    }
  };
  const runtimeModule = { exports: {} };
  const nativeRequire = value => {
    if (value === 'vscode') return vscode;
    if (value === 'http' || value === 'https') return mockHttp;
    if (value === 'child_process') return { spawn: fakeSpawn };
    if (value === 'fs') return mockFs;
    if (value === 'net') return mockNet;
    return require(value);
  };
  vm.runInNewContext(code, {
    require: nativeRequire, module: runtimeModule,
    process, Buffer, URL, setTimeout
  }, { filename: 'extension.js' });
  const context = {
    extensionPath: path.resolve(root, 'vscode-extension'),
    globalStorageUri: { fsPath: 'C:\\spotai-storage' },
    subscriptions: []
  };
  runtimeModule.exports.activate(context);
  activeEditor = vscode.window.activeTextEditor;
  return { commands, requests, errors, spawns, navigations, context,
    getPanel: kind => panels.get(kind),
    setEditorFocused: focused => { vscode.window.activeTextEditor = focused ? activeEditor : undefined; },
    receive: (kind, message) => handlers.get(kind)(message),
    deactivate: runtimeModule.exports.deactivate };
}

async function tests() {
  const started = harness(true);
  assert.deepEqual([...started.commands.keys()].sort(), [
    'spotai.openDashboard', 'spotai.reviewCurrentFile',
    'spotai.reviewSelection', 'spotai.startServer'
  ].sort());
  await started.commands.get('spotai.openDashboard')();
  const html = started.getPanel('spotaiReviewer').webview.html;
  assert.match(html, /default-src &#39;none&#39;/);
  assert.doesNotMatch(html, /unsafe-inline|unsafe-eval|postMessage\(message, '\*'\)/);
  await started.commands.get('spotai.reviewSelection')();
  assert.equal(started.requests.at(-1).body.language, 'python');
  assert.equal(started.requests.at(-1).body.code, 'def x():\n  pass');
  assert.equal(started.requests.at(-1).options.method, 'POST');
  const analysisHtml = started.getPanel('spotaiAnalysis').webview.html;
  assert.match(analysisHtml, /Complex Method/);
  assert.match(analysisHtml, /Quality Gate.*FAIL/);
  assert.match(analysisHtml, /Offline fallback/);
  assert.match(analysisHtml, /Go to line 8/);
  assert.match(analysisHtml, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.doesNotMatch(analysisHtml, /<img src=x|<script>alert\(1\)<\/script>/);
  await started.receive('spotaiAnalysis', { command: 'revealIssue', line: 8 });
  assert.equal(started.navigations.at(-1).selection.start.line, 7);
  started.setEditorFocused(false);
  await started.commands.get('spotai.reviewCurrentFile')();
  assert.match(started.requests.at(-1).body.code, /complete/);
  assert.match(started.getPanel('spotaiAnalysis').webview.html, /Go to line 3/);
  assert.equal(started.spawns.length, 0);
  started.deactivate();

  const offline = harness(false);
  await offline.commands.get('spotai.openDashboard')();
  assert.match(offline.getPanel('spotaiReviewer').webview.html, /spotai-frame/);
  assert.equal(offline.spawns.length, 1, 'Dashboard should automatically start the backend');
  await offline.commands.get('spotai.reviewSelection')();
  assert.equal(offline.spawns.length, 1);
  assert.equal(offline.spawns[0].options.shell, false);
  assert.equal(offline.spawns[0].options.cwd, 'C:\\spotai-storage');
  assert.match(offline.spawns[0].executable, /backend[\\/]spotai_backend[\\/]spotai_backend\.exe$/);
  assert.deepEqual(Array.from(offline.spawns[0].args), ['--web', '--host', '127.0.0.1', '--port', '53081']);
  assert.equal(offline.spawns[0].options.env.SPOTAI_DATA_ROOT, 'C:\\spotai-storage');
  assert.match(offline.spawns[0].options.env.SPOTAI_ALLOWED_ROOTS, /another-project/);
  assert.match(offline.getPanel('spotaiAnalysis').webview.html, /Complex Method/);
  assert.equal(offline.errors.length, 0, offline.errors.join('\n'));
  offline.deactivate();

  const syntaxError = harness(true, { data: { status: 'syntax_error',
    message: 'Python SyntaxError at line 2', line: 2 } });
  await syntaxError.commands.get('spotai.reviewCurrentFile')();
  assert.match(syntaxError.getPanel('spotaiAnalysis').webview.html, /Python SyntaxError at line 2/);
  assert.doesNotMatch(syntaxError.getPanel('spotaiAnalysis').webview.html, /Quality Gate.*PASS/);
  syntaxError.deactivate();

  const apiFailure = harness(true, { httpStatus: 413, data: { detail: 'Snippet exceeds 1 MB.' } });
  await apiFailure.commands.get('spotai.reviewCurrentFile')();
  assert.match(apiFailure.getPanel('spotaiAnalysis').webview.html, /Analysis failed/);
  assert.match(apiFailure.errors.at(-1), /Snippet exceeds 1 MB/);
  apiFailure.deactivate();
  console.log('Extension tests: direct analysis API, rendered findings, XSS escaping, syntax/API errors, navigation, backend auto-launch: PASS');
}

tests().catch(error => { console.error(error); process.exitCode = 1; });
