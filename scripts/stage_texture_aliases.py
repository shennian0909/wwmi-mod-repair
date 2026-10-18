"""Stage evidence-backed, unambiguous texture aliases without editing a live mod."""
import argparse
import collections
import difflib
import hashlib
import json
from pathlib import Path
import re

SECTIONS = re.compile(r'^\[([^\]]+)\][^\r\n]*\r*\n(.*?)(?=^\[|\Z)', re.M | re.S)
HASH = re.compile(r'^([ \t]*hash[ \t]*=[ \t]*)([0-9a-f]{8})(?=[ \t;\r\n]|\Z)([^\r\n]*)(\r*)(?=\n|\Z)', re.M | re.I)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def filename_text(byte_preserving_value, raw):
    data = byte_preserving_value.encode('latin1')
    try:
        raw.decode('utf-8-sig')
        return data.decode('utf-8')
    except UnicodeDecodeError:
        try:
            return data.decode('mbcs')
        except (UnicodeDecodeError, LookupError):
            return byte_preserving_value


def parse(text):
    items = list(SECTIONS.finditer(text.removeprefix('\xef\xbb\xbf')))
    counts = collections.Counter(m[1].lower() for m in items)
    if any(n > 1 for n in counts.values()):
        raise ValueError('Duplicate section names require manual inspection.')
    return items


def validate_conditionals(items):
    for item in items:
        level = 0
        for line in item[2].splitlines():
            s = line.strip().lower()
            if s.startswith('if '):
                level += 1
            elif s == 'endif' or s.startswith('endif ;'):
                level -= 1
            elif s.startswith(('elif ', 'else')) and level == 0:
                raise ValueError(f'Branch without if in {item[1]}')
            if level < 0:
                raise ValueError(f'Unbalanced conditions in {item[1]}')
        if level:
            raise ValueError(f'Unbalanced conditions in {item[1]}')


def canonical(body):
    return HASH.sub(lambda m: m[1] + '<HASH>' + m[3] + m[4], body).replace('\r', '').strip()


def assignments(body):
    """Read assignment keys, including pre/post, without interpreting conditions."""
    for line in body.splitlines():
        quoted = False
        for offset, character in enumerate(line):
            if character == '"':
                quoted = not quoted
            elif character == ';' and not quoted:
                line = line[:offset]
                break
        line = line.strip()
        match = re.fullmatch(r'(?:(?:pre|post)\s+)?([^\s=]+)\s*=\s*(.*)', line, re.I)
        if match:
            yield match[1].lower(), match[2].strip()


