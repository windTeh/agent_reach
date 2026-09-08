import subprocess, json, sys

NODE = r'C:/Users/zhengjingyi/.workbuddy/binaries/node/versions/22.22.2/node.exe'
MAIN = r'C:/Users/zhengjingyi/.workbuddy/binaries/node/versions/22.22.2/node_modules/@jackwener/opencli/dist/src/main.js'
TAB = '5272A8D8CDC2281D97F2DBCDD75E351B'

def ev(js):
    r = subprocess.run([NODE, MAIN, 'browser', 'dqg7tk9s', 'eval', js, '--tab', TAB],
                       capture_output=True, text=True, encoding='utf-8', timeout=60)
    out = r.stdout.strip()
    # strip trailing update notices
    i = out.find('Update available')
    if i > 0: out = out[:i].strip()
    return out

# chunk the response
chunk = 60000
for i in range(5):
    js = "(function(){var r=window.__tableResp||'';var s=r.slice(%d,%d);return JSON.stringify({ok:1,c:s});})()" % (i*chunk, (i+1)*chunk)
    out = ev(js)
    try:
        d = json.loads(out)
        content = d['c']
        with open('fb_table_resp_%d.json' % i, 'w', encoding='utf-8') as f:
            f.write(content)
        print('chunk', i, 'len', len(content))
    except Exception as e:
        print('chunk', i, 'ERR', str(e), out[:200])
        sys.exit(1)
print('DONE')
