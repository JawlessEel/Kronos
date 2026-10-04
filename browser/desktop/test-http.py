"""Probe a running desktop launcher without starting browsers or installing software."""
import hashlib
import http.client
import json
import sys

port = int(sys.argv[1])

def request(path, method='GET', host=None):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=15)
    conn.putrequest(method, path, skip_host=True)
    conn.putheader('Host', host or f'127.0.0.1:{port}')
    conn.endheaders()
    response = conn.getresponse()
    body = response.read()
    headers = dict(response.getheaders())
    status = response.status
    conn.close()
    return status, headers, body

checks = 0
status, headers, body = request('/health')
assert status == 200 and json.loads(body)['app'] == 'kronos-webgpu-desktop'
checks += 1
status, headers, body = request('/')
assert status == 200 and b'wb' in body and b'src/tradingview-bridge.js' in body
assert headers['Content-Type'].startswith('text/html')
checks += 1
status, headers, body = request('/src/kronos-local/kronos-engine.js')
assert status == 200 and headers['Content-Type'].startswith('application/javascript')
checks += 1
status, headers, body = request('/src/kronos-local/manifest.json')
assert status == 200
manifest = json.loads(body)
for file in manifest['models'][0]['files']:
    status, headers, body = request('/src/kronos-local/' + file['url'].removeprefix('./'))
    assert status == 200 and len(body) == file['bytes']
    assert hashlib.sha256(body).hexdigest() == file['sha256']
    checks += 1
status, headers, body = request('/chrome-bridge/extension/manifest.json')
assert status == 200 and json.loads(body)['manifest_version'] == 3
checks += 1
status, headers, body = request('/src/kronos-local/models/predictor-s1.onnx', 'HEAD')
assert status == 200 and int(headers['Content-Length']) == 14442515 and not body
checks += 1
for path in ['/../outside.txt', '/%2e%2e/outside.txt', '/missing.js']:
    assert request(path)[0] == 404
    checks += 1
assert request('/', 'POST')[0] == 405
checks += 1
assert request('/', host='untrusted.example')[0] == 400
checks += 1
print(json.dumps({'passed': checks, 'port': port, 'modelsVerified': 4}))
