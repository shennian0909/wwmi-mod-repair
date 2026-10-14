"""Build a deterministic runtime ZIP and SHA-256 integrity manifests."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

from _project import ROOT, SKILL_NAME, skill_files, version


def archive_bytes(root=ROOT):
    release_version = version(root)
    payload = {p.as_posix(): (root / p).read_bytes() for p in skill_files(root)}
    manifest = {'name': SKILL_NAME, 'version': release_version,
                'sha256': {p: hashlib.sha256(data).hexdigest() for p, data in payload.items()}}
    payload['MANIFEST.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(payload.items()):
            info = zipfile.ZipInfo(f'{SKILL_NAME}/{name}', date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compresslevel=9)
    return release_version, buffer.getvalue()


def write_new_or_identical(path, data):
    if path.exists():
        if path.read_bytes() != data:
            raise FileExistsError(f'Existing artifact differs; use a new output directory or release version: {path}')
        return
    with path.open('xb') as stream:
        stream.write(data)


def package(root, output, tag=None):
    release_version, data = archive_bytes(root)
    if tag is not None and tag != f'v{release_version}':
        raise ValueError('The release tag must exactly match v + VERSION.')
    filename = f'{SKILL_NAME}-{release_version}.zip'
    checksum = hashlib.sha256(data).hexdigest()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    # Check both artifacts before creating either, avoiding a partial collision.
    artifacts = {filename: data, 'SHA256SUMS.txt': f'{checksum}  {filename}\n'.encode('ascii')}
    for name, content in artifacts.items():
        if (output / name).exists() and (output / name).read_bytes() != content:
            raise FileExistsError(f'Existing artifact differs: {output / name}')
    for name, content in artifacts.items():
        write_new_or_identical(output / name, content)
    return {'version': release_version, 'archive': str(output / filename), 'sha256': checksum}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, default=ROOT / 'dist')
    parser.add_argument('--tag')
    args = parser.parse_args()
    try:
        print(json.dumps(package(ROOT, args.out_dir, args.tag), indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, f'Packaging failed: {error}\n')


if __name__ == '__main__':
    main()
