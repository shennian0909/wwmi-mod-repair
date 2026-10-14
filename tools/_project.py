"""Shared file selection for installing and exporting this skill."""
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = 'wwmi-mod-repair'


def linked(path):
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)


def version(root=ROOT):
    value = (root / 'VERSION').read_text(encoding='utf-8').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?', value):
        raise ValueError('VERSION must contain a semantic version, for example 0.1.0.')
    return value


def skill_files(root=ROOT):
    """Select runtime documents/scripts plus their license and version."""
    root = Path(root)
    if not root.is_dir() or linked(root):
        raise ValueError('The source must be a real project directory.')
    selected = [Path('SKILL.md'), Path('LICENSE'), Path('VERSION')]
    for folder, extensions in [('agents', {'.yaml', '.yml'}),
                               ('references', {'.md'}), ('scripts', {'.py'})]:
        base = root / folder
        if not base.is_dir() or linked(base):
            raise ValueError(f'Missing or linked runtime directory: {folder}')
        for current, dirs, files in os.walk(base, followlinks=False):
            dirs[:] = [d for d in dirs if d != '__pycache__']
            if any(linked(Path(current) / d) for d in dirs):
                raise ValueError('Runtime directories cannot contain links/reparse points.')
            for name in files:
                path = Path(current) / name
                if path.suffix.lower() in extensions:
                    if linked(path):
                        raise ValueError('Runtime files cannot be links/reparse points.')
                    selected.append(path.relative_to(root))
    for relative in selected:
        path = root / relative
        if not path.is_file() or linked(path):
            raise ValueError(f'Missing or linked runtime file: {relative}')
    return sorted(selected, key=lambda p: p.as_posix())
