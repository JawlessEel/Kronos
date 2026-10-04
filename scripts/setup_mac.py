"""Install the project environment on macOS; never changes global Python."""
import argparse
import platform
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download-models', action='store_true')
    args = parser.parse_args()
    if platform.system() != 'Darwin':
        parser.error('This installer is for macOS. Use WINDOWS-QUICKSTART.md on Windows.')
    if not (3, 10) <= sys.version_info[:2] <= (3, 12):
        parser.error('Use Python 3.10–3.12; Python 3.12 is recommended for the pinned dependencies.')
    if platform.machine() != 'arm64':
        parser.error('This pinned setup targets Apple Silicon. Use native arm64 Python, not Rosetta.')
    env = ROOT / '.venv'
    python = env / 'bin' / 'python'
    if env.exists() and not python.exists():
        parser.error('Existing .venv is not a macOS environment. Keep it on Windows; clone a fresh checkout on the Mac.')
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(env)
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements-macos.txt')], check=True)
    if args.download_models:
        subprocess.run([str(python), str(ROOT / 'scripts' / 'download_models.py')], check=True)
    print('Environment ready. Put your private Polygon key in .env, then run bash Start-Kronos.sh.')


if __name__ == '__main__':
    main()
