'use strict';
const { spawn } = require('node:child_process');
const { createInterface } = require('node:readline');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');

// A workbench selection owns one process. The trial queue serializes its users.
class ResidentText {
  async connect(key, launch, signal) {
    signal?.throwIfAborted();
    if (this.process?.key !== key) {
      await this.stop();
      signal?.throwIfAborted();
      const ready = Promise.withResolvers(), hold = Promise.withResolvers();
      const controller = new AbortController();
      const process = { key, controller, hold };
      this.process = process;
      process.ready = ready.promise;
      process.closed = launch(controller.signal, handle => {
        ready.resolve(handle);
        return hold.promise;
      }).catch(error => ready.reject(error)).finally(() => {
        if (this.process === process) this.process = null;
      });
    }
    const current = this.process;
    const cancel = () => { current.controller.abort(); current.hold.resolve(); };
    signal?.addEventListener('abort', cancel, { once:true });
    try { return await current.ready; }
    finally { signal?.removeEventListener('abort', cancel); }
  }
  async stop() {
    const current = this.process;
    if (current) {
      current.controller.abort(); current.hold.resolve();
      await current.closed;
    }
  }
  async directory() {
    return this.dir ??= await fs.mkdtemp(path.join(os.tmpdir(),'ailab-text-model-'));
  }
  async close() {
    await this.stop();
    if (this.dir) await fs.rm(this.dir, { recursive:true, force:true });
  }
}

async function nativeSession(exe, env, input, signal, ready) {
  signal.throwIfAborted();
  const child = spawn(exe, [], {cwd:path.dirname(exe), env, windowsHide:true, stdio:['pipe','pipe','pipe']});
  const loaded = Promise.withResolvers(), closed = Promise.withResolvers();
  let pending, tail = '', failure;
  const kill = () => child.kill();
  signal.addEventListener('abort', kill, {once:true});
  child.stdin.on('error', () => {});
  child.stderr.on('data', chunk => { tail = (tail + chunk.toString()).slice(-4000); });
  child.on('error', error => { failure = error; });
  child.once('close', () => {
    const error = signal.aborted ? Error('模型已卸载。') : Error([failure?.message,tail.trim()].filter(Boolean).join('\n') || '模型进程已退出。');
    loaded.reject(error); pending?.reject(error); closed.resolve();
  });
  createInterface({input:child.stdout,crlfDelay:Infinity}).on('line', line => {
    try {
      const e = JSON.parse(line);
      if (e.type==='error') throw Error(e.message);
      if (e.type==='ready') loaded.resolve();
      else if (e.type==='request_complete') { pending?.resolve(); pending=undefined; }
      else pending?.event(e);
    } catch (error) { failure=error; kill(); }
  });
  function send(request,event,abort) {
    abort?.throwIfAborted();
    if (child.exitCode!==null || child.killed || pending) throw Error('模型进程不可用。');
    const reply=Promise.withResolvers();
    pending={...reply,event};
    abort?.addEventListener('abort',kill,{once:true});
    child.stdin.write(JSON.stringify(request)+'\n');
    return reply.promise.finally(()=>abort?.removeEventListener('abort',kill));
  }
  try {
    child.stdin.write(JSON.stringify({...input,action:'preload'})+'\n');
    await loaded.promise;
    await Promise.race([ready(send),closed.promise]);
  } finally { signal.removeEventListener('abort',kill); kill(); await closed.promise; }
}
module.exports={ResidentText,nativeSession};
