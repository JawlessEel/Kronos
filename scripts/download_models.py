"""Download matching official model/tokenizer files into the ignored models directory."""
from pathlib import Path
from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parents[1]


def main():
    for name in ('Kronos-mini', 'Kronos-small', 'Kronos-base', 'Kronos-Tokenizer-2k', 'Kronos-Tokenizer-base'):
        snapshot_download(repo_id=f'NeoQuasar/{name}', local_dir=ROOT / 'models' / name,
                          allow_patterns=['config.json', 'model.safetensors'])
        print(f'Ready: {name}')


if __name__ == '__main__':
    main()
