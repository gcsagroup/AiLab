'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { timedMediaInvoke } = require('../../apps/windows-ui/hf/trial-timing.cjs');

test('only the completed encoder output supplies the video frame count', async () => {
  const measured = {};
  const run = timedMediaInvoke(async (_exe, args, options) => {
    assert.ok(args.includes('-progress'));
    options.onLine('frame=1');
    options.onLine('frame=7');
    return 'ok';
  }, { ffmpeg:'ffmpeg.exe' }, (_type, values) => Object.assign(measured, values));
  assert.equal(await run('ffmpeg.exe',['-frames:v','14','video.mp4']), 'ok');
  assert.equal(measured.output_frames, 7);
  assert.ok(measured.media_encode_ms >= 0);
});
test('audio session metrics accumulate over multiple segments while preserving existing callbacks', async () => {
  const measured = {}, log = [];
  const run = timedMediaInvoke(async (_exe, args, options) => {
    assert.ok(args.includes('--metrics'));
    options.onLine('metrics.wall_ms=12.5');
  }, {}, (_type, values) => Object.assign(measured, values));
  for (let i=0;i<2;i++) await run('audiocpp_cli.exe',[], { onLine:line=>log.push(line) });
  assert.equal(log.length, 2);
  assert.equal(measured.audio_session_ms, 25);
});
