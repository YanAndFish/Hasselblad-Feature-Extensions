"""只读用户授权 JPEG 像素；不导出 EXIF；生成离线分组联系表。"""
from pathlib import Path
import hashlib,json
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[4]
SRC=ROOT/'x1d/references/af-samples/20260912/219HASBL'
OUT=ROOT/'x1d/af-experiment/camera-settings-r1/build/sample-analysis-20260912'
OUT.mkdir(parents=True,exist_ok=True)
paths=sorted(SRC.glob('*.JPG'));assert len(paths)==18
sheet=Image.new('RGB',(4*360,5*300),'#202020');d=ImageDraw.Draw(sheet);records=[]
for i,p in enumerate(paths):
    original=p.read_bytes();digest=hashlib.sha256(original).hexdigest()
    with Image.open(p) as im:
        size=im.size;im=im.convert('RGB');im.thumbnail((344,258))
        x=(i%4)*360+8;y=(i//4)*300+26;sheet.paste(im,(x,y));d.text((x,y-20),p.stem,fill='white')
        w,h=im.size;d.rectangle((x+w*.455,y+h*.44,x+w*.545,y+h*.56),outline='red',width=2)
    records.append({'file':p.name,'sha256':digest,'bytes':len(original),'size':size})
sheet.save(OUT/'contact.png')
(OUT/'sources.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
print(OUT/'contact.png')
