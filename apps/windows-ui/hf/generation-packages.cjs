'use strict';
const fs = require('node:fs');
const path = require('node:path');
const packages = require('./generation-packages.json');
const index = Object.entries(packages);
const mira = {kind:'audio',task:'tts',voiceRef:true,requiresReference:true,files:[{local:'mira-tts.gguf'}]};
function recipe(id,native=false) { return id === 'mira_tts' && native ? mira : packages[id]; }
function nativeAudio(id) {
  const spec = recipe(id,true);
  return spec?.kind==='audio' && spec.files.length===1 ? spec : undefined;
}
const keyOf = (id, i) => 'package_' + id + '__' + i;
// A quantization suffix can vary within one checkpoint. Keep the repository path,
// model size, instruction variant, and shard identity in the matching key.
function quantKey(name) {
  const m = /^(.*?)[._-](?:UD-)?(?:I?Q[1-8](?:[-_][A-Z0-9]+)*|BF16|F16|F32)\.gguf$/i.exec(name || '');
  return m && m[1].toLowerCase();
}
function componentName(role) {
  const match = /^package_([a-z0-9_.]+)__(\d+)$/.exec(role);
  if (!match || +match[2] < 1 || !packages[match[1]]?.files[+match[2]]) return null;
  const file = packages[match[1]].files[+match[2]];
  return 'component-' + match[2] + path.extname(file.path);
}
function makeRef(id, paths) {
  const row = packages[id];
  const extra = Object.fromEntries(paths.slice(1).map((file, i) => [keyOf(id, i + 1), file]));
  const info = {packageId:id, kind:row.kind, name:id, pipeline:row.kind === 'audio' ? 'audiocpp-' + row.task : 'diffusion-' + row.kind};
  if (row.kind === 'audio') Object.assign(info,{audioTask:row.task,audioFamily:row.family||id});
  return {file:paths[0],extra,info};
}
function matchingFile(dir, member) {
  for (const name of new Set([member.path,member.local,path.basename(member.path)])) {
    const file = path.resolve(dir, name);
    if (!file.startsWith(dir + path.sep)) continue;
    const stat = fs.statSync(file,{throwIfNoEntry:false});
    if (stat?.isFile() && stat.size === member.size && fs.realpathSync(file).toLowerCase() === file.toLowerCase()) return file;
  }
}
function localPackage(input, allowAlternate=false) {
  const isDir = fs.statSync(input).isDirectory();
  const dir = isDir ? input : path.dirname(input);
  const matches = [];
  const lists = new Map();
  for (const [id,row] of index) {
    const primary = row.files[0];
    const standardName = path.basename(primary.path);
    const key = quantKey(standardName);
    if (!isDir && path.basename(input) !== standardName && (!key || key!==quantKey(path.basename(input)))) continue;
    if (!isDir && ['lfm2_audio','lfm3_audio'].includes(row.family||id)) continue; // A bare language backbone still uses llama.cpp.
    let file = isDir || path.basename(input)===standardName ? matchingFile(dir,primary) : undefined;
    let alternate = false;
    if (!file && key && allowAlternate) {
      const candidates = new Set();
      for (const parent of new Set([dir,path.resolve(dir,path.dirname(primary.path))])) {
        if (!fs.statSync(parent,{throwIfNoEntry:false})?.isDirectory()) continue;
        if (isDir && !lists.has(parent)) lists.set(parent,fs.readdirSync(parent));
        for (const item of isDir ? lists.get(parent) : [path.basename(input)]) {
          if (item===standardName || quantKey(item)!==key) continue;
          const candidate=path.join(parent,item);
          if ((!isDir && candidate!==input) || fs.statSync(candidate,{throwIfNoEntry:false})?.isFile()!==true) continue;
          if (fs.realpathSync(candidate).toLowerCase()!==candidate.toLowerCase()) continue;
          candidates.add(candidate);
        }
      }
      if (candidates.size>1) throw Error('此目录含同一模型的多种量化，请选择其中一个主文件。');
      [file]=candidates;
      alternate=!!file;
    }
    if (!file || (!isDir && file !== input)) continue;
    const companions = row.files.slice(1).map(f=>matchingFile(dir,f));
    if (companions.every(Boolean)) {
      if (alternate) {
        const meta=require('./gguf-metadata.cjs').metadata(file);
        if ((row.family||id)==='sensenova_u1' && !meta.senseNovaImage) continue;
        if ((row.primaryArch && meta.arch!==row.primaryArch) ||
            (row.primaryAudioFamily && meta.audioFamily!==row.primaryAudioFamily) ||
            (meta.audioFamily && (row.kind!=='audio' || meta.audioFamily!==(row.primaryAudioFamily||row.family||id))) ||
            (row.kind==='audio' && row.files.length===1 && !meta.audioFamily && !(row.primaryArch && row.primaryArch===meta.arch)))
          throw Error('GGUF 内部架构或音频家族与这套配方的主模型不一致。');
      }
      matches.push({...makeRef(id,[file,...companions]), alternate});
    }
  }
  const exact=matches.filter(m=>!m.alternate);
  const candidates=exact.length ? exact : matches;
  // Several SDK precision presets may refer to identical companions and one unlisted quant.
  const unique=new Map(candidates.map(m=>[JSON.stringify([m.file,m.info.audioFamily||m.info.packageId,Object.values(m.extra)]),m]));
  if (unique.size > 1) throw Error('此目录含多套模型，请选择其中一套的主模型文件。');
  return unique.values().next().value || (!allowAlternate ? localPackage(input,true) : undefined);
}
async function checkHashes(ref, mainHash, extras) {
  const family = packages[ref.info.packageId];
  for (const [i, member] of family.files.entries()) {
    if (i===0 && ref.alternate) continue; // Import stores and rechecks this user's own GGUF digest.
    const role = keyOf(ref.info.packageId, i);
    if (member.sha256) {
      if ((i ? extras[role] : mainHash) !== member.sha256)
        throw Error('组件摘要与发行清单不符：' + member.path);
    } else {
      await require('./downloads.cjs').verify(i ? ref.extra[role] : ref.file, {...member, gitOid:member.git});
    }
  }
}
function stored(row) {
  const p = packages[row.generation_package];
  if (!p) throw Error('未登记的模型配方。');
  const paths = [row.path,...p.files.slice(1).map((_,i)=>path.join(path.dirname(row.path),componentName(keyOf(row.generation_package,i+1))))];
  return makeRef(row.generation_package,paths);
}
function catalogMatch(repo, filename, digest, manifest) {
  if (typeof repo !== 'string' || !digest) return;
  const inRepo=index.filter(([,r])=>r.files[0].repo.toLowerCase()===repo.toLowerCase());
  // A compact recipe can reuse an older recipe's primary with different encoders.
  // Downloads created before the update retain their original component digests.
  const entries=manifest ? inRepo.filter(([id,row])=>row.files.slice(1).every((f,i)=>
    manifest.some(m=>m.path==='components/'+componentName(keyOf(id,i+1)) && m.size===f.size &&
      (f.sha256 ? m.sha256===f.sha256 : m.gitOid===f.git)))) : inRepo;
  const exact=entries.find(([,r])=>r.files[0].path===filename && r.files[0].sha256===digest);
  if (exact || !quantKey(filename)) return exact;
  const other=entries.filter(([,r])=>r.files[0].path!==filename && quantKey(r.files[0].path)===quantKey(filename));
  if (!other.length || entries.some(([,r])=>r.files[0].path===filename)) return;
  const signature=([id,r])=>JSON.stringify([r.family||id,r.files.slice(1).map(f=>f.sha256||f.git)]);
  return other.every(e=>signature(e)===signature(other[0])) ? other[0] : undefined;
}
function planFiles(repo, selected, revision, manifest) {
  if (!selected) return;
  const found=catalogMatch(repo,selected.path,selected.sha256,manifest);
  if (!found) return;
  const assets=found[1].files.slice();
  if (assets[0].path!==selected.path) {
    if (!/^[0-9a-f]{40}$/.test(revision || '')) return;
    assets[0]={repo,rev:revision,...selected};
  }
  return assets.map((f,i)=>({
    path:i ? 'components/'+componentName(keyOf(found[0],i)) : f.path,
    size:f.size,sha256:f.sha256 || null,gitOid:f.git || null,
    url:'https://huggingface.co/'+f.repo+'/resolve/'+f.rev+'/'+f.path.split('/').map(encodeURIComponent).join('/')+'?download=true',
  }));
}
function convertiblePrimaries(repo, files) {
  return files.filter(f => /\.safetensors$/i.test(f.path) && catalogMatch(repo,f.path,f.sha256));
}
function sourceChoices(repo) {
  const upstream=repo.toLowerCase();
  return index.filter(([,r])=>r.upstreamRepo?.toLowerCase()===upstream || r.upstreamAliases?.some(id=>id.toLowerCase()===upstream))
    .sort((a,b)=>Number(!!a[1].imageReference)-Number(!!b[1].imageReference) || a[1].files[0].size-b[1].files[0].size)
    .map(([,row])=>row.files[0]);
}
function downloaded(job,dir) {
  if (job.format !== 'gguf') return;
  const main=job.files.find(f=>f.path===job.filename);
  const found=main && catalogMatch(job.repoId,job.filename,main.sha256,job.files);
  if (!found) return main && catalogMatch(job.repoId,job.filename,main.sha256) ? null : undefined;
  const [id,row]=found;
  const paths=row.files.map((f,i)=>{
    const part=i ? job.files.find(v=>v.size===f.size && (f.sha256?v.sha256===f.sha256:v.gitOid===f.git)) : main;
    return part && path.join(dir,part.path);
  });
  return paths.every(Boolean) ? makeRef(id,paths) : null;
}
module.exports={packages,recipe,nativeAudio,componentName,keyOf,localPackage,stored,checkHashes,planFiles,downloaded,convertiblePrimaries,sourceChoices};
