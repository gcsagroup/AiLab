'use strict';
const os = require('node:os');
const path = require('node:path');

function gpuBackend(id) {
  if (typeof id === 'string' && /^CUDA\d+$/.test(id)) return 'cuda';
  if (typeof id === 'string' && /^Vulkan\d+$/.test(id)) return 'vulkan';
  throw Error('请选择设备列表中的 CPU、CUDA 或 Vulkan GPU。');
}

function deviceExecutable(executable, id) {
  return id?.startsWith('CUDA') ? path.join(path.dirname(executable), 'cuda', path.basename(executable)) : executable;
}

// The standard CUDA 12 build ships PTX for these architectures. The paired
// Unsloth build includes native kernels and uses its own llama, mtmd and GGML DLLs.
function textExecutable(executable, runtime) {
  if (runtime?.device_id?.startsWith('CUDA') && ['7.0', '7.5', '8.0'].includes(runtime.cuda_compute_capability)
      && path.basename(executable) !== 'plm-worker.exe')
    return path.join(path.dirname(executable), 'native-kernels', 'cuda', path.basename(executable));
  return deviceExecutable(executable, runtime?.device_id);
}

function logicalProcessors() {
  return os.cpus().length || os.availableParallelism();
}

function trialThreads(runtime) {
  return !runtime.device_id || runtime.device_id === 'cpu' ? runtime.cpu_threads ?? logicalProcessors() : 4;
}

// The audio CLI numbers devices within each backend. Verify its inventory before
// using that number; the language and diffusion workers use GGML names instead.
async function audioDevices(invoke, engine) {
  let inventory;
  await invoke(engine, ['--list-devices', '--json'], { timeout: 15000, onLine(line) {
    if (line.trim().startsWith('{')) inventory = JSON.parse(line).devices;
  } });
  if (!Array.isArray(inventory)) throw Error('音频执行器未返回设备列表。');
  return inventory;
}

async function audioDeviceIndex(invoke, engine, device) {
  const inventory = await audioDevices(invoke, engine);
  const name = device.name.replace(/ · [^·]+$/, '').trim();
  const backend = gpuBackend(device.id);
  const matches = (inventory || []).filter(row => row.backend === backend &&
    row.description?.trim() === name && Number.isSafeInteger(row.index) && row.index >= 0);
  const selected = matches.find(row => row.name === device.id) || (matches.length === 1 && matches[0]);
  if (!selected) throw Error('音频执行器未识别所选 GPU：' + device.name + '。请刷新设备或选择 CPU。');
  return selected.index;
}

function audioDeviceArgs(runtime) {
  if (!runtime.device_id || runtime.device_id === 'cpu') return ['--backend', 'cpu'];
  if (!Number.isSafeInteger(runtime.audio_device_index) || runtime.audio_device_index < 0)
    throw Error('请重新检查音频 GPU 设备。');
  return ['--backend', gpuBackend(runtime.device_id), '--device', String(runtime.audio_device_index)];
}

async function diffusionDevices(invoke, engine) {
  const devices = [];
  await invoke(engine, ['--list-devices'], { timeout: 15000, onLine(line) {
    const [id, description] = line.split('\t');
    if (description?.trim()) devices.push({ id, name: description.trim() });
  } });
  if (!devices.length) throw Error('扩散执行器未返回设备列表。');
  return devices;
}

async function checkDiffusionDevice(invoke, engine, device) {
  const name = device.name.replace(/ · [^·]+$/, '').trim();
  const devices = await diffusionDevices(invoke, engine);
  if (!devices.some(row => row.id === device.id && row.name === name))
    throw Error('扩散执行器未识别所选 GPU：' + device.name + '。请刷新设备或选择 CPU。');
}

module.exports = { gpuBackend, deviceExecutable, textExecutable, logicalProcessors, trialThreads, audioDevices, audioDeviceIndex, audioDeviceArgs, diffusionDevices, checkDiffusionDevice };
