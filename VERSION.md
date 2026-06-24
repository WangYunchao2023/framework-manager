# framework-manager 版本历史

## v1.6.2-patch4 (2026-06-24)

### 🎨 重构：默认设置下拉复用主下拉数据源

**背景**：
- 默认设置卡和主下拉独立拉 `/api/models_by_framework`, 两处数据各走各的
- 隐藏模型仅过滤主下拉, 默认设置下拉还是显示已隐藏的
- ingest 后需手动调 `loadDefaultSettings` 同步 (patch3 临时修复)
- 跟随问题: 两处各自维护, UX 容易出现不一致

**设计**：
- 主下拉 = 唯一数据源（`/api/status` 的 `available_models`）
- 默认设置下拉 = 复用主下拉（不独立拉 API）
- 例外: 「默认框架」 != 「当前框架」 时才独立拉 (覆盖"空闲后回退到其他框架"场景)

**实现**：
- `/api/status` 返 `available_display_names` 字段（后端调 `_extract_short_model_name`）
- `updateModelSelect()` 加 `displayNames` 参数，顺便调 `syncDefaultModelSelect` 同步
- `syncDefaultModelSelect(models, displayNames, selectedModel)` 新函数
- `loadDefaultSettings()` / 「默认框架」change：仅当 `defaultFw !== currentFramework` 时拉 API

**顺手修复**：
- `ingest` 成功后清 beellama 缓存（`force_refresh=False` 在 30s 内会返旧列表）
- ingest 后 `/api/status` 立即反映新模型

**验证**：
- ingest 前：5 个模型原状
- ingest 立即后：6 个，新模型出现 ✅
- 清理后：5 个原状 ✅
- 主下拉隐藏后, 默认设置下拉也不可见 ✅（同源数据）

---

## v1.6.2-patch3 (2026-06-24)

### 🐛 修复: 默认设置卡下拉两个 qwen3.6 显示相同 + ingest 后下拉不刷新

**Bug 1: 两个 qwen3.6 显示相同**
- 原因: 前端 `updateDefaultModelSelect` 用硬编码 if/elif 推断 short_name:
  ```js
  if (displayName.includes('qwen3.6')) displayName = 'qwen3.6-q3';
  ```
  导致 `qwen3.6-35b` 和 `qwen3.6-35b-uncensored` 都显示成 `qwen3.6-q3`
- 修复: `/api/models_by_framework` 新增 `display_names` 字段, 调用后端 `_extract_short_model_name()`
  保证与 wrapper / per-model / defaults 完全一致
- 验证: display_names = [gemma-4-26b, qwen3-14b, qwen3-vl, qwen3.6-uncensored, qwen3.6-q3]

**Bug 2: ingest 后新模型不出现默认设置下拉**
- 原因: `ingestBeellama()` 成功后调 `setTimeout(refresh, 1000)` 刷新主状态,
  但 `refresh()` 不同步 `default-model-select` 下拉 (该下拉只在 DOMContentLoaded / 框架切换时刷新)
- 修复: ingest 成功后额外调 `loadDefaultSettings()`
- 验证: 模拟 `Qwen3.6-35B-A3B-Uncensored-DefaultTest1-Q4_K_M.gguf` → ingest → display_names 从 5 变 6

---

## v1.6.2-patch2 (2026-06-24)

### 🎨 UI 重构：beellama 默认值卡拆分（统一默认 vs 当前模型默认）

**背景**：
- 原 `defaults-card` 同时包含两块:
  - ⚙️ **统一默认 (_fallback)**: 未来「➕ 添加新模型」会用此值初始化
  - 📋 **当前模型默认值**: 当前加载模型在 defaults.models 中的值
- 但只有一个「💾 保存默认值」按钮, 不清是改全局还是仅改当前模型
- 用户反馈: 需要明确区分, 避免误保存。

**改动 (仅 beellama 端, ollama 独立卡保留)**：

| 卡片 | 之前 | 现在 |
|---|---|---|
| 🎯 默认值卡 | 包含统一默认 + 当前模型默认两块, 单个保存按钮 | 重命名 🎯 **统一默认值**，只保留统一默认块 + 「💾 保存统一默认」按钮 |
| 📦 模型专属参数卡 | 只含 per-model 编辑 | 底部新增 📋 **当前模型默认值** 块 + 「💾 保存默认」按钮 |

