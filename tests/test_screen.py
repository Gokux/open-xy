"""Platform SVG contract; host structure checks are not hardware rendering."""
import unittest
import xml.etree.ElementTree as ET

from opxy_sdk import screen


class PlatformScreenTests(unittest.TestCase):
    def test_sdk_header_and_machine_geometry_compose_without_stock_artwork(self):
        fragment = b'<g id="machine"><rect x="0" y="25" width="480" height="195" fill="#000000"/></g>'
        root = ET.fromstring(screen.compose(fragment))
        self.assertEqual([n.get('id') for n in root], ['bg', 'values', 'titles', 'machine'])
        for name in ('titles', 'values'):
            group = next(n for n in root if n.get('id') == name)
            self.assertEqual(len(group), 4)
            self.assertTrue(all(len(n) == 1 and n[0].tag == screen.NS + 'text' for n in group))

    def test_missing_control_and_wrong_dimensions_fail_closed(self):
        original = screen.template()
        root = ET.fromstring(original)
        root[1].remove(root[1][0])
        with self.assertRaisesRegex(ValueError, 'four values'):
            screen.validate_template(ET.tostring(root))
        with self.assertRaisesRegex(ValueError, 'dimensions'):
            screen.validate_template(original.replace(b'0 0 480 220', b'0 0 480 224'))

    def test_fragment_cannot_shadow_platform_controls(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate SVG binding IDs'):
            screen.compose(b'<g id="titles"/>')
