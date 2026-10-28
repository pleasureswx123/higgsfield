"""读取受限DOCX正文，保留段落顺序，不执行域、嵌入对象或外部关系。"""
import io
import zipfile
from xml.etree import ElementTree as ET


class DocxContentService:
    mime = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    word = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    document_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'

    @classmethod
    def paragraphs(cls, body, *, max_bytes):
        if not body or len(body) > max_bytes:
            raise ValueError('文档大小超限')
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            members = archive.infolist()
            names = [item.filename for item in members]
            if (len(members) > 10000 or len(names) != len(set(names))
                    or sum(item.file_size for item in members) > min(max_bytes * 10, 64 * 1024 * 1024)
                    or any(item.flag_bits & 1 for item in members)
                    or any(name.startswith('/') or '..' in name.split('/') or '\\' in name for name in names)
                    or any('vbaproject' in name.lower() or '/embeddings/' in name.lower() for name in names)):
                raise ValueError('文档包结构不支持')
            trees = {}
            for item in members:
                if not item.filename.lower().endswith(('.xml', '.rels')):
                    continue
                if item.file_size > 16 * 1024 * 1024:
                    raise ValueError('XML体积超限')
                content = archive.read(item)
                probe = content.replace(b'\x00', b'').upper()
                if b'<!DOCTYPE' in probe or b'<!ENTITY' in probe:
                    raise ValueError('不支持XML实体声明')
                root = ET.fromstring(content)
                if sum(1 for _ in root.iter()) > 200000:
                    raise ValueError('XML节点超限')
                if item.filename.endswith('.rels'):
                    for relation in root:
                        if relation.get('TargetMode', '').lower() == 'external' and not relation.get('Type', '').endswith('/hyperlink'):
                            raise ValueError('不支持外部文档内容')
                if item.filename in {'[Content_Types].xml', '_rels/.rels', 'word/document.xml'}:
                    trees[item.filename] = root
            types = trees.get('[Content_Types].xml')
            relations = trees.get('_rels/.rels')
            document = trees.get('word/document.xml')
            if (types is None or relations is None or document is None
                    or not any(item.get('PartName') == '/word/document.xml' and item.get('ContentType') == cls.document_type for item in types)
                    or not any(item.get('Type', '').endswith('/officeDocument') and item.get('Target') in {'word/document.xml', '/word/document.xml'} for item in relations)
                    or document.tag != f'{{{cls.word}}}document'):
                raise ValueError('不是支持的DOCX正文')
            body_node = document.find(f'{{{cls.word}}}body')
            if body_node is None:
                raise ValueError('缺少文档正文')
            if any(node.tag == f'{{{cls.word}}}altChunk' for node in body_node.iter()):
                raise ValueError('不支持外部合并正文')
            paragraphs = []
            # 按正文顺序读取表格和普通段落，排除修订删除内容、图形与文本框。
            ignored = {f'{{{cls.word}}}{name}' for name in ('del', 'drawing', 'object', 'pict', 'txbxContent')}
            stack = [body_node]
            while stack:
                node = stack.pop()
                if node.tag in ignored:
                    continue
                if node.tag == f'{{{cls.word}}}p':
                    fragments, pending = [], list(reversed(list(node)))
                    while pending:
                        child = pending.pop()
                        if child.tag in ignored:
                            continue
                        if child.tag == f'{{{cls.word}}}t':
                            fragments.append(child.text or '')
                        elif child.tag == f'{{{cls.word}}}tab':
                            fragments.append('\t')
                        elif child.tag in {f'{{{cls.word}}}br', f'{{{cls.word}}}cr'}:
                            fragments.append('\n')
                        else:
                            pending.extend(reversed(list(child)))
                    paragraphs.append(''.join(fragments))
                    if len(paragraphs) > 100000:
                        raise ValueError('正文段落超限')
                else:
                    stack.extend(reversed(list(node)))
            if not any(value.strip() for value in paragraphs):
                raise ValueError('正文没有可提取文本')
            return paragraphs