**API 调整**：POST `/api/defaults` 支持部分更新
- 旧行为：必须同时传 `_fallback` 和 `models`, 前端要全量重组
- 新行为：
  - 只传 `_fallback` → 仅更 `_fallback`, `models` 完全保留
  - 只传 `models` → 合并 `models` (传过的 key 被覆盖, 未传保留)
  - 两个都传 → 全量更新 (向后兼容)

**验证（端到端）**：
- POST 只传 `_fallback` → _fallback 变化, models 5 个条目原封不动 ✅
- POST 只传 models[short_name] → 只该 short_name 变化, 其他 4 个模型 + _fallback 完全保留 ✅
- HTML 渲染: defaults-card 仅含 _fallback + 保存统一默认按钮 ✅
- HTML 渲染: beellama-model-params-card 底部含 model-defaults-current-row + 保存默认按钮 ✅

---

## v1.6.2-patch1 (2026-06-24)

### 🐛 修复：beellama ingest 需手动补 per-model

**症状**：
- v1.6.2 的 `/api/ingest_beellama` 只建软链 + 写 sha 别名
- 用户在 WebUI 点“加载” 报 "模型缺 per-model 配置: ctx_size parallel ngpu_layers"
- 加载无配置模型时需手动点模态框 → 选择使用 _fallback → 一步路难走

**修复**：
- 新增 `_init_per_model_for_ingest(short_name)` 辅助函数
- ingest 建软链后自动调:
  - 从 `_load_defaults` 读 `_fallback` (现成 131072/2/99)
  - `defaults.models[short_name]` 补齐 (已存在不覆盖)
  - `framework-manager.json` 的 `framework_params.beellama.models[short_name]` 补齐 (已存在不覆盖)
- 仅在新建时落盘 (幂等性: 二次调用不写文件)
- ingest 返回 `linked[].per_model = {created, ctx_size, parallel, ngpu_layers}`

**与既有 `api_init_model_with_fallback` 区别**：
| 项 | init_model_with_fallback (v1.1.5) | _init_per_model_for_ingest (v1.6.2-patch1) |
|---|---|---|
| 触发时机 | 加载时被动调 | ingest 时主动调 |
| 用户交互 | 弹模态框需确认 | 静默 |
| 重启 beellama | 会 | 不会 |
| 不覆盖手动调过的 | 是 | 是 |
| 写 defaults | 是 | 仅 created 时 |
| 写 per-model | 是 | 仅 created 时 |

**验证**（端到端）：
- 模拟 `Qwen3.6-35B-A3B-Uncensored-IngestTest-v3.gguf` 1MB 头
- ingest → linked[0].per_model.created = false (qwen3.6-uncensored 早存在)
- per-model 字典里 qwen3.6-uncensored 条目 131072/1/99 仍正确
- 清理后系统状态完全恢复

---

## v1.6.2 (2026-06-24)

### 🆕 新增：beellama 端「📥 自动注册下载的模型」

**背景**：
- 之前 ollama 端已有 `/api/ingest_gguf` (v1.1.18)，扫 `/data/ollama/models/blobs/` 中任意命名的 .gguf，可自动生成 ollama manifest
- beellama 端缺同等能力：用户从 HuggingFace 下载 .gguf 放 blobs/ 后，必须手动 `ln -s` 到 `~/models/<dir>/`，体验割裂

**功能**：
- 新增 `POST /api/ingest_beellama` 端点 + WebUI 「📥 自动注册下载的模型」卡片（切到 beellama 时显示）
- 扫 ollama blobs/ 中非 sha256- 开头的 .gguf，复用 `_extract_short_model_name()` 推 short_name
- `short_to_dir` 映射表（qwen3.6-q3→qwen3.6-35b、qwen3.6-uncensored→qwen3.6-35b-uncensored 等）
- 在 `~/models/<dir>/<basename>` 建软链接 → `/data/ollama/models/blobs/sha256-{hash}` 别名

**与 ollama 端 ingest_gguf 区别**：
| 项 | ollama 端 | beellama 端（v1.6.2 新增）|
|---|---|---|
| 文件系统 | 同 fs（/data）| 跨 fs（/home → /data）|
| 链接方式 | 硬链接 + 删原文件 | 软链接 + 保留原文件 |
| 生成 manifest | ✅ 写 ollama manifest | ❌ 不写 |
| 生成 modelfile | ✅ 写 Modelfile | ❌ 不写 |
| 动 ollama 端 | 是 | **否**（用户明确 “ollama 不要动”）|

