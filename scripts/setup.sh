#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if command -v python3.12 >/dev/null 2>&1; then
  report_python=python3.12
else
  report_python=python3
fi
"$report_python" -c 'import sys; assert sys.version_info >= (3,12), "Python 3.12+ required"'
chmod +x wxreport
command -v node >/dev/null
command -v npm >/dev/null
"$report_python" -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm ci --ignore-scripts
./node_modules/.bin/playwright install chromium
node <<'JS'
const fs=require('fs');
const {chromium}=require('playwright');
const config={node:process.execPath,playwright:require.resolve('playwright'),chromium:chromium.executablePath()};
fs.writeFileSync('runtime.local.json',JSON.stringify(config,null,2)+'\n',{mode:0o600});
console.log('Runtime ready. Run ./wxreport demo to verify offline HTML and PNG.');
JS
