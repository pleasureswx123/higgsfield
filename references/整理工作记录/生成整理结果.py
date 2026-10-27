from pathlib import Path
import csv,json,re,hashlib,shutil
from collections import Counter,defaultdict

src=Path(r'D:\laputta\higgsfield\references\Snipaste')
work=Path(r'D:\laputta\higgsfield\references\整理工作记录')
out=Path(r'D:\laputta\higgsfield\references\已整理')
items=json.loads((work/'清点.json').read_text(encoding='utf-8'))
records={}
for line in (work/'逐张观察.txt').read_text(encoding='utf-8-sig').splitlines():
 if not line.strip(): continue
 parts=line.split('|')
 assert len(parts)==8,(line,len(parts))
 idx,page,target,state,content,other,base,evidence=parts
 records[int(idx)]=dict(id=int(idx),page=page,target=target,state=state,content=content,other=other,base=int(base),evidence=evidence)
assert set(records)==set(range(1,len(items)+1))
# 全部查看后统一名称，并采用放大原图后的判断。
records[79]['content']='名称列右边界强调'
records[79]['evidence']='放大原图核对：Name列右边界亮线延伸至数据行；与080仅表头边界强调不同'
records[80]['evidence']='放大原图核对：Name表头右侧亮竖线，数据行右边界较暗'
records[200]['evidence']='放大原图核对：组图内部滚动条滑块靠上端，网格视图按钮白色'
records[201]['evidence']='放大原图核对：组图内部滚动条滑块位于中段，首排内容已有裁切'
# 让同一控件的默认状态、展开状态使用同名。
for i in [35,39,40,63]: records[i]['target']='视频生成参数栏'
for i in [4,7,133]:
 if i!=7: records[i]['target']='搜索框'
# 仅有同页其他视图时，不将其冒充同控件默认截图。
for i in [196,199,204,205,206,209,217,218,219]: records[i]['base']=0
records[109]['base']=132
records[124]['base']=132
records[127]['base']=125
records[129]['base']=125
records[130]['base']=125
records[152]['base']=0
records[171]['base']=0
records[172]['base']=0
records[173]['base']=0

out.mkdir(exist_ok=True)
# 任何已有输出都不能覆盖。
reserved=['截图状态对照表.csv','无法读取的截图.csv','文件校验表.csv','整理说明.txt']
for name in reserved:
 assert not (out/name).exists(),f'已有同名输出，停止以防覆盖：{name}'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def clean(s):
 return re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',s).replace('-','_').strip(' .')
counts=Counter();used=set();before={}
for item in items:
 r=records[item['id']]
 key=(r['page'],r['target'])
 counts[key]+=1
 seq=counts[key]
 while True:
  name='-'.join(clean(r[k]) for k in ['page','target','state','content'])+f'-{seq:02d}'+Path(item['file']).suffix
  if name.casefold() not in used and not (out/name).exists():break
  seq+=1
 counts[key]=seq;used.add(name.casefold());r['new']=name
 assert len(str(out/name))<260,str(out/name)
 before[item['file']]=sha(src/item['file'])

fields=['原文件名','新文件名','所属页面','目标区域或控件','主要状态','其他可见状态','对应默认状态截图','触发方式（已知或待确认）','识别依据','待确认事项']
rows=[];checks=[];hashgroups=defaultdict(list)
for item in items:
 r=records[item['id']]; base=records.get(r['base']);other=r['other'];pending=[]
 if r['state']=='默认':
  baseline='本图（当前内容或模式的静态基准）'
 elif base:
  baseline=base['new']
  if base['state'] not in ['默认','空内容']:
   pending.append('对应截图是同页或同控件的对比基准，亦含'+base['state']+'，不是完整初始状态')
 else:
  baseline='未提供可确定的同控件默认状态截图'
  pending.append('缺少可确定的同控件默认状态截图')
 if r['state'] in ['默认','空内容','页面滚动位置']:
  trigger='待确认（静态截图未记录到达此状态的操作）'
 else:
  trigger='触发方式待确认（静态截图无法区分悬停、点击或其他触发）'
 if r['state']=='触发方式待确认':
  pending.append('仅确认高亮、边界或操作按钮的可见变化；Hover、聚焦、点击激活等触发需后续验证')
 if r['state']=='Tooltip':
  pending.append('已按简短说明气泡外观归类Tooltip；是否由鼠标悬停触发待确认')
 if r['state'] in ['弹出菜单','弹出面板','弹窗']:
  pending.append('浮层按位置、内容和遮罩分类；触发方式及关闭行为待确认')
 if r['state']=='页面滚动位置':
  if r['id'] in [200,201]: pending.append('滚动位置指组图内部容器，不指整页')
  if r['id'] in [171,172]:pending.append('本组未提供角色权限页最顶部；序号只表示已见区域从上到下')
 if r['id'] in [110,111,112,113,114,115,116,117,118,119,120,121,122,123]:
  other+='；左侧预览空白（无明确加载标识）'
  pending.append('预览空白原因待确认，不能证明正在加载')
 if r['id'] in [41,52,53]:pending.append('局部裁切限制浮层边界判断；面板类型需结合实现复核')
 if r['id'] in [145,146,147,148,149,150,151,152,153,154,155,156,157,158,177,195,200,201,202,203,207,208,210]:
  other+='；右侧信息或分类侧栏可见（抽屉性质待确认）'
  pending.append('右侧面板只有展开外观，缺少收起对照，不能确认是侧边抽屉')
 if r['id']==144:pending.append('红字为截图标注，不能作为触发方式已知的证据')
 if r['id'] in [207,208]:pending.append('暂停按钮与进度仅证明截图时播放器状态；不推断实际播放过程')
 if r['id']==219:pending.append('英文目录名按截图可见拼写记录')
 if r['id'] in [79,80,200,201]:other+='；已放大原图复查'
 if '疑似' in other or '待确认' in r['evidence']:pending.append('疑似焦点或局部细节需结合交互验证')
 # 只复制字节，不重新编码；独占创建防止并发覆盖。
 with (src/item['file']).open('rb') as f,(out/r['new']).open('xb') as g:
  shutil.copyfileobj(f,g)
 shutil.copystat(src/item['file'],out/r['new'])
 digest=sha(out/r['new'])
 assert digest==before[item['file']]
 assert sha(src/item['file'])==before[item['file']]
 hashgroups[digest].append(item['id'])
 rows.append(dict(zip(fields,[item['file'],r['new'],r['page'],r['target'],r['state'],other.strip('；') or '未见其他明确状态',baseline,trigger,r['evidence'],'；'.join(dict.fromkeys(pending)) or '未见其他待确认项；不推断未展示的交互'])))
 checks.append({'原文件名':item['file'],'新文件名':r['new'],'原文件SHA256':before[item['file']],'复制文件SHA256':digest,'字节数':(src/item['file']).stat().st_size,'校验结果':'一致；原文件保留'})

