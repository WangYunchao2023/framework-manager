# framework-manager 版本历史

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
