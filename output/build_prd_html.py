from pathlib import Path
import re
import html
from markdown_it import MarkdownIt

root = Path('D:/laputta/higgsfield')
source = root / 'docs/AI图片与视频制作平台PRD-领导阅读版.md'
target = source.with_suffix('.html')
text = source.read_text(encoding='utf-8')

# 将原文流程节点绘制为内嵌矢量图，离线阅读不依赖外部脚本。
layouts = [
    {'P':(450,50),'A':(220,170),'B':(680,170),
     'A1':(220,290),'A2':(220,410),'A3':(220,530),'A4':(220,650),
     'B1':(680,290),'B2':(680,410),'B3':(680,530),'B4':(680,650),'B5':(680,770)},
    {'A':(450,50),'B':(450,160),'C':(450,270),'D':(450,380),
     'E':(210,500),'F':(690,500),'G':(690,610),'H':(450,730),
     'I':(450,840),'J':(210,960),'K':(690,960),'L':(210,1070),
     'M':(450,1190),'N':(450,1300),'O':(450,1410),'Q':(450,1520),
     'R':(210,1640),'S':(690,1640)},
    {'A':(450,50),'B':(210,180),'C':(690,180),'D':(690,310),
     'E':(690,440),'F':(210,440),'G':(450,580)},
    {'A':(450,50),'B':(450,160),'C':(450,270),'D':(450,380),
     'E':(450,490),'F':(180,600),'G':(600,600),'H':(600,710),
     'I':(600,820),'J':(600,930),'K':(270,1050),'L':(690,1050),'M':(690,1160)}
]
titles = ['平台功能全景','完整制作主路径','管理员准备路径','创作与结果保存路径']
graphs = re.findall(r'```mermaid\n(.*?)```', text, re.S)
assert len(graphs) == len(layouts)

def esc(value):
    return html.escape(str(value), quote=True)

def diagram(code, index):
    positions = layouts[index]
    labels = {m.group(1):m.group(2) or m.group(3) for m in re.finditer(r'\b([A-Z]\d*)\[([^\]]+)\]|\b([A-Z]\d*)\{([^}]+)\}', '')}
    labels = {}
    decisions = set()
    for m in re.finditer(r'\b([A-Z]\d*)(\[([^\]]+)\]|\{([^}]+)\})', code):
        labels[m.group(1)] = m.group(3) or m.group(4)
        if m.group(4):
            decisions.add(m.group(1))
    edges = []
    for line in code.splitlines():
        if '-->' not in line:
            continue
        left, right = line.strip().split('-->', 1)
        a = re.match(r'([A-Z]\d*)', left).group(1)
        label = ''
        if right.startswith('|'):
            _, label, right = right.split('|', 2)
        b = re.match(r'([A-Z]\d*)', right.strip()).group(1)
        edges.append((a,b,label))
    assert set(positions) == set(labels), (index, set(positions) ^ set(labels))
    height = max(y for x,y in positions.values()) + 80
    w,h = 226,68
    pieces = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 {height}" role="img" aria-labelledby="graph-title-{index}">',
      f'<title id="graph-title-{index}">{titles[index]}</title>',
      f'<defs><marker id="arrow{index}" markerWidth="9" markerHeight="9" refX="8" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#7890a9"/></marker></defs>']
    for n,(a,b,label) in enumerate(edges):
        x1,y1 = positions[a]; x2,y2 = positions[b]
        if index == 0 and a in ('A','B'):
            side = x1 - 150
            d = f'M{x1-w/2},{y1} H{side} V{y2} H{x2-w/2}'
            lx,ly = side,y2-10
        elif y2 < y1:
            side = 870 if index == 1 else 35
            direction = 1 if side > x1 else -1
            d = f'M{x1+direction*w/2},{y1} H{side} V{y2} H{x2+direction*w/2}'
            lx,ly = side,y2+35
        elif y1 == y2:
            d = f'M{x1+w/2},{y1} H{x2-w/2}'
            lx,ly = (x1+x2)/2,y1-10
        else:
            sy,ey = y1+h/2,y2-h/2
            mid = (sy+ey)/2
            # 主路径左右分支在空白行汇合。
            if index == 1 and a == 'E':
                d = f'M{x1},{sy} V{ey-20} H{x2} V{ey}'
            elif index == 1 and a == 'K':
                d = f'M{x1},{sy} V{ey-20} H{x2} V{ey}'
            else:
                d = f'M{x1},{sy} V{mid} H{x2} V{ey}'
            lx,ly = (x1+x2)/2,mid-8
        pieces.append(f'<path d="{d}" fill="none" stroke="#7890a9" stroke-width="2" marker-end="url(#arrow{index})"/>')
        if label:
            pieces.append(f'<text x="{lx}" y="{ly}" text-anchor="middle" font-size="14" fill="#526579" stroke="#fff" stroke-width="5" paint-order="stroke">{esc(label)}</text>')
    for node,(x,y) in positions.items():
        special = node in decisions
        fill,stroke = ('#fff6e5','#e1b35d') if special else ('#edf5fc','#b9d0e6')
        if node in ('P','A'):
            fill,stroke = '#173d62','#173d62'
        pieces.append(f'<rect x="{x-w/2}" y="{y-h/2}" width="{w}" height="{h}" rx="{24 if special else 12}" fill="{fill}" stroke="{stroke}"/>')
        value = labels[node]
        # 中文按字数分行，避免字号因长节点缩小。
        lines = [value[i:i+14] for i in range(0,len(value),14)]
        color = '#fff' if node in ('P','A') else '#173d62'
        for i,line in enumerate(lines):
            yy = y + (i-(len(lines)-1)/2)*22+6
            pieces.append(f'<text x="{x}" y="{yy}" text-anchor="middle" font-size="16" font-weight="500" fill="{color}">{esc(line)}</text>')
    pieces.append('</svg>')
    return f'<figure class="diagram"><figcaption><span>路径图 {index+1:02d}</span>{titles[index]}</figcaption>{"".join(pieces)}</figure>'

