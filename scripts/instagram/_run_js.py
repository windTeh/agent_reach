# -*- coding: utf-8 -*-
"""通过 opencli 在浏览器中执行 JS 文件并输出结果。"""
import subprocess, sys, os

NODE = r"C:\Users\zhengjingyi\.workbuddy\binaries\node\versions\22.22.2-2\node.exe"
OPENCLI_JS = r"E:\CCProject\agent_reach\.opencli-tmp\node_modules\@jackwener\opencli\dist\src\main.js"
SESSION = sys.argv[1]  # browser session id
JS_FILE = sys.argv[2]  # path to JS file

with open(JS_FILE, encoding='utf-8') as f:
    js_code = f.read().strip()

result = subprocess.run(
    [NODE, OPENCLI_JS, 'browser', SESSION, 'eval', js_code],
    capture_output=True, timeout=60, encoding='utf-8', errors='replace'
)
# Write to stdout with utf-8 to avoid GBK encoding issues on Windows
sys.stdout.buffer.write(result.stdout.encode('utf-8', errors='replace'))
sys.stdout.buffer.write(b'\n')
if result.stderr:
    sys.stderr.buffer.write(result.stderr.encode('utf-8', errors='replace'))
    sys.stderr.buffer.write(b'\n')
