"""受限 PPTX 文本读取，按演示文稿页序解析，不执行嵌入对象。"""
import io
import posixpath
import zipfile
from xml.etree import ElementTree as ET


class PptxContentService:
    mime = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
    presentation = 'http://schemas.openxmlformats.org/presentationml/2006/main'
    drawing = 'http://schemas.openxmlformats.org/drawingml/2006/main'
    relationships = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    main_type = 'application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml'

    @classmethod
    def slides(cls, body, *, max_bytes):
        if not body or len(body) > max_bytes:
            raise ValueError('演示文稿大小超限')
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            members = archive.infolist(); names = [item.filename for item in members]
            if (len(members) > 10000 or len(names) != len(set(names))
                or sum(item.file_size for item in members) > min(max_bytes * 10, 64 * 1024 * 1024)
                or any(item.flag_bits & 1 for item in members)
                or any(name.startswith('/') or '..' in name.split('/') or '\\' in name for name in names)
                or any('vbaproject' in name.lower() or '/embeddings/' in name.lower() or '/activex/' in name.lower() for name in names)):
                raise ValueError('演示文稿包结构不支持')
            trees = {}
            for member in members:
                if not member.filename.lower().endswith(('.xml', '.rels')):
                    continue
                if member.file_size > 16 * 1024 * 1024:
                    raise ValueError('XML体积超限')
                data = archive.read(member)
                probe = data.replace(b'\x00', b'').upper()
                if b'<!DOCTYPE' in probe or b'<!ENTITY' in probe:
                    raise ValueError('不支持XML实体')
                tree = ET.fromstring(data)
                if sum(1 for _ in tree.iter()) > 200000:
                    raise ValueError('XML节点超限')
                if member.filename.endswith('.rels'):
                    identities = [item.get('Id') for item in tree]
                    if None in identities or len(identities) != len(set(identities)):
                        raise ValueError('关系标识无效')
                    for relation in tree:
                        if relation.get('TargetMode', '').lower() == 'external' and not relation.get('Type', '').endswith('/hyperlink'):
                            raise ValueError('不支持外部演示内容')
                trees[member.filename] = tree
            types = trees.get('[Content_Types].xml'); root_rels = trees.get('_rels/.rels')
            presentation = trees.get('ppt/presentation.xml'); relations = trees.get('ppt/_rels/presentation.xml.rels')
            if (types is None or root_rels is None or presentation is None or relations is None
                or presentation.tag != f'{{{cls.presentation}}}presentation'
                or not any(item.get('PartName') == '/ppt/presentation.xml' and item.get('ContentType') == cls.main_type for item in types)
                or not any(item.get('Type', '').endswith('/officeDocument') and item.get('Target') in {'ppt/presentation.xml', '/ppt/presentation.xml'} for item in root_rels)):
                raise ValueError('不是支持的PPTX演示文稿')
            links = {item.get('Id'): item for item in relations}
            pages = presentation.findall(f'{{{cls.presentation}}}sldIdLst/{{{cls.presentation}}}sldId')
            if not 1 <= len(pages) <= 200:
                raise ValueError('演示页数超限或为空')
            result, seen, total = [], set(), 0
            for page in pages:
                identity = page.get(f'{{{cls.relationships}}}id')
                relation = links.get(identity)
                if identity in seen or relation is None or not relation.get('Type', '').endswith('/slide'):
                    raise ValueError('演示页关系无效')
                seen.add(identity)
                target = relation.get('Target', '')
                if '\\' in target or ':' in target or relation.get('TargetMode', '').lower() == 'external':
                    raise ValueError('演示页目标无效')
                path = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join('ppt', target))
                slide = trees.get(path)
                if not path.startswith('ppt/slides/') or slide is None or slide.tag != f'{{{cls.presentation}}}sld':
                    raise ValueError('演示页内容缺失')
                paragraphs = [''.join(node.itertext()) for node in slide.iter(f'{{{cls.drawing}}}t')]
                content = '\n'.join(paragraphs)
                total += len(content)
                if total > 2000000:
                    raise ValueError('演示文本超限')
                result.append(content)
            return result
