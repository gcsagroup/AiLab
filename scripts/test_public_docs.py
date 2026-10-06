"""在独立目录验证公开文档，不让本地保留的内部文件掩盖链接错误。"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from check_public_docs import check

ROOT = Path(__file__).resolve().parents[1]


class PublicDocsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = json.loads((ROOT / 'i18n/manifest.json').read_text())
        self.paths = [x['path'] for x in self.manifest['documents']] + self.manifest['indexes'] + ['i18n/manifest.json']
        for name in self.paths:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)

    def test_public_tree_is_self_contained(self):
        self.assertEqual(check(self.root, self.paths), [])

    def test_missing_translation_is_rejected(self):
        (self.root / 'i18n/ja/docs/USER_GUIDE.md').unlink()
        self.assertTrue(check(self.root, self.paths))

    def test_unrecorded_edit_is_rejected(self):
        with (self.root / 'i18n/fr/README.md').open('a') as file:
            file.write('\nModification\n')
        self.assertTrue(any('摘要' in x for x in check(self.root, self.paths)))

    def test_internal_local_file_cannot_satisfy_public_link(self):
        secret = self.root / 'docs/implementation/internal.md'
        secret.parent.mkdir(parents=True)
        secret.write_text('本地内部记录')
        with (self.root / 'README.md').open('a') as file:
            file.write('\n[记录](docs/implementation/internal.md)\n')
        self.assertTrue(any('链接不是公开文档' in x for x in check(self.root, self.paths)))

    def test_accidental_internal_tracking_is_rejected(self):
        self.assertTrue(any('内部' in x for x in check(self.root, self.paths + ['docs/audits/private.md'])))

    def test_duplicate_language_cannot_replace_missing_language(self):
        self.manifest['documents'][-1]['language'] = 'en'
        (self.root / 'i18n/manifest.json').write_text(json.dumps(self.manifest))
        self.assertTrue(any('每种语言' in x for x in check(self.root, self.paths)))


if __name__ == '__main__':
    unittest.main()
