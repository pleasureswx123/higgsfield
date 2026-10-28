"""明确分类的文本剧本候选解析，不执行Markdown、代码块或外部引用。"""
import re
from module_higgsfield.service.element_import_parser_service import ElementImportParserService as TableParser


class ElementTextParserService:
    version = 'element-text-v1'
    heading = re.compile(r'^(?:#{1,6}\s+)?(角色|人物|场景|道具|其他)\s*[:：]\s*(.*?)\s*$')
    categories = {'角色': 'character', '人物': 'character', '场景': 'scene', '道具': 'prop', '其他': 'other'}

    @classmethod
    def parse(cls, body, *, max_bytes, max_rows=10000, project_name='', include_project_name=False,
              markdown=False):
        TableParser.limits(body, max_bytes, max_rows)
        TableParser.options(project_name, include_project_name)
        try:
            content = body.decode('utf-8-sig')
        except UnicodeDecodeError:
            TableParser.fail(0, '文本必须使用UTF-8编码')
        if any(ord(char) < 32 and char not in '\t\r\n' for char in content):
            TableParser.fail(0, '文本包含不支持的控制字符')
        rows, current, description = [], None, []
        fence = None

        def finish():
            if current is None:
                return
            line, category, name = current
            rows.append(TableParser.candidate([name, name, category, '\n'.join(description).strip()],
                len(rows) + 1, {'line': line}, project_name=project_name,
                include_project_name=include_project_name))
            if len(rows) > max_rows:
                TableParser.fail(line, '候选数量超过限制')

        for line_no, original in enumerate(content.splitlines(), 1):
            stripped = original.strip()
            # 代码围栏中的分类标记只是描述，不作为新元素；从不渲染或执行正文。
            marker = re.match(r'^(`{3,}|~{3,})(.*)$', stripped) if markdown else None
            if fence:
                if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                    fence = None
                if current is not None:
                    description.append(original)
                continue
            if marker:
                fence = marker[1]
                if current is not None:
                    description.append(original)
                continue
            match = cls.heading.fullmatch(stripped)
            if match:
                finish()
                current = (line_no, cls.categories[match[1]], match[2])
                description = []
            elif current is not None:
                description.append(original)
        if fence:
            TableParser.fail(0, 'Markdown代码围栏未闭合')
        finish()
        return TableParser.finish(rows)
