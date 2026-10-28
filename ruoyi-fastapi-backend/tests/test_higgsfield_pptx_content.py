"""PPTX包和页序约束，不把ZIP扩展名视为有效文档。"""
import io
import unittest
import zipfile
from module_higgsfield.service.pptx_content_service import PptxContentService as Service


def document(extra=None, order=('two', 'one')):
    p, a, r = Service.presentation, Service.drawing, Service.relationships
    files = {
        '[Content_Types].xml': f'<Types><Override PartName="/ppt/presentation.xml" ContentType="{Service.main_type}"/></Types>',
        '_rels/.rels': f'<Relationships><Relationship Id="main" Type="{r}/officeDocument" Target="ppt/presentation.xml"/></Relationships>',
        'ppt/presentation.xml': f'<p:presentation xmlns:p="{p}" xmlns:r="{r}"><p:sldIdLst>' + ''.join(f'<p:sldId r:id="{key}"/>' for key in order) + '</p:sldIdLst></p:presentation>',
        'ppt/_rels/presentation.xml.rels': f'<Relationships><Relationship Id="one" Type="{r}/slide" Target="slides/slide1.xml"/><Relationship Id="two" Type="{r}/slide" Target="slides/slide2.xml"/></Relationships>',
        'ppt/slides/slide1.xml': f'<p:sld xmlns:p="{p}" xmlns:a="{a}"><a:t>第一页</a:t></p:sld>',
        'ppt/slides/slide2.xml': f'<p:sld xmlns:p="{p}" xmlns:a="{a}"><a:t>第二页</a:t></p:sld>',
    }
    files.update(extra or {})
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return out.getvalue()


class PptxContentTests(unittest.TestCase):
    def test_relationship_order_not_filename_order(self):
        self.assertEqual(Service.slides(document(), max_bytes=100000), ['第二页', '第一页'])

    def test_unsafe_packages_and_invalid_relations(self):
        for body in [b'fake', document({'ppt/vbaProject.bin': b'macro'}), document({'ppt/embeddings/item.bin': b'object'}),
                     document({'../escape.xml': '<x/>'}), document({'ppt/slides/slide1.xml': '<!DOCTYPE x [<!ENTITY y "x">]><x>&y;</x>'}),
                     document(order=('one', 'one')), document(order=('missing',)), document(order=()),
                     document({'ppt/_rels/presentation.xml.rels': f'<Relationships><Relationship Id="two" Type="{Service.relationships}/slide" Target="https://example.com/a" TargetMode="External"/></Relationships>'})]:
            with self.subTest(size=len(body)), self.assertRaises((ValueError, zipfile.BadZipFile)):
                Service.slides(body, max_bytes=100000)
        with self.assertRaises(ValueError):
            Service.slides(document(), max_bytes=10)
