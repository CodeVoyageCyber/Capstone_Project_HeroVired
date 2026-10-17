"""Rasterize this diagram using ImageMagick primitives; avoids SVG delegate differences."""
import math,re,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
p=Path(__file__).resolve().with_name('kind-architecture.svg')
root=ET.fromstring(p.read_text())
css=root.find('{http://www.w3.org/2000/svg}style').text
styles={c:dict(re.findall(r'([\w-]+):([^;]+)',body)) for c,body in re.findall(r'\.([\w-]+)\{([^}]+)\}',css)}
cmd=[]
def q(s): return "'"+s.replace('\\','\\\\').replace("'","\\'")+"'"
for e in list(root):
    tag=e.tag.split('}')[-1];a=e.attrib
    if tag not in ('rect','path','text'):continue
    if tag=='text':
        st=styles[a['class']]
        cmd.extend(['push graphic-context',f"fill {q(st.get('fill','#182b46'))}",'stroke none',f"font-size {st.get('font-size','19px').removesuffix('px')}",f"font-weight {st.get('font-weight','400')}",f"text {a['x']},{a['y']} {q(e.text or '')}",'pop graphic-context'])
        continue
    cmd.extend(['push graphic-context',f"fill {q(a.get('fill','none'))}",f"stroke {q(a.get('stroke','none'))}",f"stroke-width {a.get('stroke-width','1')}"])
    if 'stroke-dasharray' in a:cmd.append('stroke-dasharray '+a['stroke-dasharray'].replace(' ',','))
    if tag=='rect':
        x,y,w,h=[float(a.get(k,0)) for k in ['x','y','width','height']];r=a.get('rx','0')
        cmd.append(f'roundrectangle {x},{y} {x+w},{y+h} {r},{r}')
    else:cmd.append('path '+q(a['d']))
    cmd.append('pop graphic-context')
    if tag=='path' and 'marker-end' in a:
        pts=re.findall(r'[ML]([\d.]+) ([\d.]+)',a['d'])
        (x0,y0),(x1,y1)=[tuple(map(float,p)) for p in pts[-2:]]
        dx,dy=x1-x0,y1-y0;l=math.hypot(dx,dy);ux,uy=dx/l,dy/l
        bx,by=x1-11*ux,y1-11*uy
        cmd.extend(['push graphic-context','fill "#52627a"','stroke none',f'polygon {x1},{y1} {bx-5*uy},{by+5*ux} {bx+5*uy},{by-5*ux}','pop graphic-context'])
subprocess.run(['magick','-size','1920x1530','canvas:white','-font',('/System/Library/Fonts/Helvetica.ttc' if Path('/System/Library/Fonts/Helvetica.ttc').exists() else 'DejaVu-Sans'),'-draw','\n'.join(cmd),str(p.with_suffix('.png'))],check=True)
