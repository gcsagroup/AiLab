from pathlib import Path
import base64
p=Path(__file__).parent
h=p/'ailab-unified.html'
s=h.read_text()
assets=[]
for variable,name,mime in [('demoImage','ailab-product-demo.jpg','image/jpeg'),('demoVoice','ailab-voice-demo.wav','audio/wav'),('demoMusic','ailab-tone-demo.wav','audio/wav')]:
    assets.append(f'const {variable}="data:{mime};base64,'+base64.b64encode((p/name).read_bytes()).decode()+'";')
code='\n'.join(assets)+'\n'+(p/'ailab-unified-state.js').read_text()+'\n'+(p/'ailab-runtime-state.js').read_text()+'\n'+(p/'ailab-runtime-ui.js').read_text()+'\n'+(p/'ailab-unified-ui.js').read_text()
a=s.index('<script>');b=s.rindex('</script>')
s=s[:a]+'<script>\n'+code+'\n'+s[b:]
a=s.find('<style data-unified>')
if a>=0:
    b=s.index('</style>',a)+8
    s=s[:a]+s[b:]
s=s.replace('<script>','<style data-unified>\n'+(p/'ailab-unified-extra.css').read_text()+'\n</style>\n<script>',1)
assert len(s.encode())<1000000
assert '<html' not in s and '<body' not in s
h.write_text(s)
print('整合版原型已生成：',len(s.encode()),'字节')
