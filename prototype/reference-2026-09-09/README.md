# 最后确认的原型参考

原样复制最终 Demo、构建素材和测试，原目录保留。源文件身份见 [manifest.json](manifest.json)；真实应用位于 `apps/desktop`，此目录不进入生产包。此原型是模拟界面，不执行真实训练或推理。

此原型含 6 项已知行为问题，另有 1 项配方追溯语义问题。检查器的断言用于复现这些问题，退出成功表示问题仍存在，不能计为修复通过。

## 从仓库根目录复跑

需要 Node.js 和 Python 3，以下步骤只使用其标准库。先核对清单中的字节数和摘要，再复制到独立临时目录执行；检查器会在那里写出报告，固定副本保持不变。任一步失败时停止并保留输出，不继续把后续结果判为通过。

```sh
node --version
python3 --version
ailab_replay_dir="$(mktemp -d "${TMPDIR:-/tmp}/ailab-reference.XXXXXX")"
python3 - "$ailab_replay_dir" <<'PYTHON'
from pathlib import Path
import hashlib, json, shutil, sys
source = Path("prototype/reference-2026-09-09")
target = Path(sys.argv[1])
manifest = json.loads((source / "manifest.json").read_text())
for item in manifest["files"]:
    data = (source / item["path"]).read_bytes()
    assert len(data) == item["bytes"], item["path"]
    assert hashlib.sha256(data).hexdigest() == item["sha256"], item["path"]
    shutil.copy2(source / item["path"], target / item["path"])
print("Verified files:", len(manifest["files"]))
print("Replay directory:", target)
PYTHON
node "$ailab_replay_dir/test-ailab-unified.cjs"
node "$ailab_replay_dir/test-ailab-runtime.cjs"
node "$ailab_replay_dir/audit-prototype-counterexamples.cjs"
```

本次以 Node.js `v24.14.0` 实际执行：13 个清单文件身份一致，代表性检查输出 42 组通过，运行配置检查输出 17 组通过。检查器输出 `A-01` 至 `A-07`，报告保存在临时目录的 `audit-prototype-counterexamples.json`；这是历史原型的已知问题证据，不是生产 App 测试结果。

## 界面与结论边界

固定界面文件是 [ailab-unified.html](ailab-unified.html)，须由验收者在浏览器中实际打开并核对工作台、类别切换与运行设置。上述脚本使用状态函数及最小 DOM 替身，不检查真实布局、键盘焦点、播放或截图。

本轮浏览器工具因本地文件 URL 策略拒绝打开，未完成可视界面复验；没有改用其他入口绕过限制。新成员仍需独立按说明执行并记录版本、结果和困难，才能补充 AC-23 的新成员证据；开发者复跑不代替该项或 AC-25 的真实用户验收。

构建会重写 HTML；如需运行 `build-ailab-unified.py`，仅在上述临时副本中执行，保留原始摘要与报告。人工修订与原生成配方分离等产品规则以 [文档首页](../../docs/README.md) 所列规范为准。