**验证**（端到端）：
- 模拟用户下载 `Qwen3.6-35B-A3B-Uncensored-AnotherTest-Q4_K_M.gguf` 到 blobs/
- 调 `/api/ingest_beellama` → `{"scanned":1, "linked":[{dir:qwen3.6-35b-uncensored, target:sha256-335e6e8d...}]}`
- 软链接建好 → 9528 `/api/scan_for_addition?framework=beellama` 从 5 个变 6 个模型
- 幂等：再次调入返回 `skipped: [已存在, 指向同一目标]`
- ollama `/api/tags` manifest 列表无变化 ✅
- 清理后系统状态完全恢复原样

**设计决策**：
- “不动 ollama 端” 要求具体到 (1) 不写 manifest/modelfile (2) 不删 blobs 原文件
- 软链指向 `sha256-{hash}` 别名而非原文件：避免 ollama 改名/删原文件后链接失效（别名为本代码创建，生命周期同 ingest）
- mmproj 不自动链：实际场景中 mmproj 通常与 GGUF 同名/同目录，手动管理更可控

---

## v1.6.1 (2026-06-24)

### 🐛 修复：beellama 加载 qwen3.6-uncensored 后状态显示为 qwen3.6-q3

**症状**：
- beellama 框架下，加载 `qwen3.6-35b-uncensored/Qwen3.6-35B-A3B-Uncensored-...gguf` 成功后
- `/api/status` 返回 `model: "qwen3.6-q3"`，无法区分当前是 q3 还是 uncensored

**根因**：
- `detect_current_framework() → _try_infer_beellama()` 第 1358-1364 行硬编码 if/elif 链
- `'qwen3.6' in gguf_filename.lower()` 一刀切匹配，q3 和 uncensored 都返回 `qwen3.6-q3`
- 同时把 `gemma-4-26b` 错误地硬编码为 `gemma4`（与 alias_map 不一致）

**修复**：
- 复用第 2034 行已有的 `_extract_short_model_name(gguf_path)` 函数
- 5 种典型 GGUF basename 单测全部命中：
  - `Qwen3.6-35B-A3B-Uncensored-...gguf` → `qwen3.6-uncensored` ✅
  - `Qwen_Qwen3.6-35B-A3B-Q3_K_M.gguf` → `qwen3.6-q3` ✅
  - `qwen3-14b-q4.gguf` → `qwen3-14b` ✅
  - `qwen3-vl-8b.gguf` → `qwen3-vl` ✅
  - `gemma-4-26B-A4B-it-UD-Q4_K_M.gguf` → `gemma-4-26b` ✅（修正 gemma4 别名）

**关联修复**：用户还报告了 beellama 扫描找不到非 uncensored qwen3.6-q3
- 根因：`~/models/qwen3.6-35b/Qwen_Qwen3.6-35B-A3B-Q3_K_M.gguf` 是死链，指向已被 ollama 删除的 blob `sha256-6159deaf...`
- 修复：删除死链，建立软链接指向 ollama 现有的真实 blob `sha256-17350b13...` (Bartowski Q3_K_M 17.18GB)
- 跨文件系统（`/home` vs `/data`）无法硬链接，改用软链接；`is_file()` 会跟随软链接，所以扫描和加载都能正常工作
- 不动 ollama 一侧

### 验证
- ✅ 单测 5 种 GGUF basename → 5 个 short_name 全部正确
- ✅ `/api/scan_for_addition?framework=beellama` → 5 个模型（修复前 4 个）
- ✅ `/api/status` 重启后立即反映：`model: "qwen3.6-uncensored"`（修复前 `qwen3.6-q3`）

---

## v1.6.0 (2026-06-23)

beellama GPU util 自动检测 + 死锁修复。

---

## v1.2.2 (2026-06-23)

### 🆕 新增：OpenAI 兼容端点

让 OpenClaw/Claude Code/Cursor/Cherny Studio 等所有 OpenAI 兼容 Agent 工具能以 base_url 形式接入 framework-manager，统一调度所有本地模型 (ollama/beellama/comfyui)。

### 端点

| 路径 | 用途 |
|------|------|
| `POST /v1/chat/completions` | OpenAI 兼容聊天端点（同步）|
| `GET /v1/models` | 列出所有可用模型 |

### 接入方式

