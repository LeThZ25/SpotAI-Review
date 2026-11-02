const vscode = require('vscode');
const http = require('http');
const https = require('https');
const url = require('url');

let currentPanel = undefined;
let serverTerminal = undefined;

/**
 * Checks if the SpotAI backend server is responsive.
 * @param {string} serverUrl
 * @returns {Promise<boolean>}
 */
function checkServerHealth(serverUrl) {
  return new Promise((resolve) => {
    try {
      const parsed = url.parse(`${serverUrl.replace(/\/$/, '')}/api/health`);
      const client = parsed.protocol === 'https:' ? https : http;
      const req = client.get(parsed, { timeout: 1500 }, (res) => {
        resolve(res.statusCode === 200);
      });
      req.on('error', () => resolve(false));
      req.on('timeout', () => {
        req.destroy();
        resolve(false);
      });
    } catch (e) {
      resolve(false);
    }
  });
}

/**
 * Starts the local SpotAI backend server in a dedicated terminal.
 */
function startLocalBackend(context) {
  const config = vscode.workspace.getConfiguration('spotai');
  const pythonPath = config.get('pythonPath') || 'python';

  if (!serverTerminal || serverTerminal.exitStatus !== undefined) {
    serverTerminal = vscode.window.createTerminal({
      name: 'SpotAI Server',
      hideFromUser: false,
    });
  }

  serverTerminal.show(true);
  const workspaceFolders = vscode.workspace.workspaceFolders;
  const cwd = workspaceFolders && workspaceFolders.length > 0 ? workspaceFolders[0].uri.fsPath : '';
  if (cwd) {
    serverTerminal.sendText(`cd "${cwd}"`);
  }
  serverTerminal.sendText(`${pythonPath} spotai_cli.py --web`);
  vscode.window.showInformationMessage('Starting SpotAI Web Server on http://localhost:8000...');
}

/**
 * Generates the HTML content for the Webview panel.
 * @param {string} serverUrl
 * @param {boolean} isServerOnline
 * @returns {string}
 */
