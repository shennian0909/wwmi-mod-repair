"""Installation preservation and runtime-package integrity on synthetic files."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from install_skill import backup, install
from package_skill import archive_bytes, package


class ProjectToolsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='wwmi-project-test-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / 'source'
        self.destination = self.base / 'installed'
        contents = {
            'SKILL.md': b'---\nname: wwmi-mod-repair\ndescription: Synthetic test\n---\n',
            'LICENSE': b'Synthetic license\n', 'VERSION': b'0.1.0\n',
            'agents/openai.yaml': b'interface: {}\n',
            'references/example.md': b'Synthetic reference\n',
            'scripts/example.py': b'print("synthetic")\n',
            'SKILL.md 2026-01-01 00-00-00.BAK': b'private historical data',
            'README.md': b'Development documentation',
            'scripts/__pycache__/example.pyc': b'cache',
        }
        for relative, data in contents.items():
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def test_install_copies_only_runtime_files(self):
        result = install(self.source, self.destination)
        self.assertEqual(len(result['files']), 6)
        self.assertTrue(all(r['action'] == 'create' for r in result['files']))
        self.assertEqual((self.destination / 'SKILL.md').read_bytes(), (self.source / 'SKILL.md').read_bytes())
        self.assertFalse((self.destination / 'README.md').exists())
        self.assertFalse(list(self.destination.rglob('*.BAK')))
        self.assertFalse((self.destination / 'scripts/__pycache__').exists())

    def test_update_saves_exact_old_bytes_outside_skill_directory(self):
        install(self.source, self.destination)
        original = self.destination / 'SKILL.md'
        old_bytes = original.read_bytes()
        old_reference = (self.destination / 'references/example.md').read_bytes()
        (self.source / 'SKILL.md').write_bytes(old_bytes + b'Updated\n')
        (self.source / 'references/example.md').write_bytes(b'Updated reference\n')
        (self.destination / 'local-notes.md').write_bytes(b'Keep local customization')
        result = install(self.source, self.destination)
        saved = {r['file']: Path(r['backup']) for r in result['files'] if 'backup' in r}
        self.assertEqual(set(saved), {'SKILL.md', 'references/example.md'})
        self.assertEqual(saved['SKILL.md'].read_bytes(), old_bytes)
        self.assertEqual(saved['references/example.md'].read_bytes(), old_reference)
        for relative, path in saved.items():
            self.assertFalse(path.is_relative_to(self.destination))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(path, Path(result['backup_directory']) / digest / relative)
        self.assertFalse(list(self.destination.rglob('*.BAK')))
        self.assertEqual(original.read_bytes(), old_bytes + b'Updated\n')
        self.assertEqual((self.destination / 'local-notes.md').read_bytes(), b'Keep local customization')
        self.assertEqual([r['action'] for r in result['files']].count('update'), 2)

    def test_identical_install_is_noop(self):
        install(self.source, self.destination)
        original = self.destination / 'SKILL.md'
        stamp = original.stat().st_mtime_ns
        result = install(self.source, self.destination)
        self.assertTrue(all(r['action'] == 'unchanged' for r in result['files']))
        self.assertEqual(original.stat().st_mtime_ns, stamp)
        self.assertFalse(list(self.destination.rglob('*.BAK')))
        self.assertFalse(Path(result['backup_directory']).exists())

    def test_backup_name_collision_preserves_existing_backup(self):
        occupied = self.base / 'backups' / 'SKILL.md'
        occupied.parent.mkdir()
        occupied.write_bytes(b'earlier backup')
        with self.assertRaises(OSError):
            backup(occupied, b'different bytes')
        self.assertEqual(occupied.read_bytes(), b'earlier backup')
        self.assertEqual(backup(occupied, b'earlier backup'), occupied)

    def test_repeated_updates_preserve_each_previous_version(self):
        install(self.source, self.destination)
        first = (self.source / 'SKILL.md').read_bytes()
        (self.source / 'SKILL.md').write_bytes(first + b'Second\n')
        first_update = install(self.source, self.destination)
        (self.source / 'SKILL.md').write_bytes(first + b'Third\n')
        second_update = install(self.source, self.destination)
        first_snapshot = Path(next(r['backup'] for r in first_update['files'] if r['file'] == 'SKILL.md'))
        second_snapshot = Path(next(r['backup'] for r in second_update['files'] if r['file'] == 'SKILL.md'))
        self.assertNotEqual(first_snapshot, second_snapshot)
        self.assertEqual(first_snapshot.read_bytes(), first)
        self.assertEqual(second_snapshot.read_bytes(), first + b'Second\n')

    def test_dry_run_does_not_create_destination(self):
        result = install(self.source, self.destination, dry_run=True)
        self.assertTrue(result['dry_run'])
        self.assertFalse(self.destination.exists())
        self.assertFalse(Path(result['backup_directory']).exists())

    def test_dry_run_update_does_not_write_or_create_backups(self):
        install(self.source, self.destination)
        original = (self.destination / 'SKILL.md').read_bytes()
        (self.source / 'SKILL.md').write_bytes(original + b'Updated\n')
        result = install(self.source, self.destination, dry_run=True)
        self.assertEqual([r['action'] for r in result['files']].count('update'), 1)
        self.assertEqual((self.destination / 'SKILL.md').read_bytes(), original)
        self.assertFalse(Path(result['backup_directory']).exists())

    def test_linked_backup_directory_is_rejected_before_update(self):
        installed = install(self.source, self.destination)
        original = (self.destination / 'SKILL.md').read_bytes()
        (self.source / 'SKILL.md').write_bytes(original + b'Updated\n')
        actual = self.base / 'redirected-backups'
        actual.mkdir()
        try:
            Path(installed['backup_directory']).symlink_to(actual, target_is_directory=True)
        except OSError:
            self.skipTest('Creating symbolic links is unavailable on this host.')
        with self.assertRaises(ValueError):
            install(self.source, self.destination)
        self.assertEqual((self.destination / 'SKILL.md').read_bytes(), original)
        self.assertEqual(list(actual.iterdir()), [])

    def test_overlap_and_occupied_file_are_rejected_before_writing(self):
        with self.assertRaises(ValueError):
            install(self.source, self.source / 'installed')
        (self.destination / 'VERSION').mkdir(parents=True)
        with self.assertRaises(ValueError):
            install(self.source, self.destination)
        self.assertFalse((self.destination / 'SKILL.md').exists())

    def test_linked_destination_is_rejected(self):
        actual = self.base / 'actual'
        actual.mkdir()
        try:
            self.destination.symlink_to(actual, target_is_directory=True)
        except OSError:
            self.skipTest('Creating symbolic links is unavailable on this host.')
        with self.assertRaises(ValueError):
            install(self.source, self.destination)
        self.assertEqual(list(actual.iterdir()), [])

    def test_archive_is_deterministic_and_manifest_verifies_every_file(self):
        release_version, first = archive_bytes(self.source)
        self.assertEqual(release_version, '0.1.0')
        self.assertEqual(first, archive_bytes(self.source)[1])
        with zipfile.ZipFile(io.BytesIO(first)) as archive:
            names = archive.namelist()
            self.assertEqual(len(names), 7)
            self.assertFalse(any('BAK' in n or '__pycache__' in n or 'README' in n for n in names))
            manifest = json.loads(archive.read('wwmi-mod-repair/MANIFEST.json'))
            self.assertEqual(len(manifest['sha256']), 6)
            for relative, expected in manifest['sha256'].items():
                self.assertEqual(hashlib.sha256(archive.read('wwmi-mod-repair/' + relative)).hexdigest(), expected)
                self.assertEqual(archive.read('wwmi-mod-repair/' + relative), (self.source / relative).read_bytes())

    def test_packaging_checks_tag_and_does_not_replace_changed_artifact(self):
        output = self.base / 'dist'
        with self.assertRaises(ValueError):
            package(self.source, output, 'v0.2.0')
        self.assertFalse(output.exists())
        result = package(self.source, output, 'v0.1.0')
        archive = Path(result['archive'])
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), result['sha256'])
        before = archive.read_bytes()
        self.assertEqual(package(self.source, output)['sha256'], result['sha256'])
        (self.source / 'SKILL.md').write_bytes(b'changed content')
        with self.assertRaises(FileExistsError):
            package(self.source, output)
        self.assertEqual(archive.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
