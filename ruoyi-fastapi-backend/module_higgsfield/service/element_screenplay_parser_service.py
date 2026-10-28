"""按显式剧本格式识别场景和对白角色；不猜测叙事正文中的隐含实体。"""
import re
from module_higgsfield.service.element_import_parser_service import ElementImportParserService as TableParser
from module_higgsfield.service.element_text_parser_service import ElementTextParserService as TextParser


class ElementScreenplayParserService:
    version = 'element-screenplay-v2'
    scene = re.compile(r'^(?:(?:第[0-9一二三四五六七八九十百]+场|\d+[.-]\d+)\s+)?'
        r'(?:(?:INT\.?/EXT\.?|INT\.?|EXT\.?|I/E)\s+|(?:内景|外景|内外景)\s*[:：.、\s]\s*)(.+)$', re.I)
    dialogue = re.compile(r'^([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9 _·.-]{0,39})'
        r'(?:[（(][^()（）\r\n]{1,40}[）)])?\s*[:：]\s*(.+)$')
    uppercase = re.compile(r'^[A-Z][A-Z0-9 ._-]{0,39}(?:\s*\((?:V\.O\.|O\.S\.|CONT\x27D)\))?$')
    non_speakers = {'旁白', '字幕', '说明', '备注', '时间', '地点', '镜头', '画外音', '转场', '音效', '音乐'}

    @classmethod
    def parse(cls, body, *, max_bytes, max_rows=10000, project_name='', include_project_name=False, markdown=False):
        TableParser.limits(body, max_bytes, max_rows)
        TableParser.options(project_name, include_project_name)
        try:
            content = body.decode('utf-8-sig')
        except UnicodeDecodeError:
            TableParser.fail(0, '文本必须使用UTF-8编码')
        if any(ord(c) < 32 and c not in '\t\r\n' for c in content):
            TableParser.fail(0, '文本包含不支持的控制字符')
        lines = content.splitlines()
        rows, current, description, fence = [], None, [], None
        in_script = False

        def finish():
            if current is None:
                return
            position, category, name = current
            rows.append(TableParser.candidate([name, name, category, '\n'.join(description).strip()],
                len(rows) + 1, {'line': position}, project_name=project_name, include_project_name=include_project_name))
            if len(rows) > max_rows:
                TableParser.fail(position, '候选数量超过限制')

        for index, original in enumerate(lines):
            line = original.strip()
            marker = re.match(r'^(`{3,}|~{3,})(.*)$', line) if markdown else None
            if fence or marker:
                if fence and marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                    fence = None
                elif not fence:
                    fence = marker[1]
                if current is not None:
                    description.append(original)
                continue
            heading = TextParser.heading.fullmatch(line)
            scene = cls.scene.fullmatch(line)
            dialogue = cls.dialogue.fullmatch(line) if in_script else None
            category, name, first_line = None, None, None
            if heading:
                category, name = TextParser.categories[heading[1]], heading[2]
                in_script = in_script or category == 'scene'
            elif scene:
                category, name = 'scene', scene[1].strip()
                first_line = original
                in_script = True
            elif dialogue and dialogue[1].strip() not in cls.non_speakers:
                category, name, first_line = 'character', dialogue[1].strip(), original
            elif in_script and cls.uppercase.fullmatch(line) and index + 1 < len(lines) and lines[index + 1].strip():
                # 标准全大写说话人必须位于空行后，避免将动作正文或转场识别为人物。
                if (index == 0 or not lines[index - 1].strip()) and line not in {'FADE IN', 'FADE OUT', 'CUT TO', 'THE END'}:
                    category, name = 'character', re.sub(r'\s*\((?:V\.O\.|O\.S\.|CONT\x27D)\)$', '', line)
            if category is not None:
                finish()
                current = (index + 1, category, name)
                description = [first_line] if first_line else []
            elif current is not None:
                description.append(original)
        if fence:
            TableParser.fail(0, 'Markdown代码围栏未闭合')
        finish()
        return TableParser.finish(rows)