def write_csv(path,cols,data):
 with path.open('x',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(data)
write_csv(out/'截图状态对照表.csv',fields,rows)
write_csv(out/'文件校验表.csv',list(checks[0]),checks)
write_csv(out/'无法读取的截图.csv',['原文件名','原因'],[])
write_csv(work/'分批查看进度.csv',['批次','编号范围','截图数','查看结果'],[{'批次':i+1,'编号范围':f'{i*6+1:03d}—{min(i*6+6,len(items)):03d}','截图数':min(6,len(items)-i*6),'查看结果':'已逐张查看并与同页截图比较；记录见逐张观察.txt'} for i in range((len(items)+5)//6)])
summary={'原图数':len(items),'已查看':len(records),'已复制':len(rows),'不可读取':0,'哈希一致':len(checks),'重复内容组':[v for v in hashgroups.values() if len(v)>1],'状态分布':dict(Counter(r['state'] for r in records.values())),'页面分布':dict(Counter(r['page'] for r in records.values()))}
(work/'最终分类.json').write_text(json.dumps(list(records.values()),ensure_ascii=False,indent=2),encoding='utf-8')
(work/'校验结果.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
with (out/'整理说明.txt').open('x',encoding='utf-8-sig') as f:
 f.write('截图整理说明\n\n')
 f.write(f'共清点并查看 {len(items)} 张截图，分 37 批完成；全部可读取并已复制，219 对文件 SHA-256 一致。原文件未改动、未删除，重复图全部保留。\n\n')
 f.write('命名：页面名称-目标区域或控件-状态类型-具体内容-序号.原扩展名。序号在同页面、同目标区域内编号；已确认的滚动区域按从上到下编号，其他编号仅作区分，不代表操作顺序。文件名内容中的原有连字符替换为下划线，以免混淆字段。\n\n')
 f.write('页面范围：“首页”“我的项目”“我的生成”“我的元素”指 Cinema Studio 对应区域；“项目素材”“项目设置”“项目元素”“项目简报”指 project-1；Cully Hill Boys 示例项目单独命名。“元素详情”是大图查看界面，不能仅凭截图确认它是独立路由还是全屏覆盖层。\n\n')
 f.write('浮层区分：带背景遮罩和独立表单的居中窗口记为弹窗；选项或操作列表记为弹出菜单；无整页遮罩的素材选择、滑块设置等记为弹出面板；简短说明气泡记为Tooltip；Toast单列为提示消息。右侧常驻面板不直接认定为抽屉。\n\n')
 f.write('Hover与抽屉：本组静态截图没有足够证据确认触发方式或侧边展开过程。卡片遮罩、按钮显现、行高亮等采用“触发方式待确认”，并在表中说明可见外观；Tooltip按气泡外观分类，其触发方式仍待确认。未为了覆盖类型而虚构Hover或抽屉。\n\n')
 f.write('加载与禁用：Uploading、Extracting elements具有明确文字，记为加载；空白预览没有加载标识，记为预览空白。灰显按钮及其他可见状态在表中单独记录。不推断动画、实际点击结果或后台行为。\n\n')
 f.write('默认对应：优先提供同页面同控件未展开的基准文件名；没有合适默认截图时明确写“未提供”，不将其他模式冒充默认。有些对比基准本身是弹窗或选中状态，待确认事项会注明。基准之间可能存在项目名称、内容数量和参数变化，关联仅说明界面结构，不证明因果或操作顺序。\n\n')
 f.write('滚动：项目设置按内容位置区分顶部、中部、底部；街景组图的滚动位置指组图容器。其他没有可靠证据的位置不推断。\n\n')
 f.write('文件：截图状态对照表.csv为10列完整映射；文件校验表.csv为逐文件SHA-256证据；无法读取的截图.csv仅含表头，表示本次无读取失败。CSV使用UTF-8 BOM，便于Windows Excel读取中文。原图已有的红框、红字和裁切全部原样保留。\n\n')
 f.write('批次记录和临时对比图位于同级“整理工作记录”目录；未编写或修改网站。\n\n')
 f.write('状态数量：\n'+ '\n'.join(f'{k}：{v}' for k,v in summary['状态分布'].items()))
 f.write('\n\n重复内容组（清点编号；已全部保留）：'+str(summary['重复内容组'])+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
