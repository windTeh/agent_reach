import subprocess, json, sys

NODE = r'C:/Users/zhengjingyi/.workbuddy/binaries/node/versions/22.22.2/node.exe'
MAIN = r'C:/Users/zhengjingyi/.workbuddy/binaries/node/versions/22.22.2/node_modules/@jackwener/opencli/dist/src/main.js'
TAB = '5272A8D8CDC2281D97F2DBCDD75E351B'

def ev(js):
    r = subprocess.run([NODE, MAIN, 'browser', 'dqg7tk9s', 'eval', js, '--tab', TAB],
                       capture_output=True, text=True, encoding='utf-8', timeout=90)
    out = r.stdout.strip()
    i = out.find('Update available')
    if i > 0: out = out[:i].strip()
    return out

js = "(function(){return JSON.stringify({len:(window.__fullResp2||'').length});})()"
d = json.loads(ev(js))
total = d['len']
print('total len:', total)

chunk = 50000
parts = []
for i in range((total + chunk - 1) // chunk):
    js = "(function(){var r=window.__fullResp2||'';var s=r.slice(%d,%d);return JSON.stringify({ok:1,c:s});})()" % (i*chunk, (i+1)*chunk)
    out = ev(js)
    try:
        d = json.loads(out)
        parts.append(d['c'])
    except Exception as e:
        print('chunk', i, 'ERR', str(e), out[:150]); sys.exit(1)
    if i % 10 == 0: print('chunk', i, 'done', flush=True)

full = ''.join(parts)
with open('fb_20rows_full2.json', 'w', encoding='utf-8') as f:
    f.write(full)
print('saved, len:', len(full))