function getWebviewContent(serverUrl, isServerOnline) {
  const normalizedUrl = serverUrl.replace(/\/$/, '');

  if (isServerOnline) {
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy" content="default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; frame-src * blob: data: http: https:; connect-src *;">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SpotAI-Review</title>
  <style>
    body, html {
      margin: 0;
      padding: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background-color: var(--vscode-editor-background, #0f172a);
    }
    iframe {
      width: 100%;
      height: 100%;
      border: none;
    }
  </style>
</head>
<body>
  <iframe id="spotai-frame" src="${normalizedUrl}/"></iframe>
  <script>
    const vscode = acquireVsCodeApi();
    const iframe = document.getElementById('spotai-frame');

    // Forward messages from VS Code extension to the Web UI inside iframe
    window.addEventListener('message', event => {
      const message = event.data;
      if (iframe && iframe.contentWindow) {
        iframe.contentWindow.postMessage(message, '*');
      }
    });
  </script>
</body>
</html>`;
  }

  // Fallback offline / startup screen
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SpotAI-Review Server Offline</title>
  <style>
    body {
      font-family: var(--vscode-font-family, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif);
      background-color: var(--vscode-editor-background, #0b0f19);
      color: var(--vscode-editor-foreground, #e2e8f0);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 80vh;
      padding: 24px;
      text-align: center;
    }
    .card {
      background: var(--vscode-sideBar-background, #161e2e);
      border: 1px solid var(--vscode-panel-border, #2d3748);
      border-radius: 12px;
      padding: 32px;
      max-width: 520px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.3);
    }
    h2 {
      margin-top: 0;
      color: #38bdf8;
      font-size: 1.4rem;
    }
    p {
      color: var(--vscode-descriptionForeground, #94a3b8);
      font-size: 0.95rem;
      line-height: 1.6;
    }
    .btn {
      background-color: #3b82f6;
      color: #ffffff;
      border: none;
      padding: 10px 20px;
      border-radius: 6px;
      font-weight: 600;
      cursor: pointer;
      margin: 8px;
      font-size: 0.9rem;
      transition: background 0.2s;
    }
    .btn:hover {
      background-color: #2563eb;
    }
    .btn-secondary {
      background-color: transparent;
      border: 1px solid #475569;
      color: #e2e8f0;
    }
    .btn-secondary:hover {
      background-color: #1e293b;
    }
    code {
      background: #0f172a;
      padding: 2px 6px;
      border-radius: 4px;
      font-family: monospace;
      color: #f59e0b;
    }
  </style>
</head>
<body>
  <div class="card">
    <h2>🔌 SpotAI Server is Not Running</h2>
    <p>The SpotAI review backend at <code>${normalizedUrl}</code> is currently unreachable.</p>
    <p>Please launch the FastAPI backend server using the button below or by running <code>python spotai_cli.py --web</code> in your terminal.</p>
    <div style="margin-top: 24px;">
      <button class="btn" onclick="startServer()">🚀 Start Local Backend Server</button>
      <button class="btn btn-secondary" onclick="retryConnection()">🔄 Retry Connection</button>
    </div>
  </div>
  <script>
    const vscode = acquireVsCodeApi();
    function startServer() {
      vscode.postMessage({ command: 'startServer' });
    }
    function retryConnection() {
      vscode.postMessage({ command: 'retry' });
    }
  </script>
</body>
</html>`;
}

/**
 * Creates or reveals the SpotAI Webview panel.
 * @param {vscode.ExtensionContext} context
 * @returns {Promise<vscode.WebviewPanel>}
 */
async function showWebviewPanel(context) {
  const config = vscode.workspace.getConfiguration('spotai');
  const serverUrl = config.get('serverUrl') || 'http://127.0.0.1:8000';

  if (currentPanel) {
    currentPanel.reveal(vscode.ViewColumn.Beside);
    return currentPanel;
  }

  const isOnline = await checkServerHealth(serverUrl);

  currentPanel = vscode.window.createWebviewPanel(
    'spotaiReviewer',
    'SpotAI Reviewer',
    vscode.ViewColumn.Beside,
    {
      enableScripts: true,
      retainContextWhenHidden: true,
      localResourceRoots: []
    }
  );

  currentPanel.webview.html = getWebviewContent(serverUrl, isOnline);

  currentPanel.webview.onDidReceiveMessage(
    async (message) => {
      if (message.command === 'startServer') {
        startLocalBackend(context);
        // Wait 3 seconds and retry
        setTimeout(async () => {
          const ok = await checkServerHealth(serverUrl);
          if (currentPanel) {
            currentPanel.webview.html = getWebviewContent(serverUrl, ok);
          }
        }, 3500);
      } else if (message.command === 'retry') {
        const ok = await checkServerHealth(serverUrl);
        if (currentPanel) {
          currentPanel.webview.html = getWebviewContent(serverUrl, ok);
        }
      }
    },
    undefined,
    context.subscriptions
  );

  currentPanel.onDidDispose(() => {
    currentPanel = undefined;
  }, null, context.subscriptions);

  return currentPanel;
}

/**
 * Extension activation entry point.
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
  // Command 1: Open Dashboard
  const openCmd = vscode.commands.registerCommand('spotai.openDashboard', async () => {
    await showWebviewPanel(context);
  });

  // Command 2: Review Selected Code Snippet
  const reviewSnippetCmd = vscode.commands.registerCommand('spotai.reviewSelection', async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage('No active editor found.');
      return;
    }

    const selection = editor.selection;
    const text = editor.document.getText(selection).trim();

    if (!text) {
      vscode.window.showInformationMessage('Please highlight a Java or Python code snippet first.');
      return;
    }

    const langId = editor.document.languageId;
    let language = 'java';
    if (langId === 'python' || editor.document.fileName.endsWith('.py')) {
      language = 'python';
    } else if (langId === 'java' || editor.document.fileName.endsWith('.java')) {
      language = 'java';
    } else {
      vscode.window.showWarningMessage(`SpotAI-Review supports Java and Python. Detected: ${langId}`);
      return;
    }

    const panel = await showWebviewPanel(context);
    // Send snippet payload to Webview
    setTimeout(() => {
      panel.webview.postMessage({
        command: 'loadSnippet',
        code: text,
        language: language
      });
    }, 400);
  });

  // Command 3: Review Entire Current File
  const reviewFileCmd = vscode.commands.registerCommand('spotai.reviewCurrentFile', async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage('No active editor found.');
      return;
    }

    const doc = editor.document;
    const text = doc.getText();
    const fileName = doc.fileName;

    let language = 'java';
    if (doc.languageId === 'python' || fileName.endsWith('.py')) {
      language = 'python';
    } else if (doc.languageId === 'java' || fileName.endsWith('.java')) {
      language = 'java';
    } else {
      vscode.window.showWarningMessage('SpotAI-Review supports Java (.java) and Python (.py) files only.');
      return;
    }

    const panel = await showWebviewPanel(context);
    setTimeout(() => {
      panel.webview.postMessage({
        command: 'loadSnippet',
        code: text,
        language: language
      });
    }, 400);
  });

  // Command 4: Start Server
  const startServerCmd = vscode.commands.registerCommand('spotai.startServer', () => {
    startLocalBackend(context);
  });

  context.subscriptions.push(openCmd, reviewSnippetCmd, reviewFileCmd, startServerCmd);
}

function deactivate() {
  if (currentPanel) {
    currentPanel.dispose();
  }
}

module.exports = {
  activate,
  deactivate
};

