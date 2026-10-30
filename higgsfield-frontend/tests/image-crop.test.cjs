const {test}=require('node:test'),assert=require('node:assert/strict')
const {readFileSync}=require('node:fs'),{join}=require('node:path'),{runInNewContext}=require('node:vm'),ts=require('typescript')
const exportsObject={}
runInNewContext(ts.transpileModule(readFileSync(join(__dirname,'../src/utils/imageCrop.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{exports:exportsObject})
const {changeCrop,cropPixels}=exportsObject
const plain=x=>JSON.parse(JSON.stringify(x))
test('拖动边界裁剪框不能离开原图',()=>{
 assert.deepEqual(plain(changeCrop({x:.2,y:.3,width:.5,height:.4},'move',9,-9)),{x:.5,y:0,width:.5,height:.4})
})
test('八个缩放手柄保留最小范围，不翻转和越界',()=>{
 for(const handle of ['n','s','e','w','nw','ne','sw','se'])for(const delta of [-9,9]){
  const box=changeCrop({x:.2,y:.3,width:.5,height:.4},handle,delta,delta)
  assert.ok(box.x>=0&&box.y>=0&&box.x+box.width<=1.000001&&box.y+box.height<=1.000001)
  assert.ok(box.width>=.019999&&box.height>=.019999)
 }
})
test('按原图像素裁剪，边缘舍入不产生额外像素',()=>{
 assert.deepEqual(plain(cropPixels({x:.25,y:.25,width:.5,height:.5},2048,1152)),{x:512,y:288,width:1024,height:576})
 assert.deepEqual(plain(cropPixels({x:.999,y:.999,width:.001,height:.001},101,51)),{x:100,y:50,width:1,height:1})
})
