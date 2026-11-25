'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const {createHash,randomUUID} = require('node:crypto');

// Derived weights belong to the installed model. Publish the completed file in
// one filesystem operation so another trial can never open a partial layout.
async function cachedLayout(file, family, identity, expected, signal, build) {
  signal?.throwIfAborted();
  const before=await fs.stat(file);
  const key=createHash('sha256').update(JSON.stringify([path.basename(file),before.size,before.mtimeMs,identity]))
    .digest('hex').slice(0,24);
  const target=path.join(path.dirname(file),'.ailab-'+family+'-v1-'+key+'.prepared');
  async function existing() {
    try {
      const info=await fs.stat(target);
      if (!info.isFile() || (expected===undefined ? !info.size : info.size!==expected))
        throw Error('已准备的 '+family+' 权重长度异常。');
      return true;
    } catch(error) { if (error.code!=='ENOENT') throw error; return false; }
  }
  if (await existing()) return target;
  const partial=target+'.'+randomUUID()+'.tmp';
  try {
    await build(partial);
    signal?.throwIfAborted();
    const after=await fs.stat(file);
    if (after.size!==before.size || after.mtimeMs!==before.mtimeMs) throw Error('准备期间模型文件已更改。');
    if (expected!==undefined && (await fs.stat(partial)).size!==expected) throw Error('权重转换不完整。');
    try {await fs.link(partial,target);}
    catch (error) {if (error.code!=='EEXIST' || !await existing()) throw error;}
    return target;
  } finally {await fs.rm(partial,{force:true});}
}
module.exports={cachedLayout};
