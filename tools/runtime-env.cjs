const path = require('node:path');
const fs = require('node:fs');
module.exports = function configureWorkspaceRuntime() {
  const root = path.resolve(__dirname, '..');
  const temporary = path.join(root, '.research-cache', 'tmp');
  fs.mkdirSync(temporary, { recursive: true });
  process.env.TEMP = temporary;
  process.env.TMP = temporary;
  process.env.electron_config_cache = path.join(root, '.research-cache', 'electron-download');
  delete process.env.ELECTRON_RUN_AS_NODE;
  return root;
};
