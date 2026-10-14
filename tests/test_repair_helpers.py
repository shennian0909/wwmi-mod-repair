"""Check read-only inspection and append-only aliases with synthetic evidence."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from inspect_wwmi import dds_info, inspect_mod


class RepairHelpersTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='wwmi-repair-test-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.mod = self.base / 'Mods' / 'SyntheticMod'
        self.mod.mkdir(parents=True)
        self.ini = self.mod / 'mod.ini'
        self.raw = ('; synthetic author comment\r\n'
                    '[TextureOverrideHair]\r\nhash = 12345678 ; original\r\n'
                    'if $enabled\r\nthis = ResourceHair\r\nendif\r\n'
                    '[ResourceHair]\r\nfilename = "头发.dds"\r\n').encode('utf-8')
        self.ini.write_bytes(self.raw)
        (self.mod / '头发.dds').write_bytes(b'synthetic resource, no game data')
        self.mapping = self.base / 'mapping.json'
        self.output = self.base / 'stage'
        self.write_mapping()

    def write_mapping(self, **changes):
        alias = {'source_section': 'TextureOverrideHair', 'new_hash': 'aabbccdd',
                 'evidence': [{'reference': 'synthetic draw 1 / ps-t0'}]}
        alias.update(changes)
        self.mapping.write_text(json.dumps({'expected_source_sha256': hashlib.sha256(self.ini.read_bytes()).hexdigest(),
                                           'aliases': [alias]}, ensure_ascii=False), encoding='utf-8')

    def stage(self):
        return subprocess.run([sys.executable, '-B', '-X', 'utf8', str(SCRIPTS / 'stage_texture_aliases.py'),
                               '--ini', str(self.ini), '--mapping', str(self.mapping), '--out-dir', str(self.output)],
                              text=True, encoding='utf-8', capture_output=True,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), timeout=20)

    def test_alias_preserves_author_bytes_conditions_and_source(self):
        result = self.stage()
        self.assertEqual(result.returncode, 0, result.stderr)
        patched = (self.output / 'patched.ini').read_bytes()
        self.assertTrue(patched.startswith(self.raw))
        self.assertIn(b'hash = aabbccdd ; original', patched)
        self.assertEqual(patched.count(b'if $enabled\r\nthis = ResourceHair\r\nendif'), 2)
        self.assertEqual(self.ini.read_bytes(), self.raw)
        report = json.loads((self.output / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['aliases_added'], 1)
        self.assertFalse(report['installed'])
        self.assertFalse(report['game_verified'])
        self.assertFalse(report['evidence_relation_verified_by_helper'])

    def test_changed_source_is_rejected(self):
        self.ini.write_bytes(self.raw + b'; later modification\r\n')
        result = self.stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Source SHA-256 changed', result.stderr)
        self.assertFalse(self.output.exists())

    def test_conflicting_hash_recipe_is_rejected(self):
        self.ini.write_bytes(self.raw + b'[TextureOverrideConflict]\r\nhash = aabbccdd\r\nthis = ResourceOther\r\n')
        self.write_mapping()
        result = self.stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('another recipe', result.stderr)
        self.assertFalse(self.output.exists())

    def test_equivalent_existing_alias_is_not_duplicated(self):
        self.ini.write_bytes(self.raw + b'[TextureOverrideExisting]\r\nhash = aabbccdd ; original\r\nif $enabled\r\nthis = ResourceHair\r\nendif\r\n')
        self.write_mapping()
        result = self.stage()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.output / 'patched.ini').read_bytes(), self.ini.read_bytes())
        report = json.loads((self.output / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['aliases_added'], 0)

    def test_geometry_and_missing_evidence_are_rejected(self):
        self.ini.write_bytes(self.raw.replace(b'hash = 12345678', b'match_first_index = 0\r\nhash = 12345678'))
        self.write_mapping()
        result = self.stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Geometry/component', result.stderr)
        self.assertFalse(self.output.exists())
        self.ini.write_bytes(self.raw)
        self.write_mapping(evidence=[])
        result = self.stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('evidence reference', result.stderr)
        self.assertFalse(self.output.exists())

    def test_missing_resource_and_loading_directory_output_are_rejected(self):
        (self.mod / '头发.dds').unlink()
        result = self.stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Missing literal resources', result.stderr)
        self.assertFalse(self.output.exists())
        (self.mod / '头发.dds').write_bytes(b'synthetic')
        self.output = self.base / 'Mods' / 'stage'
        result = self.stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('outside', result.stderr)
        self.assertFalse(self.output.exists())

    def test_inspection_ignores_backup_ini_and_reports_conditions(self):
        (self.mod / 'mod.ini 2026-01-01 00-00-00.BAK').write_bytes(b'broken historical INI')
        report = inspect_mod(self.mod)
        self.assertEqual(report['ini_count'], 1)
        self.assertEqual(report['inis'][0]['missing_literal_resources'], [])
        self.assertFalse(report['source_files_written'])
        self.assertEqual(self.ini.read_bytes(), self.raw)
        self.ini.write_bytes(self.raw.replace(b'endif\r\n', b''))
        report = inspect_mod(self.mod)
        self.assertEqual(report['inis'][0]['conditional_errors'][0]['error'], 'unclosed if')

    def test_inspection_reports_missing_literal_resource(self):
        (self.mod / '头发.dds').unlink()
        report = inspect_mod(self.mod)
        missing = report['inis'][0]['missing_literal_resources']
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]['filename'], '头发.dds')
        self.assertFalse(report['game_verified'])

    def test_dds_header_pixel_is_decoded_without_pillow(self):
        raw = bytearray(152)
        raw[:4] = b'DDS '
        struct.pack_into('<I', raw, 4, 124)
        struct.pack_into('<II', raw, 12, 1, 1)
        struct.pack_into('<I', raw, 28, 1)
        raw[84:88] = b'DX10'
        struct.pack_into('<I', raw, 128, 28)
        raw[148:152] = bytes([12, 34, 56, 255])
        path = self.base / 'synthetic.dds'
        path.write_bytes(raw)
        self.assertEqual(dds_info(path)['rgba_pixel'], [12, 34, 56, 255])
        path.write_bytes(b'invalid')
        self.assertTrue(dds_info(path)['invalid_dds_header'])


if __name__ == '__main__':
    unittest.main()
