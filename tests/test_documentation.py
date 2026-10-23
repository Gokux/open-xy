"""Relative links in the repository's Markdown resolve to files inside it."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DocumentationTests(unittest.TestCase):
    def test_relative_markdown_links_resolve_inside_repository(self):
        documents = [ROOT / name for name in ('README.md', 'CONTRIBUTING.md', 'AGENTS.md')]
        for directory in ('docs', 'machines', 'sdk', '.github'):
            documents.extend((ROOT / directory).rglob('*.md'))
        for document in documents:
            for target in re.findall(r'\]\(([^)]+)\)', document.read_text(encoding='utf-8')):
                if target.startswith(('http://', 'https://', '#', 'mailto:')):
                    continue
                relative = target.split('#', 1)[0]
                resolved = (document.parent / relative).resolve()
                with self.subTest(document=document.relative_to(ROOT), target=target):
                    self.assertTrue(resolved.is_relative_to(ROOT), 'Public docs must not link outside the repository')
                    self.assertTrue(resolved.is_file(), 'Missing local documentation target')
