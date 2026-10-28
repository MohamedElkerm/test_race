"""Native-source raster QA, separate from full-template visual approval."""
from pathlib import Path
from PIL import Image,ImageChops
import json
from results_backend.store import ROOT

checks=[]
for p in sorted((ROOT/'assets_original/tga').rglob('*.tga')):
 q=ROOT/'assets_processed/sfs'/(p.stem.lower().replace(' ','_')+'.png')
 a=Image.open(p).convert('RGBA');b=Image.open(q).convert('RGBA');equal=a.size==b.size and a.tobytes()==b.tobytes()
 assert equal,p.name
 checks.append({'asset':str(p.relative_to(ROOT)),'size':list(a.size),'mode':'RGBA','lossless_png_conversion':equal})
for p in sorted((ROOT/'assets_original/common').rglob('*.tga')):
 if '/HD/MEDIUM/' not in str(p):continue
 q=ROOT/'assets_processed/flags'/(p.stem.upper()+'.png');a=Image.open(p).convert('RGBA');b=Image.open(q).convert('RGBA')
 assert a.size==b.size and a.tobytes()==b.tobytes(),p.name
 checks.append({'asset':str(p.relative_to(ROOT)),'size':list(a.size),'mode':'RGBA','lossless_png_conversion':True})
# Compare native FISU logo, left pictogram area and footer to actual browser pixels.
render=Image.open(ROOT/'screenshots/tvg/SFS206.png').convert('RGBA')
expected=Image.new('RGBA',(1920,1080));bg=Image.open(ROOT/'assets_processed/sfs/header2_lines.png').convert('RGBA');pict=Image.open(ROOT/'assets_processed/sfs/sfs_2.png').convert('RGBA');expected.alpha_composite(bg,(522,946));expected.alpha_composite(pict,(522,946))
regions=[]
for name,box in [('native_pictogram',(522,946,650,1025)),('native_FISU_logo',(1240,946,1392,982))]:
 a=expected.crop(box);b=render.crop(box);opaque=[(x,y) for y in range(a.height) for x in range(a.width) if a.getpixel((x,y))[3]==255]
 ds=[max(abs(a.getpixel((x,y))[k]-b.getpixel((x,y))[k]) for k in range(4)) for x,y in opaque]
 regions.append({'region':name,'box':box,'opaque_pixels':len(ds),'max_channel_delta':max(ds),'pixels_delta_over_2':sum(v>2 for v in ds),'status':'PASS' if max(ds)<=2 else 'REVIEW'})
assert all(r['status']=='PASS' for r in regions),regions
report={'status':'COMPLETED','lossless_source_derivatives_checked':len(checks),'assets':checks,'browser_static_regions':regions,'fully_matched_templates':0,'note':'Source derivative fidelity and selected static regions only. These checks do not approve per-template field geometry, dynamic typography, missing backgrounds or FISU match.'}
(ROOT/'testing/reports/visual_assets.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='assets'},indent=2))