for i,code in enumerate(graphs):
    text = text.replace('```mermaid\n'+code+'```', f'\nPRDDIAGRAM{i}TOKEN\n',1)
md = MarkdownIt('commonmark', {'html':False}).enable('table')
body = md.render(text)
for i,code in enumerate(graphs):
    body = body.replace(f'<p>PRDDIAGRAM{i}TOKEN</p>', diagram(code,i))

toc=[]
def heading(match):
    level,label = match.group(1),match.group(2)
    ident = 'section-'+str(len(toc)+1)
    toc.append((level,ident,label))
    return f'<h{level} id="{ident}">{label}</h{level}>'
body = re.sub(r'<h([23])>(.*?)</h\1>',heading,body)
body = body.replace('<table>','<div class="table-scroll"><table>').replace('</table>','</table></div>')
nav=''.join(f'<a class="level-{level}" href="#{ident}">{label}</a>' for level,ident,label in toc)
css='''
:root{--ink:#1c3045;--muted:#61748a;--line:#dfe7ee;--accent:#176e8e;--paper:#fff;--bg:#f1f5f8}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:30px}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.85 "Microsoft YaHei","PingFang SC",system-ui,sans-serif}a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}.shell{max-width:1450px;margin:auto;display:grid;grid-template-columns:250px minmax(0,1fr);gap:34px;padding:36px 30px}aside{position:sticky;top:30px;align-self:start;max-height:calc(100vh - 60px);overflow:auto;padding:12px 6px}.brand{font-size:12px;letter-spacing:2px;font-weight:700;color:var(--accent);margin-bottom:18px}.nav-title{font-size:20px;font-weight:700;margin-bottom:18px}nav a{display:block;padding:5px 10px;font-size:13px;border-left:2px solid transparent;color:var(--muted)}nav .level-2{font-weight:700;color:var(--ink);margin-top:9px}nav .level-3{padding-left:23px}nav a:hover{background:#e4edf5;border-left-color:var(--accent);text-decoration:none}.actions{display:flex;gap:8px;margin-top:20px}button{border:1px solid var(--line);background:#fff;border-radius:8px;padding:9px 14px;color:var(--ink);font:inherit;font-size:13px;cursor:pointer}button:hover{border-color:var(--accent)}main{min-width:0;background:var(--paper);border:1px solid var(--line);border-radius:16px;padding:48px 54px;box-shadow:0 12px 45px #18334d06}.eyebrow{font-size:12px;font-weight:700;letter-spacing:3px;color:var(--accent)}h1{font-size:32px;line-height:1.5;margin:12px 0 20px;letter-spacing:-.5px}h1+p{font-size:13px;line-height:1.9;color:var(--muted);padding-bottom:24px;border-bottom:1px solid var(--line)}h2{font-size:24px;line-height:1.5;margin:52px 0 20px;padding-top:20px;border-top:1px solid var(--line)}h3{font-size:18px;margin:30px 0 14px}p{margin:14px 0}strong{font-weight:700;color:#174b6c}ul{padding-left:24px}li{margin:8px 0}.table-scroll{overflow-x:auto;margin:22px 0;border:1px solid var(--line);border-radius:10px}table{border-collapse:collapse;width:100%;font-size:13px;line-height:1.75;text-align:left}th{background:#edf3f8;color:#24435e;font-weight:700;white-space:nowrap}th,td{padding:12px 14px;border-bottom:1px solid var(--line);vertical-align:top}tr:last-child td{border-bottom:0}tr:nth-child(even) td{background:#fafcfe}td:first-child{min-width:70px}figure{margin:24px 0}.diagram{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:#fff;padding:18px 20px}figcaption{font-size:15px;font-weight:700;border-bottom:1px solid #edf2f6;padding-bottom:12px;margin-bottom:12px}figcaption span{font-size:11px;letter-spacing:1px;color:var(--accent);margin-right:14px}svg{display:block;width:100%;height:auto;font-family:"Microsoft YaHei","PingFang SC",sans-serif}.footer{border-top:1px solid var(--line);padding-top:18px;margin-top:32px;font-size:12px;color:var(--muted)}.mobile-toc{display:none}
@media(max-width:1050px){.shell{grid-template-columns:205px minmax(0,1fr);gap:18px;padding:20px 15px}main{padding:30px 28px}h1{font-size:27px}}
@media(max-width:760px){.shell{display:block;padding:10px}aside{display:none}main{padding:24px 18px;border-radius:10px}h1{font-size:24px}h2{font-size:21px}body{font-size:15px}.mobile-toc{display:block;border:1px solid var(--line);border-radius:8px;padding:10px;margin:18px 0}.diagram{padding:10px;overflow-x:auto}.diagram svg{min-width:600px}th,td{padding:9px}table{min-width:560px}}
@media print{@page{size:A4;margin:15mm}html{scroll-behavior:auto}body{background:#fff;font-size:10pt;line-height:1.65}.shell{display:block;max-width:none;padding:0}aside,.mobile-toc,.actions,.eyebrow{display:none}main{padding:0;border:0;box-shadow:none;border-radius:0}h1{font-size:23pt}h2{font-size:17pt;margin-top:24pt;break-after:avoid}h3{font-size:12pt;break-after:avoid}p,li{orphans:3;widows:3}.table-scroll{overflow:visible;border-radius:0}table{font-size:9pt;min-width:0}th,td{padding:6pt}thead{display:table-header-group}tr{break-inside:avoid}.diagram{break-inside:avoid;padding:8pt}.diagram svg{min-width:0;max-height:230mm;width:100%}a{color:inherit}*{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
'''
page=f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="AI图片与视频制作平台PRD：功能全景、操作路径、素材复用、创作与交付流程。"><title>AI图片与视频制作平台 PRD · 领导阅读版</title><style>{css}</style></head>
<body><div class="shell"><aside><div class="brand">HIGGSFIELD AI</div><div class="nav-title">产品需求说明书</div><nav aria-label="文档目录">{nav}</nav><div class="actions"><button onclick="window.print()">打印 / 保存 PDF</button></div></aside><main><div class="eyebrow">PRODUCT REQUIREMENTS · V1.0</div><details class="mobile-toc"><summary>查看文档目录</summary><nav>{nav}</nav><button onclick="window.print()">打印 / 保存 PDF</button></details>{body}<div class="footer">higgsfield-ai · 领导阅读版 · 2026年10月29日<br>流程图已内嵌，可离线阅读。附录中的相关文档链接需要与项目文档目录一同保留。</div></main></div></body></html>'''
target.write_text(page,encoding='utf-8')
assert '<script src=' not in page and 'PRDDIAGRAM' not in page
assert page.count('<svg ') == 4
print(f'已生成：{target}；大小：{target.stat().st_size} 字节；流程图：4；目录项：{len(toc)}')
