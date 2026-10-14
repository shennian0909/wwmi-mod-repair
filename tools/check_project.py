"""Validate skill metadata, links, Python, workflow YAML and publication scope."""
import ast
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

import yaml

from _project import ROOT, SKILL_NAME, skill_files, version

EXCLUDED_DIRS = {'.git', '__pycache__', 'dist', 'work', 'outputs', '.venv', 'venv'}
PRIVATE_SUFFIXES = {'.bak', '.before', '.dds', '.buf', '.ini', '.log', '.pyc'}


def project_files(root):
    if (root / '.git').exists():
        result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'],
                                capture_output=True, check=True)
        tracked = result.stdout.decode('utf-8').split('\0')
        return [Path(p) for p in tracked if p]
    return sorted(p.relative_to(root) for p in root.rglob('*') if p.is_file()
                  and not any(part in EXCLUDED_DIRS for part in p.relative_to(root).parts)
                  and p.suffix.lower() not in {'.bak', '.pyc'})


def check(root=ROOT):
    errors = []
    release_version = version(root)
    runtime = skill_files(root)
    text = (root / 'SKILL.md').read_text(encoding='utf-8-sig')
    match = re.match(r'^---\s*\n(.*?)\n---(?:\s*\n|$)', text, re.S)
    metadata = yaml.safe_load(match[1]) if match else None
    if not isinstance(metadata, dict) or metadata.get('name') != SKILL_NAME:
        errors.append('SKILL.md needs YAML frontmatter with the expected name.')
    if not isinstance(metadata, dict) or not isinstance(metadata.get('description'), str) or not metadata['description'].strip():
        errors.append('SKILL.md needs a nonempty description.')
    ui = yaml.safe_load((root / 'agents/openai.yaml').read_text(encoding='utf-8'))
    interface = ui.get('interface', {}) if isinstance(ui, dict) else {}
    short = interface.get('short_description', '')
    if not isinstance(short, str) or not 25 <= len(short) <= 64:
        errors.append('UI short_description must contain 25-64 characters.')
    if '$' + SKILL_NAME not in interface.get('default_prompt', ''):
        errors.append('UI default_prompt must invoke this skill.')
    changelog = (root / 'CHANGELOG.md').read_text(encoding='utf-8')
    if not re.search(r'^##\s+\[?' + re.escape(release_version) + r'\]?(?=\s|$)', changelog, re.M):
        errors.append('CHANGELOG.md must describe VERSION.')
    files = project_files(root)
    token_pattern = re.compile(r'\b(?:' + 'gh' + r'[pousr]_[A-Za-z0-9]{30,}|' + 'github' + r'_pat_[A-Za-z0-9_]{30,})\b')
    for relative in files:
        if (relative.suffix.lower() in PRIVATE_SUFFIXES
                or any(p in EXCLUDED_DIRS or p.startswith('FrameAnalysis-') for p in relative.parts)
                or relative.name.startswith('.env') or relative.name == '.JASM_ModConfig.json'):
            errors.append(f'Private/generated resource is included: {relative}')
            continue
        path = root / relative
        if not path.is_file():
            errors.append(f'Tracked file is missing: {relative}')
            continue
        try:
            content = path.read_text(encoding='utf-8-sig')
        except UnicodeError:
            errors.append(f'Public source must be UTF-8 text: {relative}')
            continue
        if re.search(r'\b[A-Za-z]:[\\/]', content) or token_pattern.search(content):
            errors.append(f'Possible personal absolute path or credential: {relative}')
        if path.suffix == '.py':
            try:
                ast.parse(content, filename=str(relative))
            except SyntaxError as error:
                errors.append(f'Invalid Python: {relative}: {error}')
        if path.suffix in {'.yml', '.yaml'}:
            try:
                parsed = yaml.safe_load(content)
                if not isinstance(parsed, dict):
                    errors.append(f'YAML must be a mapping: {relative}')
            except yaml.YAMLError as error:
                errors.append(f'Invalid YAML: {relative}: {error}')
        if path.suffix == '.md':
            for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', content):
                target = target.strip().split(' "', 1)[0].strip('<>')
                parts = urlsplit(target)
                if parts.scheme or parts.netloc or not parts.path:
                    continue
                resolved = (path.parent / unquote(parts.path)).resolve()
                if not resolved.is_relative_to(root.resolve()) or not resolved.exists():
                    errors.append(f'Broken local link in {relative}: {target}')
    if errors:
        raise ValueError('\n'.join(errors))
    return f'Project valid: v{release_version}, {len(files)} public files, {len(runtime)} runtime files.'


if __name__ == '__main__':
    try:
        print(check())
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f'Project validation failed:\n{error}', file=sys.stderr)
        sys.exit(1)
