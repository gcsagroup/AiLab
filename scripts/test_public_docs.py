"""Documentation checks run in isolated fixtures, without local backup fallback."""
import tempfile
import unittest
from pathlib import Path
from check_public_docs import check, DOCUMENTS


class PublicDocsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in DOCUMENTS:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# Studio', encoding='utf-8')

    def test_local_screenshot(self):
        image = self.root / 'docs/images/ui.png'
        image.parent.mkdir(parents=True); image.write_bytes(b'fixture')
        (self.root / 'README.md').write_text('![UI](docs/images/ui.png)', encoding='utf-8')
        self.assertEqual(check(self.root), [])
        image.unlink()
        self.assertTrue(check(self.root))

    def test_no_link_to_backup(self):
        file = self.root / 'backup/old.md'
        file.parent.mkdir(); file.write_text('old', encoding='utf-8')
        (self.root / 'README.md').write_text('[Old](backup/old.md)', encoding='utf-8')
        self.assertTrue(check(self.root))

    def test_missing_document_and_escape(self):
        (self.root / 'CHANGELOG.md').unlink()
        (self.root / 'README.md').write_text('[Outside](../outside.md)', encoding='utf-8')
        self.assertEqual(len(check(self.root)), 2)


if __name__ == '__main__': unittest.main()
