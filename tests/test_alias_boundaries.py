"""Exercise the texture-alias contract with synthetic INIs, never live Mods."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


class AliasBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='alias-boundary-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.mod = self.root / 'Mods' / 'Synthetic'
        self.mod.mkdir(parents=True)
        self.ini = self.mod / 'mod.ini'
        self.output = self.root / 'stage'
        self.mapping = self.root / 'mapping.json'
        (self.mod / '头发.dds').write_bytes(b'synthetic placeholder; not game data')

    def stage(self, recipe, extra='', bom=False):
        text = ('[TextureOverrideHair]\r\nhash = 12345678\r\n' + recipe + '\r\n'
                '[ResourceHair]\r\nfilename = "头发.dds"\r\n' + extra)
        raw = (b'\xef\xbb\xbf' if bom else b'') + text.encode('utf-8')
        self.ini.write_bytes(raw)
        self.mapping.write_text(json.dumps({
            'expected_source_sha256': hashlib.sha256(raw).hexdigest(),
            'aliases': [{'source_section': 'TextureOverrideHair', 'new_hash': 'aabbccdd',
                         'evidence': [{'reference': 'synthetic-draw.txt', 'slot': 'ps-t0'}]}]
        }), encoding='utf-8')
        result = subprocess.run([sys.executable, '-B', '-X', 'utf8',
                                 str(SCRIPTS / 'stage_texture_aliases.py'),
                                 '--ini', str(self.ini), '--mapping', str(self.mapping),
                                 '--out-dir', str(self.output)], capture_output=True,
                                text=True, encoding='utf-8', timeout=20)
        self.assertEqual(self.ini.read_bytes(), raw, 'Source must never be modified')
        return result, raw

    def reject(self, recipe, extra=''):
        result, _ = self.stage(recipe, extra)
        self.assertNotEqual(result.returncode, 0, 'Out-of-scope recipe was certified as a valid patch')
        self.assertFalse(self.output.exists(), 'A refused recipe must not leave an installable patch')

    def test_conditional_unicode_bom_and_null_remain_supported(self):
        result, raw = self.stage('if $enabled\r\nthis = ResourceHair\r\nelse\r\nthis = null\r\nendif', bom=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        patched = (self.output / 'patched.ini').read_bytes()
        self.assertTrue(patched.startswith(raw))
        self.assertEqual(patched.count(b'\xef\xbb\xbf'), 1)
        self.assertIn(b'this = null\r\nendif', patched)
        report = json.loads((self.output / 'report.json').read_text(encoding='utf-8'))
        self.assertFalse(report['installed'])
        self.assertFalse(report['game_verified'])

    def test_local_texture_command_list_remains_supported(self):
        result, _ = self.stage('run = CommandListSelect',
                              '[CommandListSelect]\r\nif $variant\r\nthis = ResourceHair\r\n'
                              'else\r\nthis = null\r\nendif\r\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        patched = (self.output / 'patched.ini').read_bytes()
        self.assertEqual(patched.count(b'[CommandListSelect]'), 1)
        self.assertEqual(patched.count(b'run = CommandListSelect'), 2)

    def test_copy_reference_and_post_resource_assignment_remain_supported(self):
        result, _ = self.stage('if $variant\r\nthis = copy ResourceHair\r\nelse\r\n'
                              'post this = reference ResourceHair unless_null\r\nendif')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_direct_slot_binding_requires_manual_review(self):
        self.reject('this = ResourceHair\r\nps-t7 = ResourceHair')

    def test_post_slot_binding_requires_manual_review(self):
        self.reject('this = ResourceHair\r\npost ps-t7 = null')

    def test_post_geometry_is_not_hidden_from_check(self):
        self.reject('this = ResourceHair\r\npost handling = skip')

    def test_nested_draw_is_not_a_texture_only_recipe(self):
        self.reject('run = CommandListSelect',
                    '[CommandListSelect]\r\nrun = CommandListDraw\r\n'
                    '[CommandListDraw]\r\nthis = ResourceHair\r\ndrawindexed = 3, 0, 0\r\n')

    def test_nested_direct_slot_is_not_a_texture_only_recipe(self):
        self.reject('run = CommandListSelect',
                    '[CommandListSelect]\r\nthis = ResourceHair\r\nvs-cb0 = ResourceHair\r\n')

    def test_unresolved_command_call_is_not_certified(self):
        self.reject('run = CommandListMissing\r\nthis = ResourceHair')

    def test_external_command_call_requires_manual_review(self):
        self.reject('run = CommandList\\External\\Select\r\nthis = ResourceHair')

    def test_cyclic_command_call_requires_manual_review(self):
        self.reject('run = CommandListA',
                    '[CommandListA]\r\nrun = CommandListB\r\n'
                    '[CommandListB]\r\nthis = ResourceHair\r\nrun = CommandListA\r\n')

    def test_undefined_this_resource_is_not_certified(self):
        self.reject('this = ResourceTypo')

    def test_undefined_nested_resource_is_not_certified(self):
        self.reject('run = CommandListSelect',
                    '[CommandListSelect]\r\nthis = ResourceTypo\r\n')

    def test_dynamic_resource_requires_manual_review(self):
        self.reject('this = ResourceGenerated', '[ResourceGenerated]\r\n')

    def test_external_resource_requires_manual_review(self):
        self.reject('this = Resource\\External\\Hair')

    def test_dynamic_filename_after_quoted_semicolon_requires_manual_review(self):
        self.reject('this = ResourceGenerated',
                    '[ResourceGenerated]\r\nfilename = "variant;$choice.dds"\r\n')

    def test_unrelated_command_lists_do_not_block_safe_alias(self):
        result, _ = self.stage('this = ResourceHair',
                              '[CommandListUnrelated]\r\ndrawindexed = 3, 0, 0\r\n'
                              'ps-t7 = null\r\n')
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