def validate_texture_recipe(section, sections):
    """Check the selected rule's local call graph, not unrelated author rules.

    This is a bounded staging check, not a complete INI interpreter. External
    calls and runtime resource selection require an evidence-scoped manual patch.
    """
    visited, active, resources = set(), set(), set()
    has_replacement = False

    def visit(item):
        nonlocal has_replacement
        name = item[1].lower()
        if name in active:
            raise ValueError('Cyclic command-list calls require manual scope review.')
        if name in visited:
            return
        active.add(name)
        for key, value in assignments(item[2]):
            if (key.startswith(('draw', 'dispatch')) or key in {'handling', 'ib',
                    'match_first_index', 'match_index_count', 'match_first_vertex', 'match_vertex_count'}
                    or re.fullmatch(r'(?:vb|so)\d+', key)):
                raise ValueError(f'Geometry/component commands are outside this texture-only helper: {item[1]} / {key}')
            if re.fullmatch(r'(?:ps|vs|cs|gs|hs|ds)-(?:t|cb|u)\d+|o(?:\d+|d)', key):
                raise ValueError(f'Direct slot bindings require manual scope review: {item[1]} / {key}')
            if key == 'checktextureoverride':
                raise ValueError('Nested override dispatch requires manual scope review.')
            if key == 'run':
                called = sections.get(value.lower())
                if '\\' in value or not value.lower().startswith('commandlist') or called is None:
                    raise ValueError(f'Unresolved or external command call requires manual scope review: {value}')
                visit(called)
            elif key == 'this':
                target = re.sub(r'^(?:copy|reference)\s+', '', value, flags=re.I)
                target = re.sub(r'\s+unless_null$', '', target, flags=re.I).strip()
                has_replacement = True
                if target.lower() == 'null':
                    continue
                resource = sections.get(target.lower())
                if '\\' in target or not target.lower().startswith('resource') or resource is None:
                    raise ValueError(f'Unresolved or runtime this resource requires manual scope review: {value}')
                filenames = [v for k, v in assignments(resource[2]) if k == 'filename']
                if len(filenames) != 1 or not filenames[0].strip('"') or '$' in filenames[0]:
                    raise ValueError(f'Dynamic resource requires manual scope review: {target}')
                resources.add(resource[1])
        active.remove(name)
        visited.add(name)

    visit(section)
    if not has_replacement:
        raise ValueError('No local this replacement found; review the rule manually.')
    return {'recipe_sections': sorted(visited), 'resource_sections': sorted(resources)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ini', type=Path, required=True)
    parser.add_argument('--mapping', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    source = args.ini.resolve(strict=True)
    output = args.out_dir.resolve()
    loading_roots = [parent for parent in source.parents if parent.name.lower() == 'mods']
    if output.exists() or output.is_relative_to(source.parent) or any(output.is_relative_to(root) for root in loading_roots):
        raise ValueError('Use a new staging directory outside the selected mod INI directory.')
    raw = source.read_bytes()
    mapping = json.loads(args.mapping.read_text(encoding='utf-8-sig'))
    if digest(raw) != mapping['expected_source_sha256'].lower():
        raise ValueError('Source SHA-256 changed; inspect and stage again.')
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        raise ValueError('UTF-16 INI needs an encoding-aware custom patch.')
    text = raw.decode('latin1')
    original = parse(text)
    validate_conditionals(original)
    source_sections = {m[1].lower(): m for m in original}
    newline = '\r\r\n' if '\r\r\n' in text else '\r\n' if '\r\n' in text else '\n'
    changes = []
    aliases = mapping.get('aliases')
    if not isinstance(aliases, list) or not aliases:
        raise ValueError('At least one confirmed alias is required.')
    for alias in aliases:
        evidence = alias.get('evidence')
        if not isinstance(evidence, list) or not evidence or any(not isinstance(e, dict) or not str(e.get('reference', '')).strip() for e in evidence):
            raise ValueError('Each alias needs a nonempty evidence reference; the agent must verify it.')
        section = source_sections.get(alias['source_section'].lower())
        if section is None or not section[1].lower().startswith('textureoverride'):
            raise ValueError('Source must be an existing TextureOverride section.')
        body = section[2]
        scope_check = validate_texture_recipe(section, source_sections)
        matches = list(HASH.finditer(body))
        if len(matches) != 1:
            raise ValueError('Source needs exactly one eight-digit texture hash.')
        new_hash = alias['new_hash'].lower()
        if not re.fullmatch(r'[0-9a-f]{8}', new_hash):
            raise ValueError('new_hash must be eight hex digits.')
        old_hash = matches[0][2].lower()
        name = alias.get('new_section', 'TextureOverrideCaptured_' + new_hash)
        if not re.fullmatch(r'TextureOverride[A-Za-z0-9_.-]+', name):
            raise ValueError('Use a unique ASCII TextureOverride section name.')
        current = parse(text)
        existing = [m for m in current if m[1].lower().startswith('textureoverride') and any(h[2].lower() == new_hash for h in HASH.finditer(m[2]))]
        if existing:
            if any(canonical(m[2]) != canonical(body) for m in existing):
                raise ValueError(f'Hash {new_hash} has another recipe; analyze shared-resource semantics manually.')
            status = 'already_equivalent'
        else:
            if name.lower() in {m[1].lower() for m in current}:
                raise ValueError('Requested alias section name is already used.')
            cooked_body = HASH.sub(lambda m: m[1] + new_hash + m[3] + m[4], body, count=1)
            text += newline + '[' + name + ']' + newline + cooked_body
            if not text.endswith('\n'):
                text += newline
            status = 'added'
        changes.append({'source_section': section[1], 'old_hash': old_hash, 'new_hash': new_hash,
                        'new_section': name, 'status': status, 'evidence': evidence,
                        'local_scope_check': scope_check})
    validate_conditionals(parse(text))
    patched = text.encode('latin1')
    if not patched.startswith(raw):
        raise ValueError('Authored bytes must remain unchanged; only append aliases.')
    # Check literal resource filenames before creating the patch package.
    missing = []
    for filename in re.findall(r'^[ \t]*filename[ \t]*=[ \t]*([^\r\n]+)', text, re.M | re.I):
        value = filename.strip()
        value = value.split('"', 2)[1] if value.startswith('"') else value.split(';', 1)[0].strip()
        if '$' in value:
            continue
        actual_value = filename_text(value, raw)
        path = Path(actual_value) if Path(actual_value).is_absolute() else source.parent / actual_value
        if not path.is_file():
            missing.append(value)
    if missing:
        raise ValueError('Missing literal resources: ' + repr(missing))
    if source.read_bytes() != raw:
        raise ValueError('Source changed during preparation.')
    output.mkdir(parents=True, exist_ok=False)
    (output / 'original.ini').write_bytes(raw)
    (output / 'patched.ini').write_bytes(patched)
    (output / 'mapping.json').write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding='utf-8')
    diff = ''.join(difflib.unified_diff(raw.decode('latin1').replace('\r', '').splitlines(True),
                text.replace('\r', '').splitlines(True), fromfile='original', tofile='patched'))
    (output / 'patch.diff').write_text(diff, encoding='utf-8')
    report = {'source': str(source), 'source_sha256': digest(raw), 'patched_sha256': digest(patched),
              'aliases_added': sum(c['status'] == 'added' for c in changes), 'changes': changes,
              'original_bytes_preserved': True, 'missing_resources': [], 'file_validation_passed': True,
              'validation_scope': 'append-only texture aliases and selected local references; not full INI execution',
              'installed': False, 'game_verified': False, 'evidence_relation_verified_by_helper': False}
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(output), 'aliases_added': report['aliases_added'],
                      'installed': False, 'source_files_written': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
