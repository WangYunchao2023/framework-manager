# framework-manager 版本历史

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