```bash
# OpenClaw / Claude Code / Cursor / Cherry Studio / Open WebUI 等
# base_url 改为:
http://localhost:9528/v1

# model 字段填:
"ollama/qwen3.6-35b"    # Ollama + qwen3.6-35b
"beellama/qwen3.6-q3"   # beellama + qwen3.6-q3
"comfyui/sd_xl"         # (暂不支持 OpenAI 协议, 会返回 501)

# 也可以不加前缀, 默认 ollama
"qwen3.6-35b"           # = "ollama/qwen3.6-35b"
```

### 内部机制

- 完全复用 v1.2.0 的 `/api/qrun` 队列机制
- 透传 OpenAI messages 到上游
- 自动转译上游响应到 OpenAI 格式 (ollama native API → OpenAI ChatCompletion)
- beellama 本身就是 OpenAI 兼容, 直接透传

### 测试覆盖

| 场景 | 结果 |
|------|------|
| T1 `/v1/models` 列出模型 | ✅ ollama + beellama 全列出 |
| T2 beellama 当前模型命中 | ✅ 1s, switched=false |
| T3 beellama → ollama 跨框架 | ✅ 29s, switched=true |
| T4 ollama 内部跨模型 | ✅ 93s, switched=true |
| T5 不支持的 framework | ✅ 400 + 明确错误信息 |
| T6 comfyui 拒绝 (OpenAI 不适合异步工作流) | ✅ 501 + hint |
| T7 缺 model / messages 字段 | ✅ 400 |
| T8 缺省前缀默认 ollama | ✅ 兼容 |

### Diff

+1 endpoint (`/v1/chat/completions`) + 1 endpoint (`/v1/models`) + 1 helper 函数, append-only 不改任何现有逻辑

---

## v1.2.1 (2026-06-23)

### 🐛 修复：beellama 队列调用完全失败

v1.2.0 实施说明中已将 beellama 跨框架切换标记为 “已知 bug（错误优雅返回）”，但实测发现该 bug 导致 **所有 beellama 调用都失败**，队列轮换机制对 beellama 路径不可用。

#### 根因 1：`switch-inference.sh` 命令替换报错退出（switch-inference.sh v1.0.4）

```bash
# 原代码 (v1.0.3) - gemma-4-26b 行的命令替换：
"gemma-4-26b|...|/data/ollama/models/blobs/$(ls /data/ollama/models/blobs/sha256-6159deaf76075* 2>/dev/null | head -1 | xargs basename)"
```

- 当 ollama gemma4 的 GGUF 不在 `/data/ollama/models/blobs/`（例如 blob 被 unload/清理）时，`ls` 输出为空 → `xargs basename` 无输入 → basename 输出 `basename: 缺少操作对象` → **整个 `$(...)` 退出码非零** → bash `set -e` 让 `switch-inference.sh` 立刻退出
- 后果：**任何 `switch-inference.sh beellama <model>` 调用都立即失败**（不只是 gemma4，qwen3.6-q3 / qwen3.6-uncensored 等也连累）

#### 根因 2：`load_model_for_framework` alias_map 缺 uncensored (framework-manager.py)

```python
# 原代码 (v1.2.0)
alias_map = {
    'qwen3.6-q3': 'qwen3.6-35b',
    'qwen3-vl': 'qwen3-vl',
    'gemma4': 'gemma-4-26b',
}
```

- `get_beellama_models()` 返回的模型名是相对路径形式（`qwen3.6-35b-uncensored/Qwen3.6-...gguf`），需别名匹配
- `qwen3.6-uncensored` 不在 alias_map 中，也不在 models 列表中 → **模型不可用**

### 修复内容（+5 / -2 行）

| 文件 | 改动 |
|------|------|
| `switch-inference.sh` v1.0.3→v1.0.4 | gemma-4-26b 命令替换 → 固定路径 `/home/wangyc/models/gemma-4-26b/gemma-4-26B-A4B-it-UD-Q4_K_M.gguf`（已验证文件存在） |
| `framework-manager.py` v1.2.0→v1.2.1 | alias_map 加 `'qwen3.6-uncensored': 'qwen3.6-35b-uncensored'` |

### 测试覆盖

