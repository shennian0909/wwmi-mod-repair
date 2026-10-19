"""Install/update the skill; preserve replaced files in a separate backup tree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

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
    """Create the selected snapshot, or reuse an identical one without overwriting."""
    check_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('xb') as stream:
            stream.write(expected)
    except FileExistsError:
        pass
    if path.read_bytes() != expected:
        raise OSError(f'Backup verification failed: {path}')
    return path


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
    backup_directory = destination.parent / f'.{destination.name}-backups'
    if source.is_relative_to(backup_directory) or backup_directory.is_relative_to(source):
        raise ValueError('Source and backup directories must not overlap.')
    entries = []
    for relative in skill_files(source):
        target = destination / relative
        check_target(target)
        incoming = (source / relative).read_bytes()
        previous = target.read_bytes() if target.exists() else None
        action = 'unchanged' if previous == incoming else 'update' if previous is not None else 'create'
        saved = None
        if action == 'update':
            digest = hashlib.sha256(previous).hexdigest()
            saved = backup_directory / digest / relative
            check_target(saved)
            if saved.exists() and saved.read_bytes() != previous:
                raise OSError(f'Backup verification failed: {saved}')
        entries.append((relative, target, incoming, previous, action, saved))
    result = []
    for relative, target, incoming, previous, action, saved in entries:
        record = {'file': relative.as_posix(), 'action': action}
        if action != 'unchanged' and not dry_run:
            check_target(target)
            current = target.read_bytes() if target.exists() else None
            if current != previous:
                raise ValueError(f'Destination changed after inspection: {relative}')
            target.parent.mkdir(parents=True, exist_ok=True)
            if previous is not None:
                record['backup'] = str(backup(saved, previous))
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
    return {'destination': str(destination), 'backup_directory': str(backup_directory),
            'dry_run': dry_run, 'files': result}


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
