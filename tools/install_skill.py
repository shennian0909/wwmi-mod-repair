"""Install/update the skill; preserve replaced files beside their originals."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

from _project import ROOT, SKILL_NAME, linked, skill_files


def default_destination():
    configured = os.environ.get('CODEX_HOME')
    base = Path(configured).expanduser() if configured else Path.home() / '.codex'
    return base / 'skills' / SKILL_NAME


def check_target(path):
    for component in [path, *path.parents]:
        if component.exists() or component.is_symlink():
            if linked(component):
                raise ValueError(f'Destination contains a link/reparse point: {component}')
    if path.exists() and not path.is_file():
        raise ValueError(f'Destination file is occupied by another object: {path}')


def backup(path, expected):
    """Use actual local time; a name collision must never replace a backup."""
    for _ in range(30):
        stamp = datetime.now().strftime('%Y-%m-%d %H-%M-%S')
        saved = path.with_name(f'{path.name} {stamp}.BAK')
        try:
            with saved.open('xb') as stream:
                stream.write(expected)
        except FileExistsError:
            time.sleep(0.1)
            continue
        if hashlib.sha256(saved.read_bytes()).digest() != hashlib.sha256(expected).digest():
            raise OSError(f'Backup verification failed: {saved}')
        return saved
    raise FileExistsError('Could not create a unique backup with the current local time.')


def install(source, destination, dry_run=False):
    source = Path(source).absolute()
    destination = Path(destination).expanduser().absolute()
    # Check links before resolving; resolving would hide the redirected path.
    for component in [source, *source.parents]:
        if component.exists() and linked(component):
            raise ValueError('Source contains a link/reparse point.')
    source = source.resolve(strict=True)
    for component in [destination, *destination.parents]:
        if (component.exists() or component.is_symlink()) and linked(component):
            raise ValueError('Destination contains a link/reparse point.')
    destination = destination.resolve()
    if source.is_relative_to(destination) or destination.is_relative_to(source):
        raise ValueError('Source and destination must be separate, non-overlapping directories.')
    entries = []
    for relative in skill_files(source):
        target = destination / relative
        check_target(target)
        incoming = (source / relative).read_bytes()
        previous = target.read_bytes() if target.exists() else None
        action = 'unchanged' if previous == incoming else 'update' if previous is not None else 'create'
        entries.append((relative, target, incoming, previous, action))
    result = []
    for relative, target, incoming, previous, action in entries:
        record = {'file': relative.as_posix(), 'action': action}
        if action != 'unchanged' and not dry_run:
            check_target(target)
            current = target.read_bytes() if target.exists() else None
            if current != previous:
                raise ValueError(f'Destination changed after inspection: {relative}')
            target.parent.mkdir(parents=True, exist_ok=True)
            if previous is not None:
                record['backup'] = backup(target, previous).name
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.wwmi-install-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(incoming)
            try:
                if previous is not None:
                    temporary.chmod(target.stat().st_mode)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
            if target.read_bytes() != incoming:
                raise OSError(f'Installed bytes differ from the source: {relative}')
        result.append(record)
    return {'destination': str(destination), 'dry_run': dry_run, 'files': result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dest', type=Path, default=default_destination())
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(install(ROOT, args.dest, args.dry_run), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, f'Installation failed: {error}\n')


if __name__ == '__main__':
    main()
