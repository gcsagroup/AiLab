'use strict';
const fs = require('node:fs');
const path = require('node:path');

const repo = 'anik-jha/qwen3.8-flash-next-24gb-gguf';
const assets = {
  main: {name:'Qwen3.8-Flash-Next-24GB-REAP25-UD-IQ4_XS.gguf',size:20287337760,sha256:'7a6476f315c28338287eb588e9113ea6965454c6014f047fbb2cc5faba473547'},
  ple_table: {name:'Qwen3.8-Flash-Next-ngram-table-IQ4_NL.gguf_file',size:28800138400,sha256:'ee0ee5f861fb2a86bfcb08a9d981fd21287eb397a5daad9ee6aa3dfe98420206'},
  recovery_lora: {name:'recovery-adapter/Qwen3.8-Flash-Next-24GB-REAP25-adapter.gguf',size:1916951840,sha256:'130c8a74f06e1ec79e7426ab2009b0c18cc8aac6b048cc03d7aec8f6e3610422'},
};
const roles = ['ple_table','recovery_lora'];
const variants = new Map([[repo,assets],['anik-jha/qwen3.8-flash-next-16gb-gguf',{
  main:{name:'Qwen3.8-Flash-Next-16GB-REAP25-IQ2_XXS.gguf',size:13045640480,sha256:'30985a6da954eb6419686d2fe70160c0f7123e3b1d63165899fa908f89ee1fa9'},
  ple_table:assets.ple_table,
  recovery_lora:{name:'recovery-adapter/Qwen3.8-Flash-Next-16GB-REAP25-adapter.gguf',size:1916951840,sha256:'5d059ee068c0e508dc887e5b35035f04394a933374d235f485f94b42839e25b9'},
}]]);
const incomplete = () => Error('此 Qwen3.8 REAP25 版本需要主权重、配套 n-gram 查找表和 recovery-adapter 中的 LoRA。请选择包含三份原始文件的发布目录。');
function companions(repoId, chosen, siblings) {
  const release=variants.get(repoId.toLowerCase());
  if (!release || chosen.path!==release.main.name) {
    if (!/(?:^|[\/._-])no[-_]ple(?:$|[\/._-])/i.test(chosen.path)) return [];
    const tables=siblings.filter(f=>/(?:^|\/)ple[-_].*\.gguf(?:_file)?$|[-_]ngram[-_]table[-_].*\.gguf(?:_file)?$/i.test(f.path));
    return tables.length===1 ? tables : [];
  }
  if (chosen.sha256!==release.main.sha256 || chosen.size!==release.main.size) throw incomplete();
  return roles.map(role=>{
    const expected=release[role];
    const member=siblings.find(f=>f.path===expected.name && f.sha256===expected.sha256 && f.size===expected.size);
    if (!member) throw incomplete();
    return member;
  });
}
function localFiles(selected) {
  const directory=fs.statSync(selected).isDirectory();
  const dir=directory ? selected : path.dirname(selected);
  const matches=[...variants.values()].filter(v=>directory ? fs.existsSync(path.join(dir,v.main.name)) : path.basename(selected)===v.main.name);
  if (!matches.length) return null;
  if (matches.length>1) throw Error('目录中有多个 Qwen REAP25 版本，请分别选择主权重文件。');
  return Object.values(matches[0]).map(({name,size})=>{
    const member=path.join(dir,name);
    if (!fs.existsSync(member) || !fs.statSync(member).isFile() || fs.statSync(member).size!==size ||
        fs.realpathSync(member).toLowerCase()!==path.join(fs.realpathSync(dir),name).toLowerCase()) throw incomplete();
    return member;
  });
}
function requiresBundle(info) { return info.arch==='qwen4exp' && [...variants.values()].some(v=>v.main.size===info.size); }
function match(entries) {
  const main=entries.find(e=>requiresBundle(e.info));
  if (!main) return null;
  const release=[...variants.values()].find(v=>v.main.size===main.info.size);
  const extra={};
  for (const role of roles) {
    const entry=entries.find(e=>e.info.arch===main.info.arch && e.info.size===release[role].size &&
      (role==='ple_table' ? e.info.pleOnly : e.info.lora));
    if (!entry) throw incomplete();
    extra[role]=entry.file;
  }
  if (entries.length!==3 || main.info.kind!=='text') throw incomplete();
  return {file:main.file,extra,info:{...main.info,reap25:true}};
}
function verifyLocal(digest, hashes) {
  const release=[...variants.values()].find(v=>v.main.sha256===digest);
  if (!release || roles.some(role=>hashes[role]!==release[role].sha256))
    throw Error('Qwen3.8 REAP25 的文件摘要与配套发布版本不符。');
}
module.exports={companions,localFiles,match,requiresBundle,incomplete,verifyLocal,assets};