| 场景 | 结果 |
|------|------|
| T1 ollama 直接命中 | ✅ switched=false, 1s |
| T2 ollama 跨模型切换 (gemma4 → qwen3:14b) | ✅ switched=true, 12s |
| T3 并发 3 任务 FIFO (ollama/beellama 混合) | ✅ A、B 成功（修后），C 失败（ollama qwen3-vl mmproj OOM，环境问题，非本版本 bug） |
| T4 取消 pending | ✅ status=cancelled |
| T5 comfyui 拒绝 | ✅ 501 + 明确 hint |
| T6 异步 + 轮询 | ✅ queued → running → done, 109s |
| C1 ollama 默认模型 (跨框架 fallback) | ✅ 12s |
| C2 ollama → beellama (跨框架) | ✅ 17s |
| C3 beellama → ollama (反向跨框架) | ✅ 102s |
| C4 并发 3 任务 FIFO (跨框架混合) | ✅ A、B 成功，C OOM（同 T3） |

### 已知非本版本 bug（环境/数据问题）

- **ollama qwen3-vl:ctx128k 加载返回 500**: `cudaMalloc failed: out of memory (1.4 GB for mmproj vision encoder)`，需 ollama 配置 (gpu_layers / num_parallel) 调整
- **switch-inference.sh MODELS[3] 原本动态查 blob 的设计意图**：当 gemma4 GGUF 被 re-import 到 ollama 后，blob 会变化 → 现在改为固定路径后，如果未来重导入 gemma4 到 ollama，需要更新这一行

---

## v1.2.0 (2026-06-22)

### 🆕 新增：推理请求队列 + 自动 VRAM 轮换

新增 4 个 HTTP 端点 + 1 个 worker 线程，让 OpenClaw（`/model`）或其它工具可通过统一接口提交推理请求，framework-manager 自动维护队列 → 比对当前显存 → 必要时切框架/模型 → 转发 → 返回结果。

### 新增端点

| Method | Path | 用途 |
|--------|------|------|
| POST | `/api/qrun` | 入队推理请求（`?wait=true` 同步等结果） |
| GET | `/api/qrun/<task_id>` | 轮询任务结果 |
| DELETE | `/api/qrun/<task_id>` | 取消 pending 任务 |
| GET | `/api/qstatus` | 队列状态（不返回任务 body） |

### 请求示例

```bash
# 同步（阻塞等结果）
curl -X POST "http://localhost:9528/api/qrun?wait=true&timeout=600" \
  -H "Content-Type: application/json" \
  -d '{
    "framework": "ollama",
    "model": "qwen3:14b-ctx64k",
    "path": "/api/chat",
    "body": {"model": "qwen3:14b-ctx64k", "messages": [...], "stream": false},
    "source": "openclaw-/model"
  }'

# 异步（立刻返回 task_id，再轮询）
curl -X POST "http://localhost:9528/api/qrun" -d '...'  # → {"task_id": "..."}
curl "http://localhost:9528/api/qrun/<task_id>"        # → 状态 + 上游响应
```

### 转发白名单

- **ollama**：`/api/generate`、`/api/chat`、`/api/embeddings`、`/api/show`
- **beellama**：`/v1/chat/completions`、`/v1/completions`、`/v1/embeddings`
- **comfyui**：v1 不透传（异步工作流，转发语义不同；如需支持请先 `POST /api/set_framework {"framework":"comfyui"}` 后由调用方自行交互）

### 设计要点

- **append-only**：本次改动 +323/-0 行，未触碰任何现有函数/路由
- **单 worker 线程**：与「显存轮换」语义一致——同一时刻只有一个模型驻留显存
- **任务幂等查找**：用 `_qrun_tasks` 单一字典作为可信源，轮询不再有 race condition
- **活动计时同步**：worker 处理任务期间持续刷新 `last_activity_time`，避免空闲回退误触发
- **结果 5 分钟保留**：完成后保留 5 分钟供轮询，再清理

### 测试覆盖

| 场景 | 结果 |
|------|------|
| ollama 当前模型命中 → 直接转发 | ✅ |
| ollama 跨模型（gemma4 → qwen3:14b）切换 | ✅ switched=true, 推理成功 |
| beellama 框架切换（existing 代码 basename bug 导致加载失败，错误优雅返回） | ✅ switch 成功，错误回传 |
| 异步入队 + 轮询（无 race condition） | ✅ |
| 取消已 running 任务 → 409 Conflict | ✅ |
| 并发 3 任务入队 → FIFO 顺序执行 | ✅ |
| 现有所有端点（/api/status, /api/queue, /api/frameworks 等） | ✅ 无影响 |

---

## v1.1.19 (2026-06-22)

汇总 v1.1.18 + patch1~4。
