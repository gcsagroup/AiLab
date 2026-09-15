import { describe, expect, it } from 'vitest';
import { readMediaContent } from '../../apps/desktop/vite.config';

describe('开发桥接的已认证媒体读取', () => {
  it.each(['image/png', 'video/mp4', 'audio/wav'])('保持 %s 原始字节和类型', async mediaType => {
    const bytes = new Uint8Array([0, 1, 127, 128, 255]);
    const result = await readMediaContent(new Response(bytes, { headers: { 'content-type': mediaType } }));
    expect(result.contentType).toBe(mediaType); expect([...result.body]).toEqual([...bytes]);
  });
  it('拒绝主动内容、空媒体和声明过大的响应', async () => {
    await expect(readMediaContent(new Response('<script>invalid</script>', { headers: { 'content-type': 'text/html' } }))).rejects.toThrow('类型不支持');
    await expect(readMediaContent(new Response(new Uint8Array(), { headers: { 'content-type': 'image/png' } }))).rejects.toThrow('为空');
    await expect(readMediaContent(new Response('small', { headers: { 'content-type': 'image/png', 'content-length': '1024' } }), 8)).rejects.toThrow('超过预览');
  });
  it('没有 Content-Length 的分块响应仍按实际字节拒绝超限', async () => {
    let cancelled = false;
    const body = new ReadableStream({ start(controller) { controller.enqueue(new Uint8Array(5)); controller.enqueue(new Uint8Array(5)); }, cancel() { cancelled = true; } });
    await expect(readMediaContent(new Response(body, { headers: { 'content-type': 'video/mp4' } }), 8)).rejects.toThrow('超过预览');
    expect(cancelled).toBe(true);
  });
});
