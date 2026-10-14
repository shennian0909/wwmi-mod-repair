"""Read-only WWMI environment, mod INI, and FrameAnalysis inspection."""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import struct

SECTION_RX = re.compile(r'^\[([^\]]+)\][^\r\n]*\r*\n?(.*?)(?=^\[|\Z)', re.M | re.S)
SLOT_RX = re.compile(r'-(ps|vs|cs|gs|hs|ds)-(t|cb)(\d+)(?:=([0-9a-f]{8})(?:\(([0-9a-f]{8})\))?)?', re.I)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def text_bytes(raw):
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        return raw.decode('utf-16'), 'utf-16'
    try:
        return raw.decode('utf-8-sig'), 'utf-8'
    except UnicodeDecodeError:
        try:
            return raw.decode('mbcs'), 'windows-ansi'
        except (UnicodeDecodeError, LookupError):
            return raw.decode('latin1'), 'byte-preserving-latin1'


def walk_files(root):
    """Do not traverse symlinks/junctions; report only files in the selected tree."""
    def scan_error(error):
        raise error

    for current, dirs, files in os.walk(root, followlinks=False, onerror=scan_error):
        dirs[:] = [d for d in dirs if not linked(Path(current) / d)]
        for name in files:
            path = Path(current) / name
            if not linked(path):
                yield path


def linked(path):
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)


def ini_info(path):
    raw = path.read_bytes()
    text, encoding = text_bytes(raw)
    matches = list(SECTION_RX.finditer(text))
    counts = collections.Counter(m[1].lower() for m in matches)
    resources, overrides, errors, geometry, keys, outside = [], [], [], [], [], []
    before_header = text[:matches[0].start()] if matches else text
    for line in before_header.splitlines():
        if line.strip() and not line.lstrip().startswith((';', '#', 'namespace', 'include')):
            outside.append(line)
    for match in matches:
        name, body = match[1], match[2]
        depth = 0
        for line in body.splitlines():
            s = line.strip()
            lower = s.lower()
            if lower.startswith('if '):
                depth += 1
            elif lower.startswith(('elif ', 'else')) and depth == 0:
                errors.append({'section': name, 'error': 'branch without if', 'line': s})
            elif lower == 'endif' or lower.startswith('endif ;'):
                depth -= 1
                if depth < 0:
                    errors.append({'section': name, 'error': 'endif without if'})
                    depth = 0
            if re.match(r'^(drawindexed|match_first_index|match_index_count|handling|ib|vb\d+)\s*=', s, re.I):
                geometry.append([name, s])
            if name.lower().startswith('key') or re.match(r'^global\s+persist\b', s, re.I):
                if s and not s.startswith(';'):
                    keys.append([name, s])
            filename = re.match(r'^filename\s*=\s*(.*)', s, re.I)
            if filename:
                value = filename[1].strip()
                if value.startswith('"'):
                    value = value.split('"', 2)[1]
                else:
                    value = value.split(';', 1)[0].strip()
                dynamic = '$' in value
                target = Path(value) if Path(value).is_absolute() else path.parent / value
                resources.append({'section': name, 'filename': value, 'dynamic': dynamic,
                                  'path': str(target), 'exists': None if dynamic else target.is_file()})
        if depth:
            errors.append({'section': name, 'error': 'unclosed if', 'depth': depth})
        hashes = re.findall(r'^[ \t]*hash[ \t]*=[ \t]*([0-9a-f]{8,16})\b', body, re.M | re.I)
        if hashes:
            overrides.append({'section': name, 'hashes': hashes,
                              'resource_choices': re.findall(r'^[ \t]*this[ \t]*=[ \t]*([^\r\n]+)', body, re.M | re.I),
                              'first_index': re.findall(r'^[ \t]*match_first_index[ \t]*=[ \t]*([^\r\n]+)', body, re.M | re.I)})
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'encoding': encoding,
            'crcrlf_count': raw.count(b'\r\r\n'), 'section_count': len(matches),
            'duplicate_section_names': {k: n for k, n in counts.items() if n > 1},
            'conditional_errors': errors, 'entries_before_first_section': outside,
            'resources': resources, 'missing_literal_resources': [x for x in resources if x['exists'] is False],
            'overrides': overrides,
            'trigger_slots': [line.strip() for line in re.findall(r'^[ \t]*CheckTextureOverride[ \t]*=[ \t]*([^\r\n]+)', text, re.M | re.I)],
            'direct_slot_assignments': [line.strip() for line in re.findall(r'^[ \t]*ps-t\d+[ \t]*=[ \t]*[^\r\n]+', text, re.M | re.I)],
            'geometry_fingerprint': hashlib.sha256(json.dumps(geometry).encode()).hexdigest(),
            'keys_fingerprint': hashlib.sha256(json.dumps(keys).encode()).hexdigest()}


