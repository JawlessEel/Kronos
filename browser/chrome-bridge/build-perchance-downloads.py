"""Generate an additive Perchance panel with real extension/Pine downloads embedded."""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / 'extension/manifest.json').read_text(encoding='utf-8'))
    version = manifest['version']
    pine = (ROOT / 'extension/Kronos-Forecast-Bridge.pine').read_text(encoding='utf-8')
    guide = (ROOT / 'README.md').read_text(encoding='utf-8')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        files = [(p, 'extension/' + p.name) for p in sorted((ROOT / 'extension').iterdir()) if p.is_file()]
        files += [(ROOT / 'README.md', 'SETUP.md'), (ROOT.parent.parent / 'LICENSE', 'LICENSE')]
        for path, name in files:
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 4, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    payload = buffer.getvalue()
    sha = hashlib.sha256(payload).hexdigest()
    html = (ROOT / 'perchance-downloads.template.html').read_text(encoding='utf-8')
    replacements = {
        '__VERSION__': version, '__SHA__': sha,
        '__PINE_JSON__': json.dumps(pine), '__GUIDE_JSON__': json.dumps(guide),
        '__ZIP_JSON__': json.dumps(base64.b64encode(payload).decode('ascii')),
    }
    for key, value in replacements.items():
        html = html.replace(key, value)
    (output / 'Perchance-TradingView-Downloads-Panel.html').write_bytes(html.encode('utf-8'))
    (output / f'Kronos-TradingView-Extension-{version}.zip').write_bytes(payload)
    (output / 'Kronos-Forecast-Bridge.pine').write_bytes(pine.encode('utf-8'))
    (output / 'Kronos-TradingView-Setup.txt').write_bytes(guide.encode('utf-8'))
    print(f'Generated embedded panel and extension {version}; ZIP SHA-256 {sha}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    build(parser.parse_args().output)
