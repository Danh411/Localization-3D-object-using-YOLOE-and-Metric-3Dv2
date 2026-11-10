import hashlib,json,math,struct
from pathlib import Path
root=Path(__file__).resolve().parent
old=root/'kitchen_probe'
room=root/'kitchen_book_retry'
room.mkdir()
asset=root/'asset'/'single-book.glb'
blob=asset.read_bytes()
size,kind=struct.unpack_from('<I4s',blob,12)
doc=json.loads(blob[20:20+size])
node=doc['nodes'][27]
# Gazebo preserves the mesh's coordinates. Place the long local axis on world Z.
node['rotation']=[0,0,-math.sqrt(.5),math.sqrt(.5)]
node['translation']=[-.01136,0,.098335]
raw=json.dumps(doc,separators=(',',':')).encode()
raw+=b' '*(-len(raw)%4)
tail=blob[20+size:]
fixed=struct.pack('<4sII',b'glTF',2,20+len(raw)+len(tail))+struct.pack('<I4s',len(raw),kind)+raw+tail
dst=root/'asset'/'single-book-upright.glb'
dst.write_bytes(fixed)
(room/'asset_sha256.txt').write_text(hashlib.sha256(fixed).hexdigest()+'\n')
sdf=(old/'world.sdf').read_text()
assert 'single-book.glb' in sdf
(room/'world.sdf').write_text(sdf.replace('single-book.glb','single-book-upright.glb'))
cfg=json.loads((old/'design.json').read_text())
cfg['cases']=[{**c,'yaw_offset':90 if c['target']=='book_1' else 0} for c in cfg['cases'] if c['target'].startswith('book')]
(room/'design.json').write_text(json.dumps(cfg,indent=2)+'\n')
src=(root/'collect_kitchen.py').read_text()
(root/'collect_book.py').write_text(src.replace('math.radians(angle)]','math.radians(angle+case["yaw_offset"])]'))