def inspect_mod(path):
    if not path.exists() or linked(path):
        raise ValueError('Selected mod is missing or is a link/reparse point.')
    if path.is_file() and path.suffix.lower() in {'.zip', '.rar', '.7z'}:
        return {'path': str(path), 'type': 'actual_archive_file', 'requires_archive_inspection': True,
                'bytes': path.stat().st_size, 'sha256': sha(path)}
    files = [path] if path.is_file() else sorted(walk_files(path))
    inis = [ini_info(p) for p in files if p.suffix.lower() == '.ini']
    jasm = path / '.JASM_ModConfig.json' if path.is_dir() else path.parent / '.JASM_ModConfig.json'
    metadata = {}
    if jasm.is_file():
        data = json.loads(jasm.read_text(encoding='utf-8-sig'))
        metadata = {k: data.get(k) for k in ('DateAdded', 'CustomName', 'ModUrl')}
    return {'path': str(path), 'type': 'directory' if path.is_dir() else 'ini_file',
            'disabled_by_path_name': any(p.lower().startswith('disabled') for p in path.parts),
            'jasm': metadata, 'ini_count': len(inis), 'inis': inis,
            'game_verified': False, 'source_files_written': False}


def dds_info(path, stats=False):
    with path.open('rb') as stream:
        header = stream.read(152)
    if len(header) < 128 or header[:4] != b'DDS ':
        return {'invalid_dds_header': True}
    height, width = struct.unpack_from('<II', header, 12)
    result = {'size': [width, height], 'mips': struct.unpack_from('<I', header, 28)[0],
              'fourcc': header[84:88].decode('ascii', errors='replace')}
    if header[84:88] == b'DX10' and len(header) >= 148:
        result['dxgi'] = struct.unpack_from('<I', header, 128)[0]
        if (width, height) == (1, 1) and result['dxgi'] in (28, 29) and len(header) >= 152:
            result['rgba_pixel'] = list(header[148:152])
        elif (width, height) == (1, 1) and result['dxgi'] in (87, 91) and len(header) >= 152:
            result['rgba_pixel'] = [header[150], header[149], header[148], header[151]]
    elif (width, height) == (1, 1) and struct.unpack_from('<I', header, 80)[0] & 0x40:
        bits = struct.unpack_from('<I', header, 88)[0]
        if bits in (16, 24, 32) and len(header) >= 128 + bits // 8:
            packed = int.from_bytes(header[128:128 + bits // 8], 'little')
            masks = struct.unpack_from('<4I', header, 92)
            pixel = []
            for channel, mask in enumerate(masks):
                if not mask:
                    pixel.append(255 if channel == 3 else 0)
                else:
                    shift = (mask & -mask).bit_length() - 1
                    value = (packed & mask) >> shift
                    pixel.append(round(value * 255 / ((1 << mask.bit_count()) - 1)))
            result['rgba_pixel'] = pixel
    if stats:
        try:
            from PIL import Image
            with Image.open(path) as source:
                with source.convert('RGBA') as image:
                    result['rgba_extrema'] = [list(v) for v in image.getextrema()]
                    if image.size == (1, 1):
                        result['rgba_pixel'] = list(image.getpixel((0, 0)))
                    if all(a == b for a, b in image.getextrema()):
                        result['constant_rgba'] = list(image.getpixel((0, 0)))
        except (ImportError, OSError, ValueError) as error:
            result['pixel_decode_error'] = str(error)
    return result


def inspect_capture(path, fragment, draws, stats):
    if not path.is_dir() or linked(path):
        raise ValueError('Capture path is missing or is a link/reparse point.')
    log_path = path / 'log.txt'
    lines = log_path.read_text(encoding='utf-8', errors='replace').splitlines() if log_path.is_file() else []
    shader_map, mod_draws, bindings = {}, [], []
    mod_fragment = fragment.lower() if fragment else None
    for number, line in enumerate(lines, 1):
        shader = re.match(r'^(\d{6}) (?:PS|VS|CS)SetShader\(.*hash=([0-9a-f]{16})', line, re.I)
        if shader:
            shader_map.setdefault(shader[1], []).append(line)
        if '3dmigoto' in line.lower() and re.search(r'\bDrawIndexed\(', line, re.I):
            if not mod_fragment or mod_fragment in line.lower():
                mod_draws.append({'draw': int(line[:6]), 'line_number': number, 'command': line})
        if mod_fragment and mod_fragment in line.lower() and re.search(r'\bthis\s*=|\bps-t\d+\s*=', line, re.I):
            bindings.append({'line_number': number, 'command': line})
    selected = set(draws) if draws else {x['draw'] for x in mod_draws[:12]}
    if not selected:
        available = sorted({int(m[1]) for p in path.iterdir() if p.is_file() and (m := re.match(r'^(\d{6})', p.name))})
        selected = set(available[:12])
    records = []
    files = list(walk_files(path))
    for source in sorted(path.iterdir()):
        if not source.is_file() or linked(source) or source.suffix.lower() not in {'.dds', '.dsc', '.buf', '.txt'}:
            continue
        draw_match = re.match(r'^(\d{6})', source.name)
        if not draw_match or (selected and int(draw_match[1]) not in selected):
            continue
        slot = SLOT_RX.search(source.name)
        record = {'name': source.name, 'draw': int(draw_match[1]), 'bytes': source.stat().st_size}
        if slot:
            record.update(slot=f'{slot[1].lower()}-{slot[2].lower()}{slot[3]}', hash=slot[4], original_hash=slot[5])
        command = re.search(r'\[([^]]+)\]', source.name)
        if command:
            record['dump_context'] = command[1]
        if source.suffix.lower() == '.dds':
            record['dds'] = dds_info(source, stats)
            record['sha256'] = sha(source)
        elif source.suffix.lower() == '.dsc':
            record['descriptor'] = source.read_text(encoding='utf-8', errors='replace')
        records.append(record)
    present = any('[Present]' in s for s in lines[-256:])
    return {'path': str(path), 'log_exists': log_path.is_file(), 'log_sha256': sha(log_path) if log_path.is_file() else None,
            'present_observed_in_tail': present, 'last_log_lines': lines[-8:],
            'log_completeness_requires_review': True, 'all_files_count': len(files),
            'logical_bytes_including_hardlink_duplicates': sum(p.stat().st_size for p in files),
            'root_extension_counts': dict(collections.Counter(p.suffix.lower() for p in path.iterdir() if p.is_file())),
            'selected_draws': sorted(selected),
            'selection_mode': 'explicit_draws' if draws else 'automatic_sample',
            'full_draw_coverage_confirmed': False,
            'shader_set_events': {str(k): shader_map.get(f'{k:06d}', []) for k in selected},
            'mod_custom_draw_count': len(mod_draws), 'mod_custom_draws': [x for x in mod_draws if x['draw'] in selected],
            'override_assignments': bindings[:80], 'dump_records': records,
            'game_verified': False, 'source_files_written': False}


def inspect_environment(root, launcher_config=None, rabbit_ini=None):
    if not root.is_dir() or linked(root):
        raise ValueError('WWMI root is missing or is a link/reparse point.')
    result = {'root': str(root), 'files': [], 'settings': {}, 'source_files_written': False}
    for name in ('d3dx.ini', 'd3dx_user.ini', 'd3d11.dll', 'd3dcompiler_47.dll'):
        p = root / name
        if p.is_file():
            result['files'].append({'path': str(p), 'bytes': p.stat().st_size, 'sha256': sha(p)})
    p = root / 'd3dx.ini'
    if p.is_file():
        text, _ = text_bytes(p.read_bytes())
        for key in ('hunting', 'analyse_frame', 'analyse_options', 'export_shaders', 'export_hlsl'):
            result['settings'][key] = re.findall(r'^' + key + r'[ \t]*=[ \t]*([^\r\n]+)', text, re.M)
    launcher = launcher_config.absolute() if launcher_config else root.parent / 'XXMI Launcher Config.json'
    if launcher_config and not launcher.is_file():
        raise ValueError('The selected launcher configuration is missing.')
    if launcher.is_file():
        try:
            wwmi = json.loads(launcher.read_text(encoding='utf-8-sig'))['Importers']['WWMI']
            result['launcher'] = {'path': str(launcher), 'enable_hunting': wwmi['Migoto']['enable_hunting'],
                'hunting_on': wwmi['Importer']['d3dx_ini']['enable_hunting']['Hunting']['hunting']['on']}
        except (KeyError, ValueError) as error:
            result['launcher_schema_review_needed'] = str(error)
    rabbit = rabbit_ini.absolute() if rabbit_ini else None
    if rabbit is not None:
        if not rabbit.is_file():
            raise ValueError('The selected RabbitFX INI is missing.')
        result['rabbit'] = {'path': str(rabbit), 'sha256': sha(rabbit),
                            'version_mentions': re.findall(r'\bVersion\s+([0-9]+(?:\.[0-9]+)+)', rabbit.read_bytes().decode('latin1'), re.I)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    environment = sub.add_parser('environment'); environment.add_argument('--root', type=Path, required=True)
    environment.add_argument('--launcher-config', type=Path)
    environment.add_argument('--rabbit-ini', type=Path)
    mod = sub.add_parser('mod'); mod.add_argument('--path', type=Path, required=True)
    capture = sub.add_parser('capture'); capture.add_argument('--path', type=Path, required=True)
    capture.add_argument('--mod-fragment'); capture.add_argument('--draw', nargs='+', type=int)
    capture.add_argument('--dds-stats', action='store_true')
    for child in (environment, mod, capture):
        child.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.command == 'environment':
        result = inspect_environment(args.root.absolute(), args.launcher_config, args.rabbit_ini)
    elif args.command == 'mod':
        result = inspect_mod(args.path.absolute())
    else:
        result = inspect_capture(args.path.absolute(), args.mod_fragment, args.draw, args.dds_stats)
    content = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with args.out.open('x', encoding='utf-8') as stream:
            stream.write(content + '\n')
        print(json.dumps({'report': str(args.out.absolute()), 'source_files_written': False}, ensure_ascii=False))
    else:
        print(content)


if __name__ == '__main__':
    main()
