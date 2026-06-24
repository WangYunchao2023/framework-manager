#!/usr/bin/env python3
"""framework-manager.py — 框架管理器 (Ollama/Beellama/ComfyUI)
REST API + WebUI, 端口 9528
支持：Ollama ↔ beellama ↔ comfyui 切换，模型热切换
CLI 模式：python3 framework-manager.py status|ollama|beellama|comfyui [model]

版本：1.6.2-patch4

更新日志:
- v1.6.2-patch4: 默认设置下拉复用主下拉数据源 (统一/避免两处维护)
  - 背景: 默认设置卡和主下拉独立拉 /api/models_by_framework, 两处数据各走各的
    - 隐藏模型仅过滤主下拉, 默认设置下拉还是显示已隐藏的
    - ingest 后仅 patch3 手动调 loadDefaultSettings 同步
  - 修复: 默认设置下拉直接从主下拉拿数据 (不独立拉 API)
    - /api/status 返 available_display_names (后端 _extract_short_model_name)
    - updateModelSelect 顺便调 syncDefaultModelSelect 同步
    - loadDefaultSettings 仍独立拉 (仅当默认框架 != 当前框架, 覆盖"空闲回退到其他框架"场景)
    - 默认框架 select change 同样只在需要时拉
  - 顺手: ingest 成功后清 beellama 缓存, 避免 30s 内 /api/status 仍返旧
- v1.6.2-patch3: 修复默认设置卡下拉两个 qwen3.6 显示相同 + ingest 后下拉不刷新
  - 背景: updateDefaultModelSelect 用硬编码 if/elif 猜 short_name:
    `if (displayName.includes('qwen3.6')) displayName = 'qwen3.6-q3';`
    导致 qwen3.6-35b 和 qwen3.6-35b-uncensored 都显示成 qwen3.6-q3
  - 修复: /api/models_by_framework 新增 display_names 字段
    (调用后端 _extract_short_model_name, 与 wrapper / per-model / defaults 完全一致)
  - 顺手修复: ingest 成功后调 loadDefaultSettings(), 新注册的模型自动出现在默认设置下拉
    (原来只 refresh() 不刷新默认设置卡)
- v1.6.2-patch2: beellama 端默认值卡拆分 (统一默认 + 当前模型默认)
  - 背景: 原 defaults-card 同时包含 "统一默认 (_fallback)" 和 "当前模型默认值" 两块,
    只有一个保存按钮, 用户反馈不够清晰: 不清保存是改全局还是仅改当前模型
  - 改动:
    - defaults-card 重命名为 "🎯 统一默认值", 只保留 _fallback 块 + "💾 保存统一默认" 按钮
    - beellama-model-params-card 底部新增 "📋 当前模型默认值" 块 + "💾 保存默认" 按钮
    - 当前模型默认值块在加载模型时自动渲染 (与 per-model 同一卡, 上下文连贯)
  - API 调整: POST /api/defaults 支持部分更新 (只传 _fallback 或只传 models)
    - 背景: 旧 API 要求同时传 _fallback + models, 前端需全量重新组装, 易出错
    - 改动: 只传 _fallback → 仅更 _fallback; 只传 models → 合并 models (传过的 key 被覆盖, 未传保留)
  - JS 调整: saveDefaults() → saveDefaultsFallback() + saveDefaultsCurrentModel()
- v1.6.2-patch1: beellama ingest 补全 per-model + defaults 初始化
  - 背景: v1.6.2 只建软链, 加载时 beellama-wrapper 会报 "缺少 per-model 配置 (ctx_size/parallel/ngpu_layers)"
  - 修复: 新增 _init_per_model_for_ingest(short_name), ingest 建软链后自动调
    - 从 _load_defaults 读 _fallback (现成 131072/2/99)
    - defaults.models[short_name] 补齐 (已存在不覆盖)
    - framework-manager.json 的 framework_params.beellama.models[short_name] 补齐 (已存在不覆盖)
  - 与既有 api_init_model_with_fallback 区别:
    - init_model_with_fallback: 加载时被动调, 弹模态框需用户确认 + 重启 beellama
    - _init_per_model_for_ingest: ingest 时主动调, 静默 + 不重启
  - ingest 返回 linked[].per_model = {created, ctx_size, parallel, ngpu_layers}
  - 已存在不覆盖用户手动调过的值 (eg. qwen3.6-uncensored 之前是 131072/1/99, 二次 ingest 不变)
- v1.6.2: beellama 端「📥 自动注册下载的模型」功能
  - 背景: 已有 ollama 端 /api/ingest_gguf (v1.1.18) 可在 /data/ollama/models/blobs/ 扫用户下载的 .gguf
    自动生成 ollama manifest。beellama 端缺同等能力, 用户下载新模型后, 只能手动 ln -s 到 ~/models/
  - 功能: 扫 ollama blobs/ 中非 sha256- 开头的 .gguf, 为 beellama 在 ~/models/<dir>/ 下建软链接
    + 复用 _extract_short_model_name() 推 short_name
    + short_to_dir 映射 (qwen3.6-q3→qwen3.6-35b, qwen3.6-uncensored→qwen3.6-35b-uncensored 等)
    + 软链接指向 sha256-{hash} 别名 (不是原文件, 避免 ollama 改名/删 后链接失效)
  - 与 ollama 端 ingest_gguf 区别:
    - 跨 fs (/home vs /data) 软链接 vs 同 fs 硬链接
    - 不删原文件 vs ollama 端删原文件 (硬链接保留)
    - 不写 ollama manifest / modelfile vs ollama 端生成 manifest + modelfile
    - 不动 ollama 端 (用户明确 "ollama 不要动")
  - 端点: POST /api/ingest_beellama, 返回 {scanned, linked:[{src,short,dir,target,link,size,sha}], skipped, errors}
  - HTML: 切到 beellama 时显示「📥 自动注册下载的模型」卡片
  - JS: ingestBeellama() 调 API + 渲染结果 + 1s 后 refresh() 重拉模型列表
- v1.6.1: 修复 _try_infer_beellama() 硬编码 if/elif 链把所有 qwen3.6 GGUF 都识别为 'qwen3.6-q3'
  - Bug 复现: 加载 qwen3.6-35b-uncensored (GGUF basename 含 Uncensored) 后, /api/status 仍显示 model='qwen3.6-q3'
  - 根因: detect_current_framework() → _try_infer_beellama() 第 1358-1364 行用 'qwen3.6' in filename.lower() 一刀切, uncensored 版被误判成 q3 版
  - 修复: 复用第 2034 行已有的 _extract_short_model_name(gguf_path), 统一由 regex 决定 short_name
  - 验证 5 种典型 GGUF basename → qwen3.6-uncensored / qwen3.6-q3 / qwen3-14b / qwen3-vl / gemma-4-26b (全部命中)
  - 顺带把硬编码的 'gemma4' alias 改成 'gemma-4-26b' (与 alias_map 对齐)
- v1.6.0: beellama 自动检测 (GPU util 监测)
  - task_register 加 framework_ref.detect="gpu_idle" (beellama LLM 专用)
  - watcher 每 2s 读 _vram_state["gpu_util_pct"] (vram_monitor 已 5s 一次调 nvidia-smi, watcher 复用缓存)
  - 持续 < 15% 连续 3 次 (= 6s) → task_done
  - 记录 peak_gpu_util 给 result
  - 适用: beellama LLM 推理 (qwen3-14b 等, 单次几秒到几十秒)
  - 不适用: embedding (-ngl 0 CPU 推理, 0.04s 完成, 2s 轮询捕不到) → 仍需手动 task_done

  v1.6.0-patch3: api_vram_status 去掉 _ensure_vram_monitor() (避免 nvidia-smi hang 时锁住所有 API)
  v1.6.0-patch5: _tasks_lock 改 RLock (watcher 调 _auto_task_done 嵌套持锁修复死锁)

  实测: beellama chat 5-10s 推理 peak_gpu_util 97%, 自动 done; 空闲时注册标 failed
- v1.5.0: 任务自动检测 (framework_ref + 后台 watcher)
  - task_register 可传 framework_ref: {prompt_id} (ComfyUI) 或 {detect: "model_unload"} (Ollama)
  - 后台 watcher thread 每 2s 轮询框架原生信号
    - ComfyUI: /history/{prompt_id} 出现 → auto task_done (查 status_str 判定 success/failed)
    - Ollama: /api/ps 模型消失 → auto task_done (keep_alive 过期或主动 unload)
    - beellama/embedding: llama.cpp 无任务 API, 必须手动 task_done (拒绝 framework_ref)
  - 自动提取输出文件 (images/gifs) 和错误信息
  - WebUI "📋 活跃任务" 卡片加 "🤖 自动检测" 紫色 badge
  - 完全 append-only: 不修改任何现有函数/路由
  - ~140 行代码
- v1.2.2-patch1: OpenAI 端点加特殊 model 名 "framework-manager/current"
  - 收到后自动用当前显存里的模型 (current_framework/current_model)
  - 允许用户在 9528 webui 中设置加载的模型, OpenClaw / Agent 用 framework-manager/current 即用该模型
  - 无需切换 (已在显存), switched=False, 1s 响应
  - 3 行代码改动
- v1.2.2: OpenAI 兼容端点 (POST /v1/chat/completions + GET /v1/models)
  - 接收标准 OpenAI 格式请求, 内部复用 /api/qrun 队列
  - model 格式: "framework/modelname" (ollama/qwen3.6-35b / beellama/qwen3.6-q3)
  - 缺省前缀默认 ollama
  - 让 OpenClaw/Claude Code/Cursor/Cherry Studio 等所有 OpenAI 兼容工具可作为 Agent 接入
  - append-only: 不改任何现有函数/路由
- v1.2.1: 修复 beellama 队列调用完全失败
  - switch-inference.sh v1.0.4: gemma-4-26b 命令替换报错导致整个脚本退出 → 改为固定路径
  - alias_map 加 qwen3.6-uncensored → qwen3.6-35b-uncensored
- v1.2.0: 推理请求队列 + 自动 VRAM 轮换 (POST /api/qrun + worker thread)
- v1.1.19: 升版 (汇总 v1.1.18 + patch1~4)
  - v1.1.18: 自动注册用户下载的 GGUF (ingest_gguf)
    + 扫描 /data/ollama/models/blobs/ 中任意命名的 .gguf (用户下载/放置的)
    + 增量计算 sha256 (8MB chunks, 避免 OOM)
    + 硬链接为 sha256-{hash} 命名 (跨 fs 退到 shutil.copy2)
    + 删原文件 (硬链接保留, 源释放)
    + 解析 GGUF header (手写 80 行 parser, 提取 general.name + context_length)
    + 读「📋 新模型注册参数」文件中 5 个参数
    + num_ctx = min(用户设置, gguf.context_length) - 不能超原生 ctx
    + tag 格式: '{general.name}-ctx{N}k' (如 TestModel-Fake:ctx32k)
    + 复用 load-status-area 进度遮罩 + audit_log
  - v1.1.18-patch1: 删除 _meta 段, 文件只存 5 个值 (json dump 直接写 5 个参数)
  - v1.1.18-patch2: 按钮文字改为「扫描并自动注册用户下载的模型」
  - v1.1.18-patch3: 块说明文字加「不影响已注册模型」 (绿色高亮)
  - v1.1.18-patch4: 删「📋 新模型注册参数」块下方冗余说明文字
  - v1.1.17-patch5: 修复 repeat_penalty select 不显示问题 (String(1.0) === '1')
  - v1.1.17: 新增「📋 新模型注册参数」块
  + 新增独立配置文件: config/ollama_manifest_generate_parameter.json (项目内, 手动创建)
  + 新增 GET/POST /api/manifest_gen_params 端点
  + 新增 HTML 「📋 新模型注册参数」块 (与 「🎯 Ollama 默认值」 独立, 不覆盖)
  * 5 个生成 manifest 参数: num_ctx / temperature / top_p / top_k / repeat_penalty
  * UI: input + datalist 下拉, 预设常用值 + 标记推荐值
  * 默认值: num_ctx=131072, temperature=0.7, top_p=0.95, top_k=20, repeat_penalty=1.0
  * GET 文件不存在 → 404 (不兑底) - 文件手动创建, 不自动初始化
  - 不动现有 「🎯 Ollama 默认值」 块 (仍是 Modelfile 写 + tag 重建)
  - 不动 beellama / comfyui / 现有 6 个模型 / auto_register_gguf
- v1.1.16: 「⚙️ Ollama 全局参数」块简化为只露 GPU_LAYERS
  * 重命名: 「⚙️ Ollama 全局参数」→ 「🎛️ Ollama 进程参数」(明确是进程 env 层, 不是模型层)
  - 删除 UI 输入框: KEEP_ALIVE / NUM_PARALLEL / BATCH_SIZE / FLASH_ATTENTION (4 个)
    - 原因: 已在 override.conf 锁为最优值, per-model 也不能管, 99% 用户不会动
  * 保留: GPU_LAYERS (需要依显卡设置)
  + 文本提示: 常见显卡推荐值表 (2080Ti=35 / 3090=99 / 4090=99 / A100=99 / CPU=0)
  * API GET: 返回全部 5 字段 (其他 4 字段从 _OLLAMA_DEFAULT_GLOBAL 硬编码补齐)
  * API POST: 只接 gpu_layers, 写 override.conf 时用 _OLLAMA_DEFAULT_GLOBAL 补齐其他 4 字段
  * 不动: beellama / comfyui / 现有 6 个模型 / 任何 Modelfile / auto_register_gguf
- v1.1.15: 「➕ 添加/移除模型进列表」零配置注册 GGUF
  + 新增 /api/auto_register_gguf: 扫描 /data/ollama/models/blobs/, 对未被 manifest 引用的 GGUF 自动创建
    params blob (num_ctx=131072) + config blob + manifest, 无需走 ollama create (秒级, 不解析权重)
  * 修正「🎯 模型 & 参数」位置提示: ollama 路径 ~/.ollama/models/ → /data/ollama/models/ (与 override.conf 一致)
  + 提示文末增加「GGUF 放到 blobs/ 后, 点 ➕ 添加/移除模型进列表 自动注册」说明
  * JS addModelsToList: 扫描完成后检查未注册 GGUF, 弹进度遮罩调 auto_register
  * 复用现有 load-status-area 进度遮罩组件 (无需新 UI)
  - 影响范围: 仅 ollama 框架, 不动 beellama/comfyui
  - 兼容性: auto_register 是新增端点, 旧客户端不受影响
- v1.1.14: ollama 模型列表显示优化 + dedupe 隐藏不带 ctx 基础 tag
  + bge/embed 不再硬编码排除, 走 hidden 列表默认隐藏 (可见可手动启用)
  + _load_hidden() 首次启动自动把 bge/embed 加入 ollama hidden
  * _dedupe_ollama_models: 无衍生 tag 时不再返回基础名 (避免默认 2K ctx)
  + 白名单 qwen3.6-uncensored (历史, 已配 num_ctx 131072)
  - 移除 get_ollama_models / fallback 路径的 bge 硬编码 continue
  - D 修复: 新建 qwen3:14b-ctx96k tag (65536 → 98304), 删旧 :ctx64k
  - A 修复: 新建 gemma4:26b-ctx96k tag (Modelfile 131072 → 98304), 删旧 :ctx64k
  + openclaw models.json: 加 qwen3.6-uncensored 条目, 删 qwen2.5:14b/qwen2.5vl:latest
  + openclaw models.json: gemma4:26b contextWindow 256000 → 98304
  * vram_switcher_state.json: resident_model qwen2.5:14b → qwen3.6-q3:ctx128k
  * MEMORY.md: 常驻模型同步更新
- v1.1.13: qwen3-vl 模型 OOM 修复
  - 问题：qwen3-vl:ctx128k 加载时报 "cudaMalloc failed: out of memory (1.4GB)"
  - 根因：2080Ti (22GB) 显存碎片化 + vision 模型需要大块连续 buffer
         Ollama 0.30.0-rc23 分配 128K KV cache 时失败
  - 修复：推荐值从 128K → 64K (实际测试可正常加载)
  - 修改: 下拉框默认从 128K 改为 64K，Modelfile 同步更新
  - 保留：用户仍可以手动选择 128K/256K，但可能 OOM
- v1.1.12: Bug fix - ollama defaults API 返回空数据/保存失败
  - 症状：点击"保存 ollama defaults"按钮后报错，API 返回空数据
  - 根因：defaults.json 文件历史格式是顶层直接 _fallback/models (为 beellama 设计)
         v1.1.8-patch2 添加 ollama 支持后，API 期望嵌套结构 defaults["ollama"]
         但没有向后兼容迁移逻辑，导致旧格式文件读取时 ollama 段缺失
  - 修复：_load_defaults() 增加迁移逻辑 - 检测到旧格式时自动包装到 ollama 段并保存
  - 影响：首次加载时自动迁移旧格式，之后 API 正常读写
- v1.1.11: Bug fix - ollama 默认值卡片输入值被清空
  - 症状：在 ollama 默认值卡片中填写"当前模型默认值"的 num_ctx/temperature/top_p 时，值写进去后马上消失
  - 根因：renderOllamaDefaults() 函数中，设置 input value 的代码被放在 if (!ncElGlobal) 块内，只有首次渲染时才执行
          后续渲染（如切换模型后刷新）时跳过 value 设置，导致 input 被重置为空
  - 修复：将 value 设置逻辑移到 if 块外，确保每次渲染都更新 input 值
  - 影响范围：仅影响 ollama 默认值卡片的"当前模型默认值"输入框
- v1.1.10: Bug fixes 升版 (全量测试发现)
  - 整合 v1.1.8-patch3 (3 个 bug fix: ollama dedupe + timeout 180s + gemma alias)
  - 代码相对 v1.1.8-patch3 无任何改动
- v1.1.8-patch3: Bug fixes (从全量测试中发现)
  - Bug 1: ollama 下拉框同时显示基础名 + 衍生 tag, 用户选基础名会跳过 per-model num_ctx 配置
    - 根因: get_ollama_models() 未隐藏基础名, 保留全部 tag
    - 修复: 新增 _dedupe_ollama_models() 优先返回 -ctx<N>k 衍生 tag, 隐藏基础名 + :latest
    - 例: 'qwen3.6-q3' / 'qwen3.6-q3:latest' / 'qwen3.6-q3:ctx128k' -> 只显示 'qwen3.6-q3:ctx128k'
    - 额外修复: 识别混用的后缀名 ('-ctx<N>k' 和 ':ctx<N>k' 两种)
  - Bug 2: beellama load timeout 120s 太短, 35B/26B 模型实际需 >120s
    - 修复: subprocess.run timeout 120 -> 180
    - 影响: 35B qwen3.6-q3 完整加载 + health check 需 90-110s, 之前常被 kill
  - Bug 3: switch-inference.sh BEELLAMA_MODELS 用 'gemma4', framework-manager 用 'gemma-4-26b'
    - 修复: switch-inference.sh 两处改为 'gemma-4-26b' (BEELLAMA_MODELS + MODELS 数组的 key)
    - 根因: v1.0.3 后 alias 改了, switch-inference.sh 未同步
  - 未动: beellama / comfyui 加载 / ollama service pipeline / 现有端点
- v1.1.9: 多框架三层参数体系 (ComfyUI + Ollama 对齐 beellama)
  - 整合 patch1: ComfyUI 启动参数 + 模型路径管理
  - 整合 patch2: Ollama 三层参数 (global + per-model Modelfile + defaults)
  - 完成后三个框架都支持多层参数设置
  - 代码相对 v1.1.8-patch2 无任何改动
- v1.1.8-patch2: Ollama 三层参数 (global + per-model Modelfile + defaults)
  - 架构: 与 beellama 三层对齐
  - global: /api/ollama_global_params (GET/POST) - KEEP_ALIVE/NUM_PARALLEL/BATCH_SIZE/GPU_LAYERS/FLASH_ATTENTION
    - 写 ~/.config/systemd/user/ollama.service.d/override.conf (保留 HOST/MODELS + 注释)
    - daemon-reload + restart + 等侍 API 就绪
  - per-model: /api/ollama_model_params (GET/POST) - num_ctx(主) + temperature/top_p/top_k/repeat_penalty
    - 写 /data/ollama/models/modelfiles/<name>.Modelfile
    - num_ctx 改变会创建新 tag (e.g. ctx128k→ctx256k), 调 ollama create 重建
    - 旧 tag 不删 (用户手动选择)
  - defaults: /api/ollama_defaults (GET/POST) - 复用 framework-manager-defaults.json 的 ollama 段
  - 恢复默认: /api/restore_ollama_default_model_params (POST) - 读 defaults → 写 Modelfile → 重建 tag
  - HTML: 「⚙️ Ollama 全局参数」+「📦 Ollama 模型专属参数」+「🎯 Ollama 默认值」三卡片 (仅切到 ollama 时显示)
  - 未动: beellama / comfyui / ollama 加载模型 / ollama system service pipeline
- v1.1.8-patch1: ComfyUI 启动参数 + 模型路径管理
  - 新增 API: /api/comfyui_params (GET/POST) - LowVRAM/GPU only/listen/preview_method
  - 新增 API: /api/comfyui_extra_paths (GET/PUT) - base_path + custom_paths (yaml)
  - 启动参数: 写 ~/.config/systemd/user/comfyui.service + daemon-reload + restart
  - 模型路径: 写 /data/ComfyUI/extra_model_paths.yaml + restart + 重扫模型
  - get_comfyui_models: 优先从 yaml 读, 未配置则 fall back 到硬编码列表
  - HTML: 「⚙️ ComfyUI 启动参数」+「📂 ComfyUI 模型路径」两卡片 (仅在切到 comfyui 时显示)
  - 参数儲存位置: framework-manager.json 的 framework_params.comfyui.global
  - 未动: comfyui service 启动 / 加载模型 / pipeline 逻辑
  - 未动: beellama / ollama 所有逻辑
- v1.1.8: 升版基线 (整合 v1.1.7-patch1..7 修复)
  - 整合 patch1: 修正「模型 & 参数」位置提示为各框架规范路径
  - 整合 patch2: 拆「隐藏」按钮为「➕ 添加 / ➖ 移除」两个
  - 整合 patch3: 「➕ 添加模型进列表」改为弹模态框 + 复选框选择
  - 整合 patch4: 修复 refresh() 未同步 currentFramework 全局变量
  - 整合 patch5: 删除「➖ 移除模型出列表」按钮 (被模态框覆盖)
  - 整合 patch6: 修复 ollama 刚切换后加载报错 (Connection refused)
  - 整合 patch7: 加载不同模型后「默认值」卡片不刷新
  - 说明: 仅作版本基线, 代码相对 v1.1.7-patch7 无任何改动
- v1.1.7-patch7: 加载不同模型后「默认值」卡片不刷新
  - 症状: beellama 加载 gemma-4-26b 后, defaults 卡片仍显示上一个模型 (如 qwen3.6-q3)
  - 根因: refresh() 只更新 JS currentModel 变量和 DOM, 不重渲染 defaults 卡片
            须手动调 renderDefaults(), 之前从未自动调
  - 修复: refresh() 检测到 currentModel 变化时自动调 renderDefaults()
  - 验证: 加载 qwen3.6-q3 → defaults 卡片显示 qwen3.6-q3
            加载 gemma-4-26b → defaults 卡片自动切换为 gemma-4-26b
- v1.1.7-patch6: 修复 ollama 刚切换后加载报错 (Connection refused)
  - 根因: switch_framework_to 启动 ollama.service 后不等待 API 就绪
            用户立即点加载, ollama API 还没起来, urlopen 报错
  - 修复: ollama 加载前轮询 /api/tags, 最多等 30 秒
  - 进度条: 等侍期间 progress=10, 让用户看到状态
  - 验证: 手动停 ollama → 切到 ollama → 点加载 → 3s 后 API 就绪 → 成功加载
- v1.1.7-patch5: 删除「➖ 移除模型出列表」按钮 (被模态框覆盖)
  - 原因: 「➕ 添加/移除模型」模态框已能承担移除功能 (取消勾选)
  - HTML: 合并 2 个按钮为 1 个 (按钮文字改为「➕ 添加/移除模型进列表」)
  - JS: 删除 removeModelFromList 函数
  - 保留: /api/hide_model 端点 (API 保留, 前端不直接调用)
  - 保留: 「⚙️ 默认设置」卡片的「隐藏的模型」区 + ↁ 恢复按钮 (兜底恢复路径)
- v1.1.7-patch4: 修复 refresh() 未同步 currentFramework 全局变量
  - 症状: 「➕ 添加模型进列表」/「➖ 移除模型」点击后报"未加载框架" (toast)
  - 根因: refresh() 函数从 /api/status 拿到 fw 但只设到 DOM textContent, 未赋给 JS 全局 currentFramework
  - 修复: 在 refresh() 中同步 currentFramework = fw (与 currentModel 同步方式一致)
  - 影响: 下游 addModelsToList/removeModelFromList/confirmAddModels 全部正常
- v1.1.7-patch3: 「➕ 添加模型进列表」改为弹模态框 + 复选框选择
  - 替换: 之前一键全加 (调 /api/refresh_models)
  + 新增: /api/scan_for_addition?framework=X GET (返回该框架全量 + visible + hidden)
  + 新增: /api/set_visible_models POST (接受 visible 列表, 计算 hidden = all - visible)
  + 新增: HTML 「➕ 添加模型」模态框 (复选框列表 + 全选/全不选/反选)
  * JS: addModelsToList 改为弹模态框流程
  + 新增 JS: renderAddModelsList + addModelsSelectAll/None/Invert + cancelAddModels + confirmAddModels
  * 保留: /api/refresh_models 端点 (备用于一键重置, 当前不调用)
  * 保留: /api/hide_model + /api/unhide_model (被「➖ 移除模型」按钮继续用)
- v1.1.7-patch2: 拆「隐藏」按钮为「➕ 添加 / ➖ 移除」两个
  - 删除: 「🗑 隐藏」按钮 (v1.1.7)
  + 新增: 「➕ 添加模型进列表」按钮 → 调 /api/refresh_models
    行为: 强制重扫默认位置 + 清空 hidden 列表 (恢复所有被移除的)
  + 新增: 「➖ 移除模型出列表」按钮 (原隐藏按钮, 只改名)
  + 新增: /api/refresh_models 端点 (清 cache + 清 hidden + 立即重扫)
  * JS: hideSelectedModel → removeModelFromList (改名)
  + JS: addModelsToList 新函数
- v1.1.7-patch1: 修正「模型 & 参数」位置提示为各框架规范路径
  - beellama: 任意目录 *.gguf (wrapper 默认扫 ~/models/)
  - ollama:   ~/.ollama/models/ (默认; 环境变量 OLLAMA_MODELS 可改)
  - comfyui:  extra_model_paths.yaml 配置的目录 (默认 $ComfyUI/models/)
  - 移除之前错误的 /data/... 提示 (那是用户自定义路径, 不是框架默认)
- v1.1.7: 「🎯 模型 & 参数」位置提示 + 软移除 + 修复 comfyui 扫描路径
  + HTML: 三个框架的推荐保存位置提示
  + HTML: 「📥 加载模型」旁加「🗑 隐藏」按钮
  + HTML: 「⚙️ 默认设置」底部加「隐藏的模型」区, 可点 ↩️ 恢复
  + /api/hidden_models (GET) + /api/hide_model + /api/unhide_model 端点
  + 隐藏配置: ~/.openclaw/config/framework-manager-hidden.json
  * 修复 get_comfyui_models 扫描路径: 之前只扫 ~/ComfyUI (源码), 补加 /data/ComfyUI (实际部署)
  + /data/ComfyUI/models 加子目录: checkpoints/gguf/diffusion_models/loras
- v1.1.6: 重组到 scripts/framework-manager/ 子目录 + 删除孤儿仓库
  - 3 个文件移动: framework-manager.py / beellama-wrapper.sh / switch-inference.sh
  - SWITCH_SCRIPT / LOG_FILE 改为 __file__ 相对路径 (不再硬编码 ~/.openclaw/scripts/)
  - systemd unit (framework-manager + beellama) ExecStart 改为新路径
  - 删除 ~/.openclaw/framework-manager/ 独立 git 仓库 (原是技术债务, 未被任何服务引用)
- v1.1.5: 「➕ 添加新模型」被动流程 + defaults 卡片重构
  - 新增 /api/init_model_with_fallback: 用 _fallback 初始化新模型 (写 defaults+per-model+启动)
  - 改 /api/load_model: 检测到无 per-model 时返回 missing_in_defaults=true (不静默报错)
  - 前端: 加载无配置模型 → 弹模态框「用 _fallback 初始化?」→ 用户确认
  - defaults 卡片重构: 只显示当前加载模型 + _fallback (不再列出全部)
  - 保存逻辑改为只改 _fallback + 当前模型, 避免误覆盖其他模型
- v1.1.4: 新增「🎯 默认值」系统 + wrapper 简化为纯配置驱动
  - 新增独立 defaults 文件: framework-manager-defaults.json
    结构: {_fallback: {ctx/parallel/ngl}, models: {name: {...}}}
  - 新增「🎯 默认值」卡片: 编辑 _fallback + 各模型默认值
  - 新增 /api/defaults (GET/POST) 端点
  - 新增 /api/restore_default_model_params: 从 defaults 读值→写入 per-model→重启 beellama
  - 「🔄 恢复默认」按钮行为变更: 从 defaults 文件读取值覆盖 per-model (不再清空)
  - 首次启动自动初始化 defaults.json (默认 128K+2+ngl99, 各模型值预填)
  - 启动时一次性迁移 _migrate_legacy_models: 为 4 个老模型补全 per-model 缺失字段
    保留用户已设值, 只补 None 字段; 幂等可重跑
  - 后续: 「➕ 添加新模型」功能将用 _fallback 值初始化新模型 (未在本版实现)
- v1.1.3: 移除"应用推荐"功能 + 简化推荐/默认值体系
  - 需求: 统一默认值与推荐值，移除独立的"应用推荐"按钮
  - WebUI: 删除"✨ 应用推荐"按钮 + 推荐配置预览 + "应用推荐 = 最优配置"提示
  - API: 删除 /api/recommended_defaults (GET) 和 /api/apply_recommended (POST)
  - Python: 删除 RECOMMENDED_MODEL_DEFAULTS 字典 (原 qwen3.6-q3/qwen3-14b/gemma-4-26b/qwen3-vl 推荐值)
  - 逻辑: 加载模型时不再自动初始化为推荐值 — per-model 配置完全由用户手动维护
  - 后续: wrapper 默认值已对齐原推荐值, 唯一区别 qwen3-14b: PARALLEL 4→2
  - 未知模型处理由 wrapper 负责 (报错退出 + 提示用户去 WebUI 手动配置)
- v1.1.1: 模型专属参数卡片保存/重置期间显示进度遮罩
  - CSS: 新增 .processing-overlay (半透明遮罩 + spinner)
  - JS: saveInProgress 标志防止 refresh() 在保存期间隐藏卡片
  - UX 优化: 用户看到连续的"保存中..."状态, 无视觉断点
- v1.1.0: beellama 高级参数配置 (KV 量化/FlashAttn/Reasoning + per-model ctx/parallel/ngl)
  - Web UI 新增"⚙️ beellama 参数设置"卡片 (KV Cache 量化/Flash Attn/Reasoning)
  - Web UI 新增"📦 模型专属参数"卡片 (加载模型后自动显示)
  - 端点 /api/save_and_apply_model_params: 保存→重启→重载全自动 (一个端点完成)
  - beellama-wrapper: 智能短别名映射 (basename ↔ qwen3.6-q3), 优先匹配配置文件
  - 配置结构升级: framework_params.beellama = {global: {...}, models: {name: {...}}}
- v1.0.4: beellama 端 KV cache 放回 VRAM (turbo3 量化) + 并发/ctx 全面提升
  - beellama-wrapper.sh: 删 --no-kv-offload，KV 从 CPU 内存 → GPU VRAM
  - 并发/ctx 提档 (配合 turbo3 1-2GB/parallel):
      qwen3-14b:    64K+2   → 128K+4   (~13 GB)
      gemma-4-26b:  64K+1   → 128K+1   (~17 GB)
      qwen3-vl-8b:  128K+2  → 128K+4   (~10 GB)
      qwen3.6-35b:  128K+1  → 128K+2   (~20 GB 临界)
  - turbo3 默认启用 (switch-inference.sh 默认 turbo_level=3)
  - 收益: 推理速度提升 (KV 在 GPU 比 CPU 快 5-10x), 释放 CPU RAM
  - 质量: turbo3 3-bit KV 精度损失可忽略
  - 回退: wrapper 改回 --no-kv-offload + ctx/parallel 恢复 v1.0.2 值
- v1.0.3: ollama 端 num_ctx 改为 per-model Modelfile 配置 (对齐 beellama 端)
  - 新建 5 个 Modelfile (/data/ollama/models/modelfiles/), 用 ollama create 建立独立 tag:
      bge-m3:ctx8k         (8K,  embedding 够用)
      qwen3:14b-ctx64k     (64K, 对齐 beellama qwen3-14b)
      gemma4:26b-ctx64k    (64K, 对齐 beellama gemma4)
      qwen3.6-q3:ctx128k   (128K, 对齐 beellama qwen3.6-q3)
      qwen3-vl:ctx128k     (128K, 对齐 beellama qwen3-vl)
  - systemd override.conf: 删除 OLLAMA_CONTEXT_LENGTH=32768 全局 32K 设置
    保留 OLLAMA_KEEP_ALIVE=10m, OLLAMA_NUM_PARALLEL=1
  - switch-inference.sh: OLLAMA_TAGS 列表 + list() 显示; 默认 tag 引用改为新 tag
  - 效果: 轻量模型 (qwen3-14b 9GB) 不再被 32K 全局值限制; 各模型 num_ctx 与 beellama 完全对齐
  - 兼容性: 原 tag (qwen3:14b, gemma4:26b 等) 仍保留, 不影响现有调用
- v1.0.2: 修复 OOM 根因 (beellama 并行 4 + 128K 必爆 VRAM) + 修 ollama 永久驻留
  - beellama-wrapper.sh: 4 个 case 的 CTX/PARALLEL 改为按模型差异化推荐值
    qwen3-14b: 131K+4 → 64K+2
    gemma-4-26b: 131K+4 → 64K+1
    qwen3-vl-8b: 131K+4 → 128K+2
    qwen3.6-35b: 131K+4 → 128K+1
  - ollama.service.d/override.conf: KEEP_ALIVE=-1 → 10m, NUM_PARALLEL=2 → 1, CONTEXT_LENGTH=98304 → 32768
  - 彻底消除 "connected| error" 错误 (beellama 端 OOM) 和 idle 回退失效 (ollama 端永久驻留)
- v1.0.1: 修复空闲回退失效 (_check_gpu_idle/_check_engine_active 误重置 last_activity_time)
- v1.0.0: 初始正式版本。Ollama/Beellama/ComfyUI 框架切换，模型热切换，
  空闲超时自动回退默认设置，操作日志审计与 Web UI 显示，队列监控
"""

import os, sys, json, time, hashlib, subprocess, signal, threading, logging, re
from pathlib import Path
from datetime import datetime

import flask
from flask import Flask, request, jsonify, render_template_string

# ── 配置 ──────────────────────────────────────────────────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 9528
SWITCH_SCRIPT = os.path.join(_THIS_DIR, "switch-inference.sh")
OLLAMA_SERVICE = "ollama.service"
BEELLAMA_SERVICE = "beellama.service"
COMFYUI_SERVICE = "comfyui.service"
OLLAMA_PORT = 11434
BEELLAMA_PORT = 8080
COMFYUI_PORT = 8188
LOG_FILE = os.path.join(_THIS_DIR, "framework-manager-audit.log")
CONFIG_DIR = os.path.expanduser("~/.openclaw/config")
CONFIG_FILE = os.path.join(CONFIG_DIR, "framework-manager.json")

# 默认值文件 (v1.1.4 新增): 独立存储各模型的推荐/默认参数
# 与 framework-manager.json 解耦, 只被「🎯 默认值」卡片读写
# 结构: {_fallback: {...}, models: {short_name: {...}}}
DEFAULTS_FILE = os.path.join(CONFIG_DIR, "framework-manager-defaults.json")

# 隐藏模型列表 (v1.1.7 新增): 从下拉框中隐藏但不删除文件
# 结构: {beellama: [path1, ...], ollama: [name1, ...], comfyui: [path1, ...]}
HIDDEN_MODELS_FILE = os.path.join(CONFIG_DIR, "framework-manager-hidden.json")

# v1.1.8 新增: ComfyUI 相关路径
COMFYUI_DIR = "/home/wangyc/ComfyUI"  # v1.3.0-patch1: 修正路径 (原 /data/ComfyUI 是旧部署)
COMFYUI_EXTRA_PATHS_YAML = os.path.join(COMFYUI_DIR, "extra_model_paths.yaml")
COMFYUI_USER_SERVICE_DIR = os.path.expanduser("~/.config/systemd/user")
COMFYUI_SERVICE_FILE = os.path.join(COMFYUI_USER_SERVICE_DIR, "comfyui.service")

# v1.1.8-patch2 新增: Ollama 相关路径
OLLAMA_OVERRIDE_DIR = os.path.expanduser("~/.config/systemd/user/ollama.service.d")
OLLAMA_OVERRIDE_FILE = os.path.join(OLLAMA_OVERRIDE_DIR, "override.conf")
OLLAMA_MODELS_DIR = "/data/ollama/models"  # 与 override.conf 中 OLLAMA_MODELS 一致
OLLAMA_MODELFILES_DIR = os.path.join(OLLAMA_MODELS_DIR, "modelfiles")

# v1.1.17: 「📋 新模型注册参数」 文件 (项目内, 与 ~/.openclaw/config 独立)
PROJECT_CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
MANIFEST_GEN_PARAMS_FILE = os.path.join(PROJECT_CONFIG_DIR, "ollama_manifest_generate_parameter.json")
# manifest 生成参数合法字段 (顺序 = UI 顺序)
_MANIFEST_GEN_PARAM_FIELDS = ["num_ctx", "temperature", "top_p", "top_k", "repeat_penalty"]
# v1.1.18: ingest_gguf 兑底参数 (「📋 新模型注册参数」 文件不存在时使用, 仅 ingest 路径)
_MANIFEST_GEN_PARAMS_DEFAULTS_FOR_INGEST = {
    "num_ctx": 131072,
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 20,
    "repeat_penalty": 1.0,
}

# 首次启动初始化内容 (从原 wrapper 4 case 导入 + 统一默认)
_DEFAULT_FALLBACK = {"ctx_size": 131072, "parallel": 2, "ngpu_layers": 99}
_DEFAULT_MODELS = {
    "qwen3.6-q3":  {"ctx_size": 131072, "parallel": 1, "ngpu_layers": 99},
    "qwen3-14b":   {"ctx_size": 131072, "parallel": 2, "ngpu_layers": 99},
    "gemma-4-26b": {"ctx_size": 131072, "parallel": 1, "ngpu_layers": 99},
    "qwen3-vl":    {"ctx_size": 131072, "parallel": 4, "ngpu_layers": 99},
}

app = Flask(__name__)
log = logging.getLogger("framework-manager")
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

# ── 审计日志 ───────────────────────────────────────────────────────
def audit_log(action, detail="", status="ok"):
    """写入审计日志文件：仅记录框架/模型的加载、切换操作"""
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {action:20s} | {detail:50s} | {status}\n"
        with open(LOG_FILE, "a") as f:
            f.write(line)
    except Exception:
        pass

# ── 默认配置 ───────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "default_framework": "beellama",
    "default_model": "",
    "idle_timeout": 300,
    "framework_params": {
        "beellama": {
            "global": {
                "turbo_level": "",
                "flash_attn": True,
                "reasoning_off": True
            },
            "models": {}
        },
        "ollama": {},
        "comfyui": {}
    }
}

# ── 全局状态 ───────────────────────────────────────────────────────
current_framework = None
current_model = None
last_activity_time = time.time()
idle_reset_thread = None
stop_idle_thread = threading.Event()

# ── 模型加载状态（用于前端实时反馈） ─────────────────────────────
_loading_state = {
    "status": "idle",       # idle | loading | done | error
    "framework": None,
    "model": None,
    "start_time": 0,
    "eta_seconds": 60,      # 预估最大加载时间
    "message": "",
    "progress": 0,          # 0-100
}

# 待自动加载的模型（用户保存参数/恢复默认值时设置，beellama 重启后自动加载）
_pending_model = None

# ── 辅助函数 ───────────────────────────────────────────────────────
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                for k, v in DEFAULT_CONFIG.items():
                    config.setdefault(k, v)
                return config
        except Exception as e:
            log.error(f"加载配置失败：{e}")
    return DEFAULT_CONFIG.copy()

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        log.error(f"保存配置失败：{e}")


def _load_defaults():
    """加载默认值文件。不存在则首次初始化 (原 wrapper 4 case 值 + 统一默认)"""
    if not os.path.exists(DEFAULTS_FILE):
        defaults = {
            "_fallback": _DEFAULT_FALLBACK.copy(),
            "models": {k: v.copy() for k, v in _DEFAULT_MODELS.items()}
        }
        try:
            os.makedirs(os.path.dirname(DEFAULTS_FILE), exist_ok=True)
            with open(DEFAULTS_FILE, 'w') as f:
                json.dump(defaults, f, indent=2, ensure_ascii=False)
            audit_log("初始化默认值文件",
                      f"path={DEFAULTS_FILE}, fallback={defaults['_fallback']}, models={list(defaults['models'].keys())}",
                      "ok")
        except Exception as e:
            log.error(f"初始化默认值文件失败: {e}")
            return defaults
    try:
        with open(DEFAULTS_FILE, 'r') as f:
            data = json.load(f)
        # v1.1.18: 向后兼容迁移 - 如果文件是旧格式 (顶层直接 _fallback/models)，自动包装到 ollama 段
        if "ollama" not in data and "_fallback" in data:
            # 这是旧格式，迁移到新格式
            log.info("检测到旧格式 defaults.json，迁移到 ollama 段")
            data["ollama"] = {
                "_fallback": data.get("_fallback", {}).copy(),
                "models": {k: v.copy() for k, v in data.get("models", {}).items()}
            }
            # 保留旧格式在顶层 (向后兼容 beellama 等其他框架)
            _save_defaults(data)
        return data
    except Exception as e:
        log.error(f"加载默认值文件失败：{e}")
        return {"_fallback": _DEFAULT_FALLBACK.copy(), "models": {}, "ollama": {"_fallback": {}, "models": {}}}


def _save_defaults(defaults):
    """保存默认值文件"""
    try:
        os.makedirs(os.path.dirname(DEFAULTS_FILE), exist_ok=True)
        with open(DEFAULTS_FILE, 'w') as f:
            json.dump(defaults, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        log.error(f"保存默认值文件失败: {e}")
        return False


def _load_hidden():
    """加载隐藏模型列表, 不存在则返回空结构
    v1.1.14: 首次启动时自动把 bge/embed 类模型加入 ollama hidden
              (可见但默认不在下拉列表, 用户可手动添加/移出)
    """
    if not os.path.exists(HIDDEN_MODELS_FILE):
        # 首次启动: 扫描 ollama 列表, 把 bge/embed 默认加入 hidden
        default_hidden = {"beellama": [], "ollama": [], "comfyui": []}
        try:
            # 直接调 subprocess 避免循环依赖
            import subprocess as _sp
            out = _sp.check_output(["ollama", "list"], text=True, stderr=_sp.DEVNULL, timeout=5)
            for line in out.strip().split("\n")[1:]:
                if line.strip():
                    name = line.split()[0].lower()
                    if name.startswith("bge") or "embed" in name:
                        default_hidden["ollama"].append(line.split()[0])
        except Exception:
            pass
        # 写文件固化
        _save_hidden(default_hidden)
        return default_hidden
    try:
        with open(HIDDEN_MODELS_FILE, 'r') as f:
            data = json.load(f)
        for k in ("beellama", "ollama", "comfyui"):
            data.setdefault(k, [])
        return data
    except Exception as e:
        log.error(f"加载隐藏列表失败: {e}")
        return {"beellama": [], "ollama": [], "comfyui": []}


def _save_hidden(hidden):
    """保存隐藏模型列表"""
    try:
        with open(HIDDEN_MODELS_FILE, 'w') as f:
            json.dump(hidden, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        log.error(f"保存隐藏列表失败: {e}")
        return False


def _migrate_legacy_models():
    """v1.1.4 一次性迁移: 为 defaults.json 中列出的模型补全 per-model 缺失字段
    背景: v1.1.4 删除 wrapper 4 case 写死, 改为从 per-model 读取
    后果: 4 个老模型必须 per-model 三字段齐全才能启动
    策略: 保留用户已设值 (非 None), 只补 None 字段
    幂等: 多次调用结果一致, 可安全重跑
    """
    try:
        defaults = _load_defaults()
        config = load_config()
        models_cfg = (
            config
            .setdefault("framework_params", {})
            .setdefault("beellama", {})
            .setdefault("models", {})
        )
        migrated = []
        for short_name, default_params in defaults.get("models", {}).items():
            pm = models_cfg.setdefault(short_name, {})
            for field in ("ctx_size", "parallel", "ngpu_layers"):
                # 只补 None 字段, 保留用户已设值
                if pm.get(field) is None and default_params.get(field) is not None:
                    pm[field] = default_params[field]
                    migrated.append(f"{short_name}.{field}={default_params[field]}")
        if migrated:
            save_config(config)
            audit_log("迁移老模型 per-model",
                      f"补全字段: {', '.join(migrated)}", "ok")
        return len(migrated)
    except Exception as e:
        log.error(f"迁移老模型失败: {e}")
        return 0


def get_nvidia_vram():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.total,memory.used", "--format=csv,noheader,nounits"],
            text=True
        )
        lines = out.strip().split("\n")
        if not lines:
            return (0, 0)
        total, used = map(int, lines[0].split(","))
        return (total, used)
    except Exception:
        return (0, 0)

def _dedupe_ollama_models(raw_models):
    """v1.1.8-patch3 + v1.1.14: 从原始 tag 列表中, 优先保留带 ctx 后缀的衍生 tag
    例: ['qwen3:14b-ctx64k', 'qwen3:14b', 'gemma4:26b', 'gemma4:26b-ctx64k']
        -> ['gemma4:26b-ctx64k', 'qwen3:14b-ctx64k']  (隐藏基础名, 避免走默认 2K ctx)
    注意: ollama tag 命名不规范, 上下文后缀混用 '-ctx' 和 ':ctx':
      - 短名 (gemma4:26b-ctx64k, qwen3:14b-ctx64k, bge-m3:ctx8k) 用 '-'
      - 长名 (qwen3.6-q3:ctx128k, qwen3-vl:ctx128k) 用 ':'
    另外: ollama Hub 拉取的原始 tag 会自动建 :latest 别名, 也视为基础名
      - qwen3.6-q3 / qwen3.6-q3:latest / qwen3.6-q3:ctx128k -> 只保留 :ctx128k
    v1.1.14 修改: 不再保留 ':latest' / 基础名
      - 即便 base 没有衍生 tag, 也只返回衍生 tag (空集时不返回)
      - 避免用户加载走默认 2048 ctx 的基础 tag
      - 例外: qwen3.6-uncensored:latest (历史, 实际已配 num_ctx 131072) → 保留
    """
    import re
    # 同时识别 :ctx<N>k 和 -ctx<N>k 后缀
    ctx_suffix_re = re.compile(r'[-:]ctx\d+k$')
    ctx_k_re = re.compile(r'ctx(\d+)k')
    # 去掉 :latest / -ctx<N>k 后缀得到 base name
    base_strip_re = re.compile(r':latest$|[-:]ctx\d+k$')
    # v1.1.14: 例外白名单 (这些 tag 虽不带 :ctx 后缀, 但实际 num_ctx > 2048)
    _NUM_CT_OK_BASE = {"qwen3.6-uncensored"}  # ollama show 显示 num_ctx=131072
    by_base = {}  # base_name -> [tag, ...]
    for m in raw_models:
        base = base_strip_re.sub('', m)
        by_base.setdefault(base, []).append(m)
    result = []
    for base, tags in by_base.items():
        ctx_tags = [t for t in tags if ctx_suffix_re.search(t)]
        if ctx_tags:
            # 只保留衍生 tag (按 ctx 升序)
            result.extend(sorted(ctx_tags, key=lambda x: int(ctx_k_re.search(x).group(1))))
        elif base in _NUM_CT_OK_BASE:
            # v1.1.14 例外: 已知 num_ctx > 2048 的基础 tag, 保留
            result.extend(tags)
        # else: base 既无衍生 tag 又不在白名单 → 不返回 (默认 2K, 加载必踩坑)
    return sorted(set(result))


def get_ollama_models():
    """
    获取 Ollama 模型列表。
    Ollama 服务运行中 -> ollama list 实时拉取。
    Ollama 未运行 -> 从本地 manifest 目录回退，展示已下载的模型。

    v1.1.8-patch3: 优先返回 -ctx<N>k 衍生 tag (含 per-model num_ctx 配置)
                    隐藏对应的基础 tag, 避免用户加载基础 tag 后走默认 2K ctx
                    例: 返回 qwen3:14b-ctx64k, 隐藏 qwen3:14b
    """
    try:
        out = subprocess.check_output(["ollama", "list"], text=True, stderr=subprocess.DEVNULL)
        lines = out.strip().split("\n")[1:]
        raw_models = []
        for line in lines:
            if line.strip():
                name = line.split()[0]
                # v1.1.14: 不再硬编码排除 bge/embed, 改为走 hidden 列表 (默认隐藏, 可手动添加/移出)
                raw_models.append(name)
        return _dedupe_ollama_models(raw_models)
    except Exception:
        pass
    # ollama 未运行时的 fallback：扫描本地已下载的模型 manifest
    # 只列出原始 tag，跳过衍生 tag（如 -ctx64k、ctx128k），避免重复
    # 衍生 tag 的 manifest 中 layers[].from 指向本地同目录下的另一个 tag
    # Hub 原始 tag 的 latest 指向 Ollama Hub 原始名称，不算本地衍生
    try:
        manifests = []
        seen_bases = set()
        for base in [Path.home() / ".local/share/ollama/models/manifests/registry.ollama.ai/library",
                     Path("/data/ollama/models/manifests/registry.ollama.ai/library")]:
            if not base.exists():
                continue
            for model_dir in base.iterdir():
                if not model_dir.is_dir():
                    continue
                for tag_file in model_dir.iterdir():
                    if not tag_file.is_file():
                        continue
                    tag = tag_file.name
                    name = model_dir.name if tag == "latest" else f"{model_dir.name}:{tag}"
                    # v1.1.14: 不再硬编码排除 bge, 走 hidden 列表
                    # 跳过衍生 tag：layers 中有 from 字段且 from 指向本地同目录下的 tag（排除自身）
                    # 原始 tag 的 from 可能指向自身（如 gemma4:26b 的 from="gemma4:26b"），不算衍生
                    try:
                        manifest_data = json.loads(tag_file.read_text())
                        is_derivative = False
                        for layer in manifest_data.get("layers", []):
                            src = layer.get("from", "")
                            if src and src != name:
                                # 解析 src 的 tag 部分（格式：model_dir_name:tag）
                                if ":" in src:
                                    src_tag = src.split(":", 1)[1]
                                else:
                                    src_tag = src
                                # 如果 from 指向同目录下的另一个 tag，则为衍生
                                if src_tag in [tf.name for tf in model_dir.iterdir() if tf.is_file()]:
                                    is_derivative = True
                                    break
                        if is_derivative:
                            continue
                    except Exception:
                        pass
                    base_key = model_dir.name
                    if base_key not in seen_bases:
                        seen_bases.add(base_key)
                        manifests.append(name)
        # v1.1.8-patch3: 优先返回 -ctx<N>k 衍生 tag, 隐藏对应基础名
        return _dedupe_ollama_models(sorted(manifests))
    except Exception:
        return []
def unload_ollama_models():
    import urllib.request, urllib.error

    try:
        req = urllib.request.Request("http://localhost:11434/api/ps")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        for m in data.get("models", []):
            name = m.get("name", "")
            if name and 'bge' not in name.lower() and 'embed' not in name.lower():
                payload = json.dumps({"model": name, "keep_alive": -1, "stream": False}).encode()
                try:
                    req2 = urllib.request.Request("http://localhost:11434/api/chat", data=payload,
                        headers={"Content-Type": "application/json"}, method="POST")
                    urllib.request.urlopen(req2, timeout=5).read()
                except Exception:
                    pass
    except Exception as e:
        log.warning(f"卸载模型失败: {e}")

def get_beellama_models():
    """扫描 beellama 模型目录，支持多个可能的位置
    v1.0.9: 修复重复扫描导致 8 个模型变 4 个的问题
    """
    possible_dirs = [
        Path.home() / "models" / "beellama",
        Path.home() / "models",  # 也可能直接在 ~/models 下
        Path("/data/ollama/models/blobs"),  # Ollama blob 目录备用
    ]
    models = set()
    seen_paths = set()  # 用绝对路径去重（避免 ~/models vs ~/models/beellama 重复）
    for model_dir in possible_dirs:
        if not model_dir.exists():
            continue
        # 扫描 GGUF 文件
        for gguf in model_dir.rglob("*.gguf"):
            if not gguf.is_file():
                continue
            # 跳过 mmproj 视觉投影文件（不是可加载的 LLM 模型）
            if 'mmproj' in gguf.name.lower():
                continue
            # 用绝对路径去重
            abs_path = str(gguf.resolve())
            if abs_path in seen_paths:
                continue
            seen_paths.add(abs_path)
            # 使用相对路径作为模型标识
            try:
                rel_path = gguf.relative_to(model_dir)
                models.add(str(rel_path))
            except ValueError:
                models.add(gguf.name)
    return sorted(models)

def get_comfyui_models():
    """扫描 ComfyUI 模型，支持子目录和多种模型类型
    v1.1.7: 加 /data/ComfyUI/models 实际部署路径, 原来只扫 ~/ComfyUI (源码) 扫不到任何实际模型
    v1.1.8: 优先从 extra_model_paths.yaml 读 base_path + custom_paths, 未配置则 fall back 到硬编码列表
    """
    # v1.1.8: 优先从 yaml 读路径
    yaml_cfg = _read_comfyui_yaml()
    yaml_based = False
    model_dirs = []
    if yaml_cfg and yaml_cfg.get("base_path"):
        base = Path(yaml_cfg["base_path"])
        # base_path 默认包含 models/{checkpoints,gguf,diffusion_models,loras}
        for sub in ("checkpoints", "gguf", "diffusion_models", "loras", "diffusers", "unet"):
            d = base / "models" / sub
            if d.exists():
                model_dirs.append(d)
                yaml_based = True
        # custom_paths 直接拼绝对路径
        for cat, p in (yaml_cfg.get("custom_paths") or {}).items():
            d = Path(p)
            if d.exists():
                model_dirs.append(d)
                yaml_based = True
    if not yaml_based:
        # 兼容: 未配 yaml 时使用硬编码列表
        model_dirs = [
            # 实际部署路径 (优先)
            Path("/data/ComfyUI/models/checkpoints"),
            Path("/data/ComfyUI/models/diffusers"),
            Path("/data/ComfyUI/models/unet"),
            Path("/data/ComfyUI/models/gguf"),
            Path("/data/ComfyUI/models/diffusion_models"),
            Path("/data/ComfyUI/models/loras"),
            # 源码 demo 路径 (兼容, 旧脚本)
            Path.home() / "ComfyUI" / "models" / "checkpoints",
            Path.home() / "ComfyUI" / "models" / "diffusers",
            Path.home() / "ComfyUI" / "models" / "unet",
        ]
    models = []
    for model_dir in model_dirs:
        if not model_dir.exists():
            continue
        # 扫描文件
        for ext in (".ckpt", ".safetensors", ".pth", ".pt", ".gguf"):
            for f in model_dir.rglob(f"*{ext}"):
                if f.is_file():
                    try:
                        rel_path = f.relative_to(model_dir)
                        models.append(str(rel_path))
                    except ValueError:
                        models.append(f.name)
        # 扫描子目录（针对 diffusers 格式或分拆模型）
        for subdir in model_dir.iterdir():
            if subdir.is_dir() and not subdir.name.startswith('.'):
                # 检查子目录是否包含模型文件
                has_model = any(subdir.rglob("*.safetensors")) or \
                           any(subdir.rglob("*.ckpt")) or \
                           any(subdir.rglob("*.pth"))
                if has_model:
                    models.append(f"{subdir.name}/")
    return sorted(set(models))

# 模型列表缓存（带时间戳，避免频繁扫描）
_model_cache = {"ollama": None, "beellama": None, "comfyui": None}
_cache_timestamps = {"ollama": 0, "beellama": 0, "comfyui": 0}

def get_framework_models(framework, force_refresh=False):
    """获取指定框架的模型列表，带缓存机制
    
    Args:
        framework: 框架名称 (ollama/beellama/comfyui)
        force_refresh: 强制刷新缓存
    
    Returns:
        模型列表
    """
    import time
    current_time = time.time()
    cache_age = current_time - _cache_timestamps.get(framework, 0)
    
    # 缓存有效期 30 秒，或强制刷新时重新扫描
    if not force_refresh and _model_cache.get(framework) and cache_age < 30:
        return _model_cache[framework]
    
    # 重新扫描
    if framework == "ollama":
        models = get_ollama_models()
    elif framework == "beellama":
        models = get_beellama_models()
    elif framework == "comfyui":
        models = get_comfyui_models()
    else:
        models = []

    # v1.1.7: 过滤隐藏模型
    hidden = _load_hidden()
    models = [m for m in models if m not in hidden.get(framework, [])]

    _model_cache[framework] = models
    _cache_timestamps[framework] = current_time
    return models

def is_service_running(service):
    try:
        out = subprocess.check_output(["systemctl", "--user", "is-active", service], text=True, stderr=subprocess.DEVNULL)
        return out.strip() == "active"
    except Exception:
        return False

def get_service_pid(service):
    try:
        out = subprocess.check_output(["systemctl", "--user", "show", service, "-p", "MainPID"], text=True)
        pid = out.strip().split("=")[1]
        return pid if pid.isdigit() else None
    except Exception:
        return None

def run_cmd(cmd, timeout=10):
    """执行 shell 命令，返回 (ok, stdout)"""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, f"timeout ({timeout}s)"
    except Exception as e:
        return False, str(e)

def stop_service(service):
    try:
        subprocess.run(["systemctl", "--user", "stop", service], check=True, timeout=10)
        return True
    except Exception as e:
        log.error(f"停止服务 {service} 失败：{e}")
        return False

def start_service(service):
    try:
        subprocess.run(["systemctl", "--user", "start", service], check=True, timeout=20)
        return True
    except Exception as e:
        log.error(f"启动服务 {service} 失败：{e}")
        return False


# ── ComfyUI service / yaml 读写 (v1.1.8 新增) ──────────────────────
# 原因: 之前启动参数 (--lowvram) 和模型路径都是硬编码, 用户改不动
# 设计: 参数写 framework-manager.json 的 framework_params.comfyui.global
#       路径写 extra_model_paths.yaml (ComfyUI 原生支持)
#       service file 仅存储最简 ExecStart 框架, 具体 flag 由代码动态拼接

_COMFYUI_DEFAULT_PARAMS = {
    "lowvram": True,        # 默认开启 (匹配当前 service)
    "gpu_only": False,
    "listen": False,        # 0.0.0.0 监听 (默认仅 127.0.0.1, 安全)
    "preview_method": "auto",  # auto | latent2rgb | taesd | none
}


def _read_comfyui_service_execstart():
    """读 comfyui.service 的 ExecStart 行, 解析出 main.py 的 flag 列表
    返回: list[str] (不含 'main.py' 也不含 python3)
    """
    try:
        with open(COMFYUI_SERVICE_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith("ExecStart="):
                    # 去掉前缀, 按空白切分
                    cmd = line[len("ExecStart="):]
                    parts = cmd.split()
                    # 跳过第一个 (python 可执行文件)
                    if parts:
                        parts = parts[1:]
                    # 跳过 main.py
                    if parts and parts[0].endswith("main.py"):
                        parts = parts[1:]
                    return parts
    except Exception:
        pass
    return []


def _write_comfyui_service_execstart(flags):
    """重写 comfyui.service 的 ExecStart 行 (保留 [Unit]/[Service] 其他段)
    flags: list[str] (不含 main.py 也不含 python3)
    """
    try:
        with open(COMFYUI_SERVICE_FILE, 'r') as f:
            content = f.read()
        new_line = f"ExecStart=/usr/bin/python3 main.py {' '.join(flags)}".rstrip()
        # 替换现有的 ExecStart=
        import re
        new_content = re.sub(r'^ExecStart=.*$', new_line, content, flags=re.MULTILINE)
        if 'ExecStart=' not in new_content:
            # 不存在则追加到 [Service] 段
            new_content = re.sub(
                r'(\[[Ss]ervice\])',
                f'\\1\n{new_line}',
                new_content,
                count=1
            )
        with open(COMFYUI_SERVICE_FILE, 'w') as f:
            f.write(new_content)
        return True
    except Exception as e:
        log.error(f"写 comfyui.service 失败: {e}")
        return False


def _flags_to_comfyui_params(flags):
    """从 flag 列表解析为 params dict (反向提取 _COMFYUI_DEFAULT_PARAMS 字段)
    未知 flag 保留在 extra_flags, 不丢失
    """
    known = {
        "--lowvram": "lowvram",
        "--gpu-only": "gpu_only",
        "--listen": "listen",
        "--preview-method": "preview_method",
    }
    p = _COMFYUI_DEFAULT_PARAMS.copy()
    p["extra_flags"] = []  # 未知 flag
    i = 0
    while i < len(flags):
        f = flags[i]
        if f in known and known[f] != "preview_method":
            p[known[f]] = True
            i += 1
        elif f in known and known[f] == "preview_method":
            if i + 1 < len(flags):
                p["preview_method"] = flags[i + 1]
                i += 2
            else:
                i += 1
        elif f == "--lowvram" or f == "--gpu-only" or f == "--listen":
            # 兜底: bool flag
            p[known.get(f, f.lstrip("-").replace("-", "_"))] = True
            i += 1
        else:
            # 未知 flag, 保留 (含值)
            if i + 1 < len(flags) and not flags[i + 1].startswith("-"):
                p["extra_flags"].extend([f, flags[i + 1]])
                i += 2
            else:
                p["extra_flags"].append(f)
                i += 1
    return p


def _comfyui_params_to_flags(params):
    """从 params dict 生成 flag 列表
    """
    flags = []
    if params.get("lowvram"):
        flags.append("--lowvram")
    if params.get("gpu_only"):
        flags.append("--gpu-only")
    if params.get("listen"):
        flags.append("--listen")
    pm = params.get("preview_method")
    if pm and pm != "auto":
        flags.extend(["--preview-method", pm])
    # 追加未知 flag
    flags.extend(params.get("extra_flags") or [])
    return flags


# ── extra_model_paths.yaml 读写 (v1.1.8 新增) ──────────────────────
# 结构 (ComfyUI 原生格式):
#   comfyui:
#     base_path: /data/ComfyUI
#     custom_paths:
#       checkpoints: /path/to/checkpoints
#       loras: /path/to/loras

_DEFAULT_COMFYUI_YAML = """# ComfyUI 模型路径配置 (framework-manager v1.1.8 自动生成)
# 修改后需重启 comfyui.service 生效
# 字段说明:
#   base_path:    ComfyUI 模型根目录, 子目录 checkpoints/diffusion_models/gguf/loras 自动扫
#   custom_paths: 额外的分类路径 (key = 分类名, value = 绝对路径)
comfyui:
  base_path: /data/ComfyUI
  custom_paths: {}
"""


def _read_comfyui_yaml():
    """读 extra_model_paths.yaml, 返回 {base_path, custom_paths}
    不存在或解析失败: 返回默认值 (不创建, 让调用方决定)
    """
    if not os.path.exists(COMFYUI_EXTRA_PATHS_YAML):
        return None
    try:
        import yaml
        with open(COMFYUI_EXTRA_PATHS_YAML, 'r') as f:
            data = yaml.safe_load(f) or {}
        comfy = data.get("comfyui", {}) or {}
        return {
            "base_path": comfy.get("base_path", ""),
            "custom_paths": comfy.get("custom_paths", {}) or {},
        }
    except Exception as e:
        log.error(f"读 extra_model_paths.yaml 失败: {e}")
        return None


def _write_comfyui_yaml(base_path, custom_paths):
    """写 extra_model_paths.yaml"""
    try:
        import yaml
        data = {
            "comfyui": {
                "base_path": base_path,
                "custom_paths": custom_paths or {},
            }
        }
        with open(COMFYUI_EXTRA_PATHS_YAML, 'w') as f:
            f.write(_DEFAULT_COMFYUI_YAML.split("# ComfyUI 模型路径配置")[0])  # 注释行
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        return True
    except Exception as e:
        log.error(f"写 extra_model_paths.yaml 失败: {e}")
        return False


# ── Ollama service / Modelfile 读写 (v1.1.8-patch2 新增) ────────────────
# 原因: 之前 systemd 环境变量 + per-model Modelfile 都是手写, WebUI 不可控
# 设计:
#   global   - 写 ~/.config/systemd/user/ollama.service.d/override.conf
#              字段: OLLAMA_KEEP_ALIVE / OLLAMA_NUM_PARALLEL / OLLAMA_BATCH_SIZE
#                    OLLAMA_GPU_LAYERS / OLLAMA_FLASH_ATTENTION
#                    (HOST/MODELS 为环境信息, 不从 WebUI 改)
#   per-model - 写 /data/ollama/models/modelfiles/<name>.Modelfile
#              字段: num_ctx (主) / temperature / top_p / top_k / repeat_penalty
#              保存后调 ollama create 重建 tag: <base>-ctx<N>k
#   defaults - 复用 framework-manager-defaults.json, 加 ollama 段
#              {ollama: {_fallback: {...}, models: {name: {...}}}}

_OLLAMA_GLOBAL_FIELD_MAP = {
    # field_name → env_var_name
    "keep_alive": "OLLAMA_KEEP_ALIVE",
    "num_parallel": "OLLAMA_NUM_PARALLEL",
    "batch_size": "OLLAMA_BATCH_SIZE",
    "gpu_layers": "OLLAMA_GPU_LAYERS",
    "flash_attention": "OLLAMA_FLASH_ATTENTION",
}
_OLLAMA_DEFAULT_GLOBAL = {
    "keep_alive": "10m",
    "num_parallel": 1,
    "batch_size": None,  # 不设
    "gpu_layers": None,  # 不设
    "flash_attention": 1,
}

# per-model Modelfile 字段 (顺序 = 写入顺序)
_OLLAMA_MODEL_PARAM_FIELDS = [
    "num_ctx", "temperature", "top_p", "top_k", "repeat_penalty",
]


def _read_ollama_override_conf():
    """读 override.conf, 解析为 {field_name: value, ...}
    仅提取白名单字段 (不碰 OLLAMA_HOST/OLLAMA_MODELS 等结构字段)
    """
    if not os.path.exists(OLLAMA_OVERRIDE_FILE):
        return _OLLAMA_DEFAULT_GLOBAL.copy()
    try:
        result = _OLLAMA_DEFAULT_GLOBAL.copy()
        with open(OLLAMA_OVERRIDE_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                m = re.match(r'^Environment="(OLLAMA_[A-Z_]+)=(.+)"$', line)
                if not m:
                    continue
                var, val = m.group(1), m.group(2)
                for field, ev in _OLLAMA_GLOBAL_FIELD_MAP.items():
                    if var == ev:
                        # int 字段尝试转 int
                        if field in ("num_parallel", "batch_size", "gpu_layers", "flash_attention"):
                            try:
                                val = int(val)
                            except ValueError:
                                pass
                        result[field] = val
        return result
    except Exception as e:
        log.error(f"读 override.conf 失败: {e}")
        return _OLLAMA_DEFAULT_GLOBAL.copy()


def _write_ollama_override_conf(params):
    """写 override.conf (保留 [Service] 头 + 注释, 替换/追加白名单 Environment 行)
    params: {keep_alive, num_parallel, batch_size, gpu_layers, flash_attention}
    """
    try:
        os.makedirs(OLLAMA_OVERRIDE_DIR, exist_ok=True)
        # 读现有内容 (保留非白名单 Environment 行 + 注释)
        existing_lines = []
        if os.path.exists(OLLAMA_OVERRIDE_FILE):
            with open(OLLAMA_OVERRIDE_FILE, 'r') as f:
                existing_lines = f.readlines()
        # 构建新的白名单行
        whitelist_vars = set(_OLLAMA_GLOBAL_FIELD_MAP.values())
        # 过滤现有: 丢弃白名单行, 保留其他
        kept = []
        for line in existing_lines:
            stripped = line.strip()
            m = re.match(r'^Environment="(OLLAMA_[A-Z_]+)=(.+)"$', stripped)
            if m and m.group(1) in whitelist_vars:
                continue
            kept.append(line)
        # 拼接新行
        new_lines = list(kept)
        # 必要时补充间隔
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] = new_lines[-1] + "\n"
        if new_lines and new_lines[-1].strip() != "":
            new_lines.append("\n")
        for field, ev in _OLLAMA_GLOBAL_FIELD_MAP.items():
            val = params.get(field)
            if val is None or val == "":
                continue
            new_lines.append(f'Environment="{ev}={val}"\n')
        with open(OLLAMA_OVERRIDE_FILE, 'w') as f:
            f.writelines(new_lines)
        return True
    except Exception as e:
        log.error(f"写 override.conf 失败: {e}")
        return False


def _modelfile_path_for(model_name):
    """model_name (如 qwen3.6-q3:ctx128k) → Modelfile 路径
    tag 里的 ':' 转为 '-' (文件名合法)
    """
    safe = model_name.replace(":", "-").replace("/", "_")
    return os.path.join(OLLAMA_MODELFILES_DIR, f"{safe}.Modelfile")


def _parse_modelfile(path):
    """读 Modelfile, 解析为 {num_ctx, temperature, top_p, top_k, repeat_penalty, from}
    不存在返回 None
    """
    if not os.path.exists(path):
        return None
    try:
        params = {f: None for f in _OLLAMA_MODEL_PARAM_FIELDS}
        params["from"] = None
        with open(path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("FROM "):
                    params["from"] = line[5:].strip()
                elif line.startswith("PARAMETER "):
                    parts = line[len("PARAMETER "):].split(None, 1)
                    if len(parts) == 2 and parts[0] in _OLLAMA_MODEL_PARAM_FIELDS:
                        v = parts[1].strip()
                        # 尝试转 float/int
                        try:
                            v = int(v) if "." not in v else float(v)
                        except ValueError:
                            pass
                        params[parts[0]] = v
        return params
    except Exception as e:
        log.error(f"读 Modelfile 失败: {path}: {e}")
        return None


def _write_modelfile(path, params, header_lines=None):
    """写 Modelfile
    params: {from, num_ctx, temperature, top_p, top_k, repeat_penalty}
    header_lines: 顶部注释行列表 (可选)
    """
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            if header_lines:
                for hl in header_lines:
                    f.write("# " + hl + "\n")
            f.write("\nFROM " + (params.get("from") or "<unknown>") + "\n\n")
            for field in _OLLAMA_MODEL_PARAM_FIELDS:
                v = params.get(field)
                if v is not None and v != "":
                    f.write(f"PARAMETER {field} {v}\n")
        return True
    except Exception as e:
        log.error(f"写 Modelfile 失败: {path}: {e}")
        return False


def _create_ollama_tag_from_modelfile(modelfile_path, tag_name):
    """调 ollama create <tag_name> -f <modelfile_path>
    返回 (ok, msg)
    """
    try:
        r = subprocess.run(
            ["/home/wangyc/.local/bin/ollama", "create", tag_name, "-f", modelfile_path],
            capture_output=True, text=True, timeout=120
        )
        if r.returncode == 0:
            return True, r.stdout.strip()
        return False, r.stderr.strip() or r.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "ollama create 超时 (>120s)"
    except Exception as e:
        return False, f"ollama create 失败: {e}"


def _tag_from_model_name(model_name):
    """model_name → tag name (e.g. qwen3.6-q3 + num_ctx=131072 → qwen3.6-q3:ctx128k)
    规则: ctx round 到 K → 8k/16k/32k/64k/128k/256k
    """
    # 不接管已有 tag (如 :ctx128k 结尾) — 直接返回
    if re.search(r':ctx\d+k$', model_name):
        return model_name
    # 否则期望输入是 base 名, 需要额外 ctx; 此函数只负责 round, 调用方拼装
    raise ValueError("use _make_ollama_tag for base name")


def _ctx_to_ollama_tag_suffix(num_ctx):
    """num_ctx → ctx<N>k 字符串 (8k/16k/32k/64k/128k/256k)
    不足 8K 补足到 8K, 然后向下取整到最近的幂阶
    """
    if not num_ctx or num_ctx < 8192:
        return "ctx8k"
    # 允许的阶
    steps = [8, 16, 32, 64, 128, 256, 512, 1024]
    k = num_ctx // 1024
    for s in steps:
        if k <= s:
            return f"ctx{s}k"
    return f"ctx{steps[-1]}k"


def _make_ollama_tag(base_name, num_ctx):
    """base_name + num_ctx → 完整 tag (e.g. qwen3.6-q3 + 131072 → qwen3.6-q3:ctx128k)"""
    suffix = _ctx_to_ollama_tag_suffix(num_ctx)
    # base_name 可能已带 :tag, 剥掉
    base = base_name.split(":")[0]
    return f"{base}:{suffix}"

def detect_current_framework():
    """检测当前运行的框架，并尝试识别已加载的模型

    注意：
    - 如果已有框架选择（非初次检测），不切换框架，仅检测模型
    - beellama 下通过 health + 简单推理验证模型是否真正就绪，
      防止进程已启动但模型还在加载中时错误显示模型名
    """
    global current_framework, current_model

    def _try_infer_beellama():
        """尝试检测 beellama 是否真正就绪（health + 推理测试）
        返回 (模型名 or None, 是否真正就绪)
        """
        import urllib.request
        import urllib.error

        # 1. 先检查 health 端点（服务进程是否存活）
        health_ok = False
        try:
            req = urllib.request.Request(f"http://localhost:{BEELLAMA_PORT}/health")
            resp = urllib.request.urlopen(req, timeout=3)
            if resp.status == 200:
                health_ok = True
        except Exception:
            pass

        if not health_ok:
            return None, False

        # 2. health 通过后，做简单推理验证模型是否真的已加载到显存
        infer_ok = False
        try:
            payload = json.dumps({
                "model": "test",
                "messages": [{"role": "user", "content": "1"}],
                "max_tokens": 2
            }).encode()
            req = urllib.request.Request(
                f"http://localhost:{BEELLAMA_PORT}/v1/chat/completions",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=10)
            d = json.loads(resp.read())
            infer_ok = "choices" in d
        except Exception:
            pass

        # 3. 从进程命令行提取模型名（仅用于展示）
        # ⚡ 修复：使用精确的可执行文件路径匹配，避免被残留 bash 进程（含模糊文本匹配）干扰
        model_name = None
        ok, cmdline = run_cmd("pgrep -af '/home/wangyc/beellama.cpp/build/bin/llama-server' | grep -v pgrep | grep -v bash | head -1")
        if ok and cmdline:
            import re
            mm = re.search(r'-m\s+(\S+)', cmdline)
            if mm:
                gguf_path = mm.group(1)
                # v1.6.1: 复用 _extract_short_model_name(), 之前硬编码 if/elif 链把
                # 'qwen3.6-35b-uncensored/Qwen3.6-35B-A3B-Uncensored-...gguf' 也识别成
                # 'qwen3.6-q3', 导致加载 uncensored 后 /api/status 错显 'qwen3.6-q3'
                model_name = _extract_short_model_name(gguf_path)

        return model_name, infer_ok

    # 如果已经有框架选择，不要覆盖（除非是启动时的初次检测）
    if current_framework is not None and current_framework != "":
        # 只在已有框架下检测模型，不切换框架
        if current_framework == "ollama":
            import urllib.request
            try:
                req = urllib.request.Request("http://localhost:11434/api/ps")
                resp = urllib.request.urlopen(req, timeout=3)
                data = json.loads(resp.read())
                models = data.get("models", [])
                llm_models = [m for m in models if 'bge' not in m.get('name','').lower() and 'embed' not in m.get('name','').lower()]
                if llm_models:
                    raw = llm_models[-1].get('name', '')
                    current_model = raw
            except Exception:
                pass
        elif current_framework == "beellama":
            # ⚡ 修复：验证模型是否真正就绪，避免显示正在加载中的模型
            model_name, infer_ok = _try_infer_beellama()
            if infer_ok and model_name:
                current_model = model_name
                log.info(f"beellama 模型推理就绪：{model_name}")
            elif model_name:
                # 虽然进程有 -m 参数指定了模型，但还没推理就绪 → 清空模型名
                log.info(f"beellama 进程有模型 {model_name} 但未就绪，清空显示")
                current_model = None
            else:
                log.info("beellama 未加载任何模型")
                current_model = None
        return

    # 初次启动时的检测
    if is_service_running(OLLAMA_SERVICE):
        current_framework = "ollama"
        import urllib.request
        try:
            req = urllib.request.Request("http://localhost:11434/api/ps")
            resp = urllib.request.urlopen(req, timeout=3)
            data = json.loads(resp.read())
            models = data.get("models", [])
            llm_models = [m for m in models if 'bge' not in m.get('name','').lower() and 'embed' not in m.get('name','').lower()]
            if llm_models:
                raw = llm_models[-1].get('name', '')
                current_model = raw
        except Exception:
            pass

    elif is_service_running(BEELLAMA_SERVICE):
        current_framework = "beellama"
        # ⚡ 初次检测也用推理验证
        model_name, infer_ok = _try_infer_beellama()
        if infer_ok and model_name:
            current_model = model_name
            log.info(f"检测到 beellama 模型推理就绪：{model_name}")
        elif model_name:
            log.info(f"beellama 进程有模型 {model_name} 但未就绪，清空显示")
            current_model = None
        else:
            log.info("beellama 未加载任何模型")
            current_model = None

    elif is_service_running(COMFYUI_SERVICE):
        current_framework = "comfyui"

    else:
        current_framework = None

def switch_framework_to(target_framework):
    global current_framework, current_model, last_activity_time

    # 停止所有服务，然后彻底清理残留进程，确保端口释放
    for svc in [OLLAMA_SERVICE, BEELLAMA_SERVICE, COMFYUI_SERVICE]:
        stop_service(svc)
    # 用 pgrep + kill 组合，确保杀干净所有 llama-server（killall 可能受 cgroup 限制）
    run_cmd("kill -9 $(pgrep llama-server 2>/dev/null) 2>/dev/null; true", timeout=3)
    run_cmd("pkill -9 -f 'beellama-wrapper' 2>/dev/null; true", timeout=3)
    time.sleep(2)

    success = False
    if target_framework == "ollama":
        success = start_service(OLLAMA_SERVICE)
    elif target_framework == "beellama":
        # ⚡ 切换到 beellama 时，先写入 NONE 标记，让 wrapper 仅激活服务不加载模型
        _write_beella_none_flag()
        success = start_service(BEELLAMA_SERVICE)
    elif target_framework == "comfyui":
        success = start_service(COMFYUI_SERVICE)
    if success:
        current_framework = target_framework
        current_model = None  # ⚡ 切换框架后清空模型名，等待显式加载
        last_activity_time = time.time()
        audit_log("切换框架", f"→ {target_framework}", "ok")
        return True
    # 启动失败：重置框架检测，让 UI 正确反映实际状态
    current_framework = None
    current_model = None
    detect_current_framework()
    audit_log("切换框架", f"→ {target_framework}", "fail")
    return False

def load_model_for_framework(model_name):
    """加载模型到当前框架

    Ollama: 通过 API 保持模型在显存中
    Beellama: 调用 switch-inference.sh 进行热切换
    ComfyUI: 仅记录，动态加载
    """
    global current_model, last_activity_time, _loading_state

    if not current_framework:
        _loading_state.update({"status": "error", "framework": None, "model": None,
                               "message": "未选择框架", "progress": 0})
        return False, "未选择框架"

    # ⚡ 立即更新活动时间，防止加载慢导致空闲回退线程误触发
    last_activity_time = time.time()

    # 设置加载中状态（立即反馈给前端）
    _loading_state.update({
        "status": "loading",
        "framework": current_framework,
        "model": model_name,
        "start_time": time.time(),
        "message": f"正在使用 {current_framework} 加载 {model_name} 中...",
        "progress": 5,
    })

    # 刷新模型列表确保最新
    models = get_framework_models(current_framework, force_refresh=True)

    # ── Ollama: 通过 API 加载模型 ─────────────────────────────────────
    if current_framework == "ollama":
        import urllib.request
        import urllib.error

        # v1.1.7-patch6: 修复 ollama 刚切换后 API 未就绪导致 Connection refused
        # 轮询 /api/tags 等待就绪, 最多 30 秒
        for _ in range(30):
            try:
                urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1).close()
                break
            except Exception:
                _loading_state.update({"message": f"等 Ollama API 就绪...", "progress": 10})
                time.sleep(1)
        else:
            return False, "Ollama API 30 秒未就绪, 请检查 ollama.service 状态"

        # 检查模型是否在列表中（允许部分匹配）
        model_matched = False
        for m in models:
            if m == model_name or m.replace(':latest', '') == model_name.replace(':latest', ''):
                model_matched = True
                break

        if not model_matched:
            _loading_state.update({"status": "error", "message": f"模型 {model_name} 不可用", "progress": 0})
            return False, f"模型 {model_name} 在 Ollama 中不可用。可用：{', '.join(models[:5])}..."

        _loading_state.update({"message": f"正在使用 Ollama 加载 {model_name}...", "progress": 20})

        # v1.1.14: 先定义 ollama_model_name (用于后面的检查)
        ollama_model_name = model_name
        if ':' not in model_name:
            ollama_model_name = model_name + ':latest'

        # 检查当前模型是否已在内存中, 避免不必要的 unload+reload
        try:
            ps_req = urllib.request.Request("http://localhost:11434/api/ps")
            ps_resp = urllib.request.urlopen(ps_req, timeout=5)
            ps_data = json.loads(ps_resp.read())
            loaded_names = [m.get("name", "") for m in ps_data.get("models", [])]
        except Exception:
            loaded_names = []

        # 判断当前已加载的模型名称是否匹配目标模型
        already_loaded = False
        target_tag = ollama_model_name
        for ln in loaded_names:
            # 比较 base name (去掉 tag)
            ln_base = ln.split(':')[0] if ':' in ln else ln
            target_base = target_tag.split(':')[0]
            if ln_base == target_base:
                already_loaded = True
                break

        if not already_loaded:
            # v1.1.14: 仅在模型未加载时才卸载当前所有模型
            unload_ollama_models()

        _loading_state.update({"message": f"正在使用 Ollama 加载 {model_name}...", "progress": 40})

        # 2. 通过 /api/generate 加载模型到显存
        payload = json.dumps({
            "model": ollama_model_name,
            "prompt": "",
            "stream": False,
            "keep_alive": -1
        }).encode()

        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            resp = urllib.request.urlopen(req, timeout=300)
            result = json.loads(resp.read())
            log.info(f"Ollama 模型 {ollama_model_name} 加载结果：{result}")
            current_model = model_name
            last_activity_time = time.time()
            audit_log("加载模型", f"Ollama/{model_name}", "ok")
            _loading_state.update({"status": "done", "message": f"{model_name} 已加载到 Ollama", "progress": 100})
            return True, f"模型 {model_name} 已加载到 Ollama"
        except urllib.error.URLError as e:
            _loading_state.update({"status": "error", "message": f"Ollama API 不可用: {e}", "progress": 0})
            return False, f"Ollama API 不可用：{e}"
        except Exception as e:
            _loading_state.update({"status": "error", "message": f"模型加载失败: {e}", "progress": 0})
            return False, f"模型加载失败：{e}"

    # ── Beellama: 调用 switch-inference.sh ──────────────────────────
    elif current_framework == "beellama":
        # 检查模型名是否在列表中（兼容短别名 qwen3.6-q3 / 完整路径 / basename）
        model_matched = model_name in models
        if not model_matched:
            # 别名匹配: qwen3.6-q3 ↔ qwen3.6-35b/Qwen_Qwen3.6-35B-A3B-Q3_K_M.gguf
            alias_map = {
                'qwen3.6-q3': 'qwen3.6-35b',
                'qwen3.6-uncensored': 'qwen3.6-35b-uncensored',  # v1.2.0-patch1: 补齐 alias, 否则 beellama 队列找不到此模型
                'qwen3-vl': 'qwen3-vl',
                'gemma4': 'gemma-4-26b',
            }
            alias_key = alias_map.get(model_name, model_name)
            for m in models:
                if alias_key.lower() in m.lower():
                    model_matched = True
                    break
        if not model_matched:
            _loading_state.update({"status": "error", "message": f"模型 {model_name} 不可用", "progress": 0})
            return False, f"模型 {model_name} 在当前框架 {current_framework} 中不可用"

        # 从完整路径提取短模型名 (与 beellama-wrapper.sh 提取规则保持一致)
        # v1.1.4: gemma 改用 gemma-4-26b 与 wrapper regex 对齐
        short_model_name = _extract_short_model_name(model_name)

        log.info(f"模型名转换：{model_name} -> {short_model_name}")
        _loading_state.update({
            "message": f"正在使用 beellama 加载 {short_model_name} 中...",
            "model": short_model_name,
            "progress": 15
        })

        try:
            cmd = [SWITCH_SCRIPT, "beellama", short_model_name, "0", "3"]
            log.info(f"执行命令：{' '.join(cmd)}")
            _loading_state.update({"message": f"正在使用 beellama 加载 {short_model_name} 中...", "progress": 30})
            # v1.1.8-patch3: timeout 120 -> 180, 35B 加载需 >120s
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

            if result.returncode != 0:
                log.error(f"切换失败：{result.stderr}")
                _loading_state.update({"status": "error", "message": f"切换失败: {result.stderr[:100]}", "progress": 0})
                return False, f"切换 beellama 模型失败：{result.stderr[:200]}"

            log.info(f"切换成功：{result.stdout}")
            _loading_state.update({"message": f"模型 {short_model_name} 加载完成，等待就绪...", "progress": 70})
            time.sleep(3)
            current_model = short_model_name
            last_activity_time = time.time()
            audit_log("加载模型", f"beellama/{short_model_name}", "ok")
            _loading_state.update({"status": "done", "message": f"{short_model_name} 已加载到 beellama", "progress": 100})
            return True, f"模型 {short_model_name} 已加载到 beellama"
        except subprocess.TimeoutExpired:
            _loading_state.update({"status": "error", "message": "加载超时（>120s）", "progress": 0})
            return False, "切换超时（>120s）"
        except Exception as e:
            _loading_state.update({"status": "error", "message": f"加载失败: {e}", "progress": 0})
            return False, f"切换 beellama 模型失败：{e}"

    # ── ComfyUI: 仅记录 ─────────────────────────────────────────────
    elif current_framework == "comfyui":
        if model_name not in models:
            _loading_state.update({"status": "error", "message": f"模型 {model_name} 不可用", "progress": 0})
            return False, f"模型 {model_name} 在当前框架 {current_framework} 中不可用"
        current_model = model_name
        last_activity_time = time.time()
        audit_log("加载模型", f"ComfyUI/{model_name}", "ok")
        _loading_state.update({"status": "done", "message": f"{model_name} 已设置为 ComfyUI 默认模型", "progress": 100})
        return True, f"模型 {model_name} 已设置为 ComfyUI 默认模型（实际使用时动态加载）"

    _loading_state.update({"status": "error", "message": "未知框架", "progress": 0})
    return False, "未知框架"



def _write_beella_none_flag():
    """向 /tmp/beella_model 写入 NONE 标记，使 beellama-wrapper 仅激活不加载模型"""
    import pathlib
    flag_file = pathlib.Path("/tmp/beella_model")
    try:
        flag_file.write_text("NONE 0 0")
        log.info("已写入 NONE 标记到 beella_model（无模型模式）")
    except Exception as e:
        log.warning(f"写入 beella_model NONE 标记失败：{e}")


def stop_all_engines():
    global current_framework, current_model, _loading_state
    stopped = []
    for svc in [OLLAMA_SERVICE, BEELLAMA_SERVICE, COMFYUI_SERVICE]:
        if stop_service(svc):
            stopped.append(svc)
    # 清除所有状态
    current_framework = None
    current_model = None
    _loading_state.update({"status": "idle", "framework": None, "model": None,
                           "message": "", "progress": 0, "start_time": 0})
    return stopped

def get_queue_length():
    """获取队列长度（向后兼容）"""
    return get_queue_info()["total"]

def get_queue_info():
    """获取队列详细信息，包含框架、模型、任务数等
    
    扫描多个可能的队列文件位置
    """
    queue_files = [
        Path.home() / ".openclaw" / "tmp" / "unified_queue.json",
        Path.home() / ".openclaw" / "tmp" / "model_switcher_queue.json",
    ]
    
    all_tasks = []
    framework_counts = {}
    model_counts = {}
    
    for qf in queue_files:
        if not qf.exists():
            continue
        try:
            with open(qf, 'r') as f:
                data = json.load(f)
                if isinstance(data, list):
                    all_tasks.extend(data)
        except Exception:
            pass
    
    # 统计每个框架和模型的任务数
    for task in all_tasks:
        fw = task.get("framework", task.get("engine", "unknown"))
        model = task.get("model", "unknown")
        
        framework_counts[fw] = framework_counts.get(fw, 0) + 1
        model_counts[model] = model_counts.get(model, 0) + 1
    
    return {
        "total": len(all_tasks),
        "by_framework": framework_counts,
        "by_model": model_counts,
        "tasks": all_tasks[:20]  # 只返回前 20 个任务详情
    }

def _normalize_model_name(name):
    """统一模型名为短名称格式，用于比较"""
    if not name:
        return name
    n = name
    if '/' in n:
        n = n.split('/')[0]
    if n.endswith('.gguf'):
        n = n[:-5]
    if 'gemma' in n.lower():
        n = 'gemma4'
    if 'qwen3.6' in n.lower() or 'qwen3.6-35b' in n.lower():
        n = 'qwen3.6-q3'
    if 'qwen3-vl' in n.lower():
        n = 'qwen3-vl'
    if ':' in n:
        n = n.split(':')[0]
    return n


def _check_gpu_idle(threshold=0):
    """检查 GPU 是否空闲：对比两次显存使用量，若无变化则认为空闲"""
    try:
        total1, used1 = get_nvidia_vram()
        time.sleep(2)
        total2, used2 = get_nvidia_vram()
        diff = abs(used2 - used1)
        return diff <= threshold
    except Exception:
        return True  # 检测失败时视为空闲


def _check_has_queued_tasks():
    """检查队列中是否有待处理的任务"""
    qi = get_queue_info()
    return qi.get("total", 0) > 0


def _check_engine_active():
    """检查引擎服务是否存活（不代表正在推理），避免干扰空闲回退"""
    # ⚡ 此函数仅检查服务是否存活，而非模型是否驻留内存。
    #    真正的推理活动由 _check_gpu_idle()（显存变化检测）覆盖。
    #    Ollama 的 keep_alive 会让模型驻留很长时间。
    #    之前 Ollama 分支用 api/ps 检查模型存在性，任何非 bge 模型
    #    都会返回 True 导致 _engine_active()→重置 last_activity_time→
    #    空闲超时永不触发→回退失效。见 Issue: #idle-reset-blocked-by-ps
    #
    #   ✅ _check_engine_active() 现在只确认服务进程在运行。
    #   ✅ 空闲回退依赖于 _check_gpu_idle() + 超时时间。
    return False


def idle_reset_worker():
    global current_framework, current_model, last_activity_time
    while not stop_idle_thread.is_set():
        try:
            time.sleep(10)
            config = load_config()
            default_framework = config.get("default_framework", "beellama")
            default_model = config.get("default_model", "")
            timeout = config.get("idle_timeout", 300)
            if timeout <= 0:
                continue

            loading_status = _loading_state.get("status", "idle")
            if loading_status == "loading":
                continue

            if _check_has_queued_tasks():
                # 有任务在执行：重置活动时间为现在，防止超时误触发
                last_activity_time = time.time()
                continue

            # 注意：以下两个检查只决定本次循环是否触发回退，
            # 不再重置 last_activity_time（偶发 GPU/服务探测波动不应覆盖真实空闲时长）
            if not _check_gpu_idle():
                continue
            if _check_engine_active():
                continue

            norm_current_model = _normalize_model_name(current_model or "")
            norm_default_model = _normalize_model_name(default_model or "")

            if time.time() - last_activity_time > timeout:
                need_framework_switch = (current_framework != default_framework) or (current_framework is None)
                need_model_load = bool(default_model) and (norm_current_model != norm_default_model)

                if not need_framework_switch and not need_model_load:
                    log.info(f"IdleReset: 框架={default_framework} 模型={default_model} 已为默认，已跳过")
                    continue

                if need_framework_switch:
                    log.info(f"IdleReset: 超时{timeout}s，切框架 {current_framework}->{default_framework}")
                    audit_log("空闲回退", f"切框架 {current_framework}->{default_framework}", "ok")
                    switch_framework_to(default_framework)
                    current_model = None
                    if need_model_load:
                        log.info(f"IdleReset: 框架已切换，将加载默认模型 {default_model}")

                if need_model_load:
                    log.info(f"IdleReset: 加载默认模型 {default_model} (当前={norm_current_model})")
                    audit_log("空闲回退", f"加载默认模型 {default_model}", "ok")
                    load_model_for_framework(default_model)

                last_activity_time = time.time()
        except Exception as _idle_err:
            log.error(f"IdleReset: 线程异常: {_idle_err}")
            import traceback
            log.error(traceback.format_exc())

def start_idle_thread():
    global idle_reset_thread
    if idle_reset_thread is None or not idle_reset_thread.is_alive():
        stop_idle_thread.clear()
        idle_reset_thread = threading.Thread(target=idle_reset_worker, daemon=True)
        idle_reset_thread.start()

def stop_idle_thread_func():
    stop_idle_thread.set()
    if idle_reset_thread:
        idle_reset_thread.join(timeout=2)

# ── API 路由 ───────────────────────────────────────────────────────
@app.route("/")
def index():
    config = load_config()
    return render_template_string(INDEX_HTML, port=PORT,
                                  default_framework=config.get("default_framework", "beellama"),
                                  default_model=config.get("default_model", ""),
                                  idle_timeout=config.get("idle_timeout", 300))

@app.route("/api/status")
def api_status():
    global current_framework, current_model, last_activity_time
    detect_current_framework()
    framework_display = "无"
    pid = "—"
    if current_framework == "ollama":
        framework_display = "Ollama"
        pid = get_service_pid(OLLAMA_SERVICE) or "—"
    elif current_framework == "beellama":
        framework_display = "beellama"
        pid = get_service_pid(BEELLAMA_SERVICE) or "—"
    elif current_framework == "comfyui":
        framework_display = "ComfyUI"
        pid = get_service_pid(COMFYUI_SERVICE) or "—"
    total, used = get_nvidia_vram()
    vram_used_mb = used * 1024
    vram_total_mb = total * 1024
    vram_percent = int((used / total) * 100) if total > 0 else 0
    models = get_framework_models(current_framework, force_refresh=False) if current_framework else []
    # v1.6.2-patch4: 顺便返回 short_name, 让「默认设置」下拉可直接复用同一份数据
    if current_framework == "beellama":
        available_display_names = [_extract_short_model_name(m) for m in models]
    else:
        available_display_names = list(models)
    queue_info = get_queue_info()
    return jsonify({
        "framework": framework_display,
        "pid": pid,
        "model": current_model or "—",
        "vram_used_mb": vram_used_mb,
        "vram_total_mb": vram_total_mb,
        "vram_percent": vram_percent,
        "framework_key": current_framework or "—",
        "available_models": models[:10],
        "available_display_names": available_display_names[:10],
        "last_activity": int(time.time() - last_activity_time),
        "queue": queue_info
    })

@app.route("/api/frameworks")
def api_frameworks():
    """获取可用框架列表及当前状态，包含各框架的模型数量"""
    framework_info = {
        "ollama": {"name": "Ollama", "port": OLLAMA_PORT, "running": is_service_running(OLLAMA_SERVICE)},
        "beellama": {"name": "beellama", "port": BEELLAMA_PORT, "running": is_service_running(BEELLAMA_SERVICE)},
        "comfyui": {"name": "ComfyUI", "port": COMFYUI_PORT, "running": is_service_running(COMFYUI_SERVICE)},
    }
    # 添加每个框架的模型数量
    for fw in framework_info:
        models = get_framework_models(fw, force_refresh=True)
        framework_info[fw]["model_count"] = len(models)
    
    return jsonify({
        "available": list(framework_info.keys()),
        "current": current_framework,
        "frameworks": framework_info
    })

@app.route("/api/models")
def api_models():
    """获取模型列表，支持强制刷新参数"""
    if not current_framework:
        return jsonify({"error": "未选择框架"}), 400
    force_refresh = request.args.get("refresh", "false").lower() == "true"
    models = get_framework_models(current_framework, force_refresh=force_refresh)
    return jsonify({"framework": current_framework, "models": models, "cache_refreshed": force_refresh})

@app.route("/api/set_framework", methods=["POST"])
def api_set_framework():
    global last_activity_time
    data = request.get_json(silent=True) or {}
    fw = data.get("framework")
    if fw not in ["ollama", "beellama", "comfyui"]:
        return jsonify({"error": "无效的框架"}), 400
    if switch_framework_to(fw):
        last_activity_time = time.time()
        return jsonify({"status": "ok", "framework": fw})
    return jsonify({"error": f"切换到 {fw} 失败"}), 500

@app.route("/api/load_status")
def api_load_status():
    """获取当前模型加载状态（前端实时轮询用）"""
    ls = _loading_state
    elapsed = time.time() - ls["start_time"] if ls["start_time"] > 0 else 0
    return jsonify({
        "status": ls["status"],
        "framework": ls["framework"],
        "model": ls["model"],
        "message": ls["message"],
        "progress": ls["progress"],
        "elapsed_seconds": round(elapsed, 1),
        "eta_seconds": max(0, ls["eta_seconds"] - round(elapsed)),
    })

@app.route("/api/load_model", methods=["POST"])
def api_load_model():
    data = request.get_json(silent=True) or {}
    model = data.get("model")
    if not model:
        _loading_state.update({"status": "error", "message": "未指定模型", "model": None, "progress": 0})
        return jsonify({"error": "未指定模型"}), 400

    # v1.1.5: 检测 per-model 是否完整. 缺失则返回 missing_in_defaults=true
    # 避免静默调用 wrapper 失败, 前端能弹模态框引导用户初始化
    if current_framework == "beellama":
        short_name = _extract_short_model_name(model)
        config = load_config()
        pm = (config.get("framework_params", {}).get("beellama", {}).get("models", {}).get(short_name, {}))
        miss = [f for f in ("ctx_size", "parallel", "ngpu_layers") if pm.get(f) is None]
        if miss:
            return jsonify({
                "status": "needs_init",
                "missing_in_defaults": True,
                "short_name": short_name,
                "model": model,
                "missing_fields": miss,
                "error": f"模型 {short_name} 缺少配置字段: {', '.join(miss)}",
                "message": "需先用 _fallback 初始化"
            }), 200

    ok, msg = load_model_for_framework(model)
    if ok:
        return jsonify({"status": "ok", "message": msg})
    return jsonify({"error": msg}), 400


@app.route("/api/init_model_with_fallback", methods=["POST"])
def api_init_model_with_fallback():
    """「➕ 添加新模型」被动流程: 用 _fallback 初始化指定模型 → 启动
    流程: 写 defaults (如果未登记) → 写 per-model → 重启 beellama + 重载
    前端在加载无配置模型时, 弹模态框让用户确认后调用
    """
    global current_model, current_framework
    if current_framework != "beellama":
        return jsonify({"error": "当前不是 beellama 框架"}), 400

    data = request.get_json(silent=True) or {}
    model_name = data.get("model")
    if not model_name:
        return jsonify({"error": "未指定模型"}), 400

    short_name = _extract_short_model_name(model_name)
    defaults = _load_defaults()

    # 1) defaults 补充 (如果该模型未登记)
    if short_name not in defaults.get("models", {}):
        defaults.setdefault("models", {})[short_name] = defaults.get("_fallback", {}).copy()
        if not _save_defaults(defaults):
            return jsonify({"error": "写入 defaults.json 失败"}), 500
        audit_log("defaults 补充新模型",
                  f"model={short_name}, source=_fallback={defaults['_fallback']}", "ok")

    # 2) per-model 写入 (从 defaults 读, 保证两端一致)
    config = load_config()
    models_cfg = (
        config
        .setdefault("framework_params", {})
        .setdefault("beellama", {})
        .setdefault("models", {})
    )
    models_cfg[short_name] = {
        "ctx_size": defaults["models"][short_name].get("ctx_size"),
        "parallel": defaults["models"][short_name].get("parallel"),
        "ngpu_layers": defaults["models"][short_name].get("ngpu_layers"),
    }
    save_config(config)
    audit_log("初始化新模型 per-model",
              f"model={short_name}, ctx={models_cfg[short_name]['ctx_size']}, parallel={models_cfg[short_name]['parallel']}", "ok")

    # 3) 重启 + 重载
    return _apply_model_params(model_name)


def _extract_short_model_name(model_path):
    """提取 short_name (同时支持 GGUF 路径 和 short_name 输入)
    提取逻辑与 beellama-wrapper.sh 保持一致, 保证两端 per-model key 统一:
    qwen3.6-35b/Qwen_Qwen3.6-35B-A3B-Q3_K_M.gguf -> qwen3.6-q3
    qwen3-14b/qwen3-14b-q4.gguf -> qwen3-14b
    qwen3-vl/Qwen3-VL-8B-Instruct-Q4_K_M.gguf -> qwen3-vl
    gemma-4-26B-A4B-it-UD-Q4_K_M -> gemma-4-26b
    qwen3.6-q3 (已是 short_name) -> qwen3.6-q3 (原样返回)
    """
    import re
    # 如果输入不含路径分隔符且不以 .gguf 结尾, 可能是 short_name 本身
    if "/" not in model_path and not model_path.endswith(".gguf"):
        return model_path
    # 取 basename (去掉 .gguf)
    basename = model_path.split("/")[-1].replace(".gguf", "")
    # Qwen_Qwen3.6-35B-A3B-Q3_K_M -> qwen3.6-q3
    m = re.match(r"Qwen_Qwen([0-9.]+)-([0-9]+B)-A([0-9]+B)", basename)
    if m:
        return f"qwen{m.group(1)}-q{m.group(2)[0].lower()}"
    # qwen3-vl-8b / Qwen3-VL-8B-... -> qwen3-vl (不区分大小写)
    if re.search(r"qwen3-?vl", basename, re.IGNORECASE):
        return "qwen3-vl"
    # qwen3-14b-q4 -> qwen3-14b
    m = re.match(r"(qwen[0-9.]+(?:-[0-9]+b)?)-q[0-9]", basename)
    if m:
        return m.group(1)
    # gemma-4-26B-... -> gemma-4-26b
    m = re.match(r"gemma-?([0-9]+)-?([0-9]+b)", basename.lower())
    if m:
        return f"gemma-{m.group(1)}-{m.group(2)}"
    # Qwen3.6-35B-A3B-Uncensored-... / Qwen3-30B-A3B-abliterated-... -> qwen3.6-uncensored
    # 简化短名: 去掉 -A<N>B 专家数
    if re.search(r"qwen[0-9.]+-[0-9]+b-a[0-9]+b[-_]?(uncensored|abliterated)", basename.lower()):
        ver = re.match(r"qwen([0-9.]+)", basename.lower()).group(1)
        return f"qwen{ver}-uncensored"
    return basename

@app.route("/api/stop_all", methods=["POST"])
def api_stop_all():
    stopped = stop_all_engines()
    return jsonify({"status": "ok", "stopped": stopped})

@app.route("/api/queue")
def api_queue():
    return jsonify({"length": get_queue_length()})

@app.route("/api/default_config")
def api_default_config():
    config = load_config()
    return jsonify(config)

@app.route("/api/set_default_config", methods=["POST"])
def api_set_default_config():
    data = request.get_json(silent=True) or {}
    config = load_config()
    for key in ["default_framework", "default_model", "idle_timeout"]:
        if key in data:
            config[key] = data[key]
    if config["default_framework"] not in ["ollama", "beellama", "comfyui"]:
        return jsonify({"error": "默认框架无效"}), 400
    try:
        config["idle_timeout"] = int(config["idle_timeout"])
        if config["idle_timeout"] < 0:
            raise ValueError
    except:
        return jsonify({"error": "空闲超时必须是非负整数"}), 400
    save_config(config)
    return jsonify({"status": "ok", "config": config})

@app.route("/api/beellama_params", methods=["GET"])
def api_get_beellama_params():
    """获取 beellama 框架参数设置"""
    config = load_config()
    params = config.get("framework_params", {}).get("beellama", {})
    return jsonify({
        "turbo_level": params.get("turbo_level", ""),
        "flash_attn": params.get("flash_attn", True),
        "reasoning_off": params.get("reasoning_off", True)
    })

@app.route("/api/beellama_params", methods=["POST"])
def api_set_beellama_params():
    """设置 beellama 全局参数"""
    if current_framework != "beellama":
        return jsonify({"error": "当前不是 beellama 框架"}), 400
    data = request.get_json(silent=True) or {}
    config = load_config()
    if "framework_params" not in config:
        config["framework_params"] = {"beellama": {"global": {}, "models": {}}, "ollama": {}, "comfyui": {}}
    if "beellama" not in config["framework_params"]:
        config["framework_params"]["beellama"] = {"global": {}, "models": {}}
    if "global" not in config["framework_params"]["beellama"]:
        config["framework_params"]["beellama"]["global"] = {}
    # 更新全局参数
    if "turbo_level" in data:
        config["framework_params"]["beellama"]["global"]["turbo_level"] = data["turbo_level"]
    if "flash_attn" in data:
        config["framework_params"]["beellama"]["global"]["flash_attn"] = bool(data["flash_attn"])
    if "reasoning_off" in data:
        config["framework_params"]["beellama"]["global"]["reasoning_off"] = bool(data["reasoning_off"])
    save_config(config)
    audit_log("设置 beellama 全局参数", f"turbo={data.get('turbo_level', '')}, fa={data.get('flash_attn')}, reasoning={data.get('reasoning_off')}", "ok")
    return jsonify({"status": "ok", "params": config["framework_params"]["beellama"]["global"]})

@app.route("/api/beellama_model_params", methods=["GET"])
def api_get_beellama_model_params():
    """获取当前加载模型的专属参数"""
    if current_framework != "beellama" or not current_model:
        return jsonify({"error": "未加载 beellama 模型"}), 400
    config = load_config()
    model_params = config.get("framework_params", {}).get("beellama", {}).get("models", {}).get(current_model, {})
    return jsonify({
        "model": current_model,
        "ctx_size": model_params.get("ctx_size", None),
        "parallel": model_params.get("parallel", None),
        "ngpu_layers": model_params.get("ngpu_layers", None)
    })

@app.route("/api/beellama_model_params", methods=["POST"])
def api_set_beellama_model_params():
    """设置当前加载模型的专属参数"""
    if current_framework != "beellama":
        return jsonify({"error": "当前不是 beellama 框架"}), 400
    data = request.get_json(silent=True) or {}
    # 优先使用前端传入的 model 名（避免状态不同步）
    model_name = data.get("model") or current_model
    if not model_name:
        return jsonify({"error": "未指定模型名"}), 400
    config = load_config()
    if "framework_params" not in config:
        config["framework_params"] = {"beellama": {"global": {}, "models": {}}, "ollama": {}, "comfyui": {}}
    if "beellama" not in config["framework_params"]:
        config["framework_params"]["beellama"] = {"global": {}, "models": {}}
    if "models" not in config["framework_params"]["beellama"]:
        config["framework_params"]["beellama"]["models"] = {}
    if model_name not in config["framework_params"]["beellama"]["models"]:
        config["framework_params"]["beellama"]["models"][model_name] = {}
    # 更新模型专属参数
    if "ctx_size" in data:
        config["framework_params"]["beellama"]["models"][model_name]["ctx_size"] = int(data["ctx_size"]) if data["ctx_size"] else None
    if "parallel" in data:
        config["framework_params"]["beellama"]["models"][model_name]["parallel"] = int(data["parallel"]) if data["parallel"] else None
    if "ngpu_layers" in data:
        config["framework_params"]["beellama"]["models"][model_name]["ngpu_layers"] = int(data["ngpu_layers"]) if data["ngpu_layers"] else None
    save_config(config)
    audit_log("设置 beellama 模型参数", f"model={model_name}, ctx={data.get('ctx_size')}, parallel={data.get('parallel')}, ngl={data.get('ngpu_layers')}", "ok")
    return jsonify({"status": "ok", "model": model_name, "params": config["framework_params"]["beellama"]["models"][model_name]})


# ── ComfyUI 全局参数 API (v1.1.8 新增) ─────────────────────────
# 读 framework-manager.json 的 framework_params.comfyui.global
# 写 service file + daemon-reload + restart

@app.route("/api/comfyui_params", methods=["GET"])
def api_get_comfyui_params():
    """获取 ComfyUI 启动参数
    优先从 framework-manager.json 读, 缺失字段从当前 service file 提取
    """
    config = load_config()
    saved = config.get("framework_params", {}).get("comfyui", {}).get("global", {})
    # 服务运行时不可靠读 (字段可能跟 config 不一致), 以 config 为准 + service 作 fallback
    flags = _read_comfyui_service_execstart()
    runtime = _flags_to_comfyui_params(flags)
    # 合并: config 优先, 缺失字段用 runtime 填
    merged = _COMFYUI_DEFAULT_PARAMS.copy()
    merged.update(runtime)
    merged.update(saved)
    return jsonify(merged)


@app.route("/api/comfyui_params", methods=["POST"])
def api_set_comfyui_params():
    """保存 ComfyUI 启动参数 → 写 service file → daemon-reload → restart
    字段: lowvram / gpu_only / listen / preview_method / extra_flags
    """
    if current_framework != "comfyui":
        return jsonify({"error": "当前不是 ComfyUI 框架 (参数可存但不能改 service)"}), 400
    data = request.get_json(silent=True) or {}
    # 验证
    valid_keys = {"lowvram", "gpu_only", "listen", "preview_method", "extra_flags"}
    unknown = set(data.keys()) - valid_keys
    if unknown:
        return jsonify({"error": f"未知字段: {unknown}"}), 400
    pm = data.get("preview_method", "auto")
    if pm not in ("auto", "latent2rgb", "taesd", "none"):
        return jsonify({"error": f"preview_method 必须是 auto/latent2rgb/taesd/none"}), 400

    # 1) 写 config
    config = load_config()
    if "framework_params" not in config:
        config["framework_params"] = {"beellama": {"global": {}, "models": {}}, "ollama": {}, "comfyui": {}}
    if "comfyui" not in config["framework_params"]:
        config["framework_params"]["comfyui"] = {"global": {}}
    if "global" not in config["framework_params"]["comfyui"]:
        config["framework_params"]["comfyui"]["global"] = {}
    cfg_global = config["framework_params"]["comfyui"]["global"]
    for k in valid_keys:
        if k in data:
            cfg_global[k] = data[k]
    save_config(config)

    # 2) 写 service file
    flags = _comfyui_params_to_flags(cfg_global)
    if not _write_comfyui_service_execstart(flags):
        return jsonify({"error": "写 comfyui.service 失败"}), 500

    # 3) daemon-reload + restart
    run_cmd("systemctl --user daemon-reload", timeout=5)
    if not stop_service(COMFYUI_SERVICE):
        return jsonify({"error": "停止 comfyui 失败"}), 500
    if not start_service(COMFYUI_SERVICE):
        return jsonify({"error": "启动 comfyui 失败"}), 500
    audit_log("保存 ComfyUI 启动参数", f"flags={flags}", "ok")
    return jsonify({"status": "ok", "params": cfg_global, "flags": flags, "message": "已保存并重启 ComfyUI"})


@app.route("/api/comfyui_extra_paths", methods=["GET"])
def api_get_comfyui_extra_paths():
    """读 extra_model_paths.yaml
    不存在: 返回默认建议 (不创建文件)
    """
    yaml_cfg = _read_comfyui_yaml()
    if yaml_cfg is None:
        return jsonify({
            "exists": False,
            "base_path": COMFYUI_DIR,
            "custom_paths": {},
            "default_base": COMFYUI_DIR,
        })
    return jsonify({
        "exists": True,
        "base_path": yaml_cfg["base_path"],
        "custom_paths": yaml_cfg["custom_paths"],
        "default_base": COMFYUI_DIR,
    })


@app.route("/api/comfyui_extra_paths", methods=["PUT"])
def api_set_comfyui_extra_paths():
    """保存 extra_model_paths.yaml → 写文件 → restart ComfyUI → 重扫模型
    body: {base_path: str, custom_paths: {cat: path, ...}}
    """
    if current_framework != "comfyui":
        return jsonify({"error": "当前不是 ComfyUI 框架"}), 400
    data = request.get_json(silent=True) or {}
    base_path = (data.get("base_path") or "").strip()
    custom_paths = data.get("custom_paths") or {}
    if not base_path:
        return jsonify({"error": "base_path 不能为空"}), 400
    if not base_path.startswith("/"):
        return jsonify({"error": "base_path 必须是绝对路径"}), 400
    if not isinstance(custom_paths, dict):
        return jsonify({"error": "custom_paths 必须是 dict"}), 400
    # 写 yaml
    if not _write_comfyui_yaml(base_path, custom_paths):
        return jsonify({"error": "写 extra_model_paths.yaml 失败"}), 500
    # restart
    if not stop_service(COMFYUI_SERVICE):
        return jsonify({"error": "停止 comfyui 失败"}), 500
    if not start_service(COMFYUI_SERVICE):
        return jsonify({"error": "启动 comfyui 失败"}), 500
    # 清模型缓存强制重扫
    global _model_cache, _cache_timestamps
    _model_cache.pop("comfyui", None)
    _cache_timestamps.pop("comfyui", None)
    new_models = get_comfyui_models()
    audit_log("保存 ComfyUI 模型路径", f"base={base_path}, custom={list(custom_paths.keys())}, models={len(new_models)}", "ok")
    return jsonify({
        "status": "ok",
        "base_path": base_path,
        "custom_paths": custom_paths,
        "models": new_models,
        "message": f"已保存并重启 ComfyUI, 扫描到 {len(new_models)} 个模型"
    })


# ── Ollama 全局参数 API (v1.1.8-patch2 新增) ─────────────────────────
# 写 override.conf + daemon-reload + restart
# 字段: keep_alive / num_parallel / batch_size / gpu_layers / flash_attention

@app.route("/api/ollama_global_params", methods=["GET"])
def api_get_ollama_global_params():
    """获取 Ollama 全局参数
    优先从 framework-manager.json 读, 缺失字段从 override.conf 读
    v1.1.16: 始终返回全部 5 字段 (其他 4 字段会从 _OLLAMA_DEFAULT_GLOBAL 补齐, 因为 cfg_global 现在只存 gpu_layers)
    """
    config = load_config()
    saved = config.get("framework_params", {}).get("ollama", {}).get("global", {})
    runtime = _read_ollama_override_conf()
    merged = _OLLAMA_DEFAULT_GLOBAL.copy()
    merged.update(runtime)
    merged.update(saved)
    return jsonify(merged)


@app.route("/api/ollama_global_params", methods=["POST"])
def api_set_ollama_global_params():
    """保存 Ollama 全局参数 → 写 override.conf → daemon-reload → restart
    v1.1.16: UI 只提交 GPU_LAYERS, 其他 4 字段 (keep_alive/num_parallel/batch_size/flash_attention)
    使用 _OLLAMA_DEFAULT_GLOBAL 硬编码最优值补齐, 不接受前端覆盖
    body: {gpu_layers: 35} (可省略; null=不设)
    """
    if current_framework != "ollama":
        return jsonify({"error": "当前不是 Ollama 框架 (参数可存但不能 restart)"}), 400
    data = request.get_json(silent=True) or {}
    valid_keys = set(_OLLAMA_GLOBAL_FIELD_MAP.keys())
    unknown = set(data.keys()) - valid_keys
    if unknown:
        return jsonify({"error": f"未知字段: {unknown}"}), 400
    # 验证 int 字段
    for f in ("num_parallel", "batch_size", "gpu_layers", "flash_attention"):
        if f in data and data[f] is not None and data[f] != "":
            try:
                data[f] = int(data[f])
            except (TypeError, ValueError):
                return jsonify({"error": f"{f} 必须是整数"}), 400
    # 1) 写 config
    config = load_config()
    if "framework_params" not in config:
        config["framework_params"] = {"beellama": {"global": {}, "models": {}}, "ollama": {}, "comfyui": {}}
    if "ollama" not in config["framework_params"]:
        config["framework_params"]["ollama"] = {"global": {}, "models": {}}
    if "global" not in config["framework_params"]["ollama"]:
        config["framework_params"]["ollama"]["global"] = {}
    cfg_global = config["framework_params"]["ollama"]["global"]
    for k in valid_keys:
        if k in data:
            cfg_global[k] = data[k] if data[k] != "" else None
    save_config(config)
    # 2) 写 override.conf (v1.1.16: cfg_global 可能不含其他 4 字段, 用 _OLLAMA_DEFAULT_GLOBAL 补齐)
    #    override.conf 必须保持全部 5 字段, 否则服务启动时 env 缺失
    runtime = _read_ollama_override_conf()
    merged = runtime.copy()
    for k in valid_keys:
        if k in cfg_global and cfg_global[k] is not None:
            merged[k] = cfg_global[k]
        elif k not in merged:
            # cfg_global 没有, runtime 也没有, 用硬编码最优值
            merged[k] = _OLLAMA_DEFAULT_GLOBAL.get(k)
    if not _write_ollama_override_conf(merged):
        return jsonify({"error": "写 override.conf 失败"}), 500
    # 3) daemon-reload + restart
    run_cmd("systemctl --user daemon-reload", timeout=5)
    if not stop_service(OLLAMA_SERVICE):
        return jsonify({"error": "停止 ollama 失败"}), 500
    if not start_service(OLLAMA_SERVICE):
        return jsonify({"error": "启动 ollama 失败"}), 500
    # 4) 等侍 API 就绪 (复用 patch6 逻辑)
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1).close()
            break
        except Exception:
            time.sleep(1)
    audit_log("保存 Ollama 全局参数", f"params={cfg_global}", "ok")
    return jsonify({"status": "ok", "params": cfg_global, "message": "已保存并重启 Ollama"})


# ── Ollama per-model Modelfile API (v1.1.8-patch2 新增) ─────────────────
# 读: 从 Modelfile 读参数
# 写: 写 Modelfile → ollama create 重建 tag (如 qwen3.6-q3:ctx128k)
# 注意: num_ctx 改变会生成新 tag (e.g. ctx64k→ctx128k), 旧 tag 保留不删

@app.route("/api/ollama_model_params", methods=["GET"])
def api_get_ollama_model_params():
    """获取指定 ollama 模型的 Modelfile 参数
    query: ?model=xxx (默认 current_model)
    """
    model = request.args.get("model") or current_model
    if not model:
        return jsonify({"error": "未指定 model"}), 400
    mf_path = _modelfile_path_for(model)
    parsed = _parse_modelfile(mf_path)
    if parsed is None:
        return jsonify({
            "model": model,
            "modelfile_path": mf_path,
            "exists": False,
            "params": {f: None for f in _OLLAMA_MODEL_PARAM_FIELDS},
            "from": None,
        })
    return jsonify({
        "model": model,
        "modelfile_path": mf_path,
        "exists": True,
        "params": {f: parsed.get(f) for f in _OLLAMA_MODEL_PARAM_FIELDS},
        "from": parsed.get("from"),
    })


@app.route("/api/ollama_model_params", methods=["POST"])
def api_set_ollama_model_params():
    global current_model, current_framework  # v1.1.13
    """保存 ollama per-model 参数 -> 写 Modelfile -> ollama create 重建 tag
    body: {model, num_ctx, temperature, top_p, top_k, repeat_penalty}
    - num_ctx 必填，改变会创建新 tag (e.g. ctx128k->ctx256k)
    - 其他字段可省略 (保留原值) 或 传 null/0 (从 Modelfile 删除)
    """
    if current_framework != "ollama":
        return jsonify({"error": "当前不是 Ollama 框架"}), 400
    data = request.get_json(silent=True) or {}
    model = data.get("model") or current_model
    if not model:
        return jsonify({"error": "未指定 model"}), 400
    num_ctx = data.get("num_ctx")
    if num_ctx is None or num_ctx == "":
        return jsonify({"error": "num_ctx 必填 (决定 tag 后缀)"}), 400
    try:
        num_ctx = int(num_ctx)
    except (TypeError, ValueError):
        return jsonify({"error": "num_ctx 必须是整数"}), 400
    if num_ctx < 512 or num_ctx > 1048576:
        return jsonify({"error": "num_ctx 范围 512-1048576"}), 400
    # 读现有参数 (用于保留未指定的字段)
    mf_path = _modelfile_path_for(model)
    existing = _parse_modelfile(mf_path) or {f: None for f in _OLLAMA_MODEL_PARAM_FIELDS}
    existing["from"] = existing.get("from") or model.split(":")[0] + ":latest"
    # 验证其他字段
    for f in ("temperature", "top_p", "top_k", "repeat_penalty"):
        if f in data and data[f] is not None and data[f] != "":
            try:
                data[f] = float(data[f])
            except (TypeError, ValueError):
                return jsonify({"error": f"{f} 必须是数字"}), 400
    # 更新参数
    new_params = dict(existing)
    new_params["num_ctx"] = num_ctx
    for f in ("temperature", "top_p", "top_k", "repeat_penalty"):
        if f in data:
            new_params[f] = data[f] if data[f] != "" and data[f] != 0 else None
    # 写 Modelfile
    base_name = model.split(":")[0]
    new_params["from"] = existing["from"]  # 保持 FROM 指向
    header = [
        f"模型 {model} 参数配置 (framework-manager v1.1.8-patch2)",
        f"FROM: {new_params['from']}",
        f"num_ctx: {new_params['num_ctx']} → tag: {_make_ollama_tag(base_name, num_ctx)}",
    ]
    if not _write_modelfile(mf_path, new_params, header_lines=header):
        return jsonify({"error": "写 Modelfile 失败"}), 500
    # ollama create 重建 tag
    new_tag = _make_ollama_tag(base_name, num_ctx)
    ok, msg = _create_ollama_tag_from_modelfile(mf_path, new_tag)
    audit_log("保存 ollama 模型参数", f"model={model}, tag={new_tag}, ok={ok}", "ok" if ok else "fail")
    if not ok:
        return jsonify({
            "status": "partial",
            "warning": f"Modelfile 已写但 ollama create 失败: {msg}",
            "modelfile": mf_path,
            "intended_tag": new_tag,
            "params": {f: new_params.get(f) for f in _OLLAMA_MODEL_PARAM_FIELDS},
        }), 500
    # v1.1.13: 自动加载新 tag (如果当前框架是 ollama 且新 tag 存在)
    auto_loaded = False
    try:
        import urllib.request
        # 检查新 tag 是否在 ollama list 中
        tags_resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5)
        tags_data = json.loads(tags_resp.read())
        available_tags = [m.get("name", "") for m in tags_data.get("models", [])]
        if new_tag in available_tags:
            # 通过 /api/generate 加载新 tag 到显存
            payload = json.dumps({
                "model": new_tag,
                "prompt": "",
                "stream": False,
                "keep_alive": -1
            }).encode()
            req = urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            urllib.request.urlopen(req, timeout=300)
            # 更新全局 current_model
            current_model = new_tag
            auto_loaded = True
            log.info(f"自动加载新 tag: {new_tag}")
    except Exception as e:
        log.warning(f"自动加载新 tag 失败: {e}")
        # 不阻断成功返回，前端会提示用户手动加载
    
    return jsonify({
        "status": "ok",
        "model": model,
        "modelfile": mf_path,
        "tag": new_tag,
        "auto_loaded": auto_loaded,
        "params": {f: new_params.get(f) for f in _OLLAMA_MODEL_PARAM_FIELDS},
        "message": f"已保存 {model} 参数并重建 tag {new_tag}" + ("，已自动加载" if auto_loaded else "，请手动加载")
    })


# ── Ollama defaults API (v1.1.8-patch2 新增) ──────────────────────────
# 复用 framework-manager-defaults.json, 加 ollama 段
# 结构: {ollama: {_fallback: {...}, models: {name: {...}}}}

@app.route("/api/ollama_defaults", methods=["GET"])
def api_get_ollama_defaults():
    defaults = _load_defaults()
    return jsonify(defaults.get("ollama", {"_fallback": {}, "models": {}}))


@app.route("/api/ollama_defaults", methods=["POST"])
def api_set_ollama_defaults():
    data = request.get_json(silent=True) or {}
    if "_fallback" not in data or "models" not in data:
        return jsonify({"error": "需包含 _fallback 和 models"}), 400
    # 轻量验证
    for k in _OLLAMA_MODEL_PARAM_FIELDS:
        v = data["_fallback"].get(k)
        if v is not None and v != "" and not isinstance(v, (int, float)):
            return jsonify({"error": f"_fallback.{k} 必须是数字或 null"}), 400
    for name, p in data["models"].items():
        for k in _OLLAMA_MODEL_PARAM_FIELDS:
            v = p.get(k)
            if v is not None and v != "" and not isinstance(v, (int, float)):
                return jsonify({"error": f"models.{name}.{k} 必须是数字或 null"}), 400
    defaults = _load_defaults()
    defaults["ollama"] = data
    if not _save_defaults(defaults):
        return jsonify({"error": "保存失败"}), 500
    audit_log("保存 ollama defaults", f"fallback={data['_fallback']}, models={list(data['models'].keys())}", "ok")
    return jsonify({"status": "ok"})


# ── v1.1.17: 新模型注册参数 (项目内独立配置, 与 ollama defaults 块独立) ─────────
@app.route("/api/manifest_gen_params", methods=["GET"])
def api_get_manifest_gen_params():
    """获取「📋 新模型注册参数」: 读项目内 config/ollama_manifest_generate_parameter.json
    文件不存在 → 报错 (调用方应保证文件已存在)
    """
    if not os.path.exists(MANIFEST_GEN_PARAMS_FILE):
        return jsonify({"error": f"配置文件不存在: {MANIFEST_GEN_PARAMS_FILE}"}), 404
    try:
        with open(MANIFEST_GEN_PARAMS_FILE, "r") as f:
            params = json.load(f)
        return jsonify({
            "params": params,
            "file_path": MANIFEST_GEN_PARAMS_FILE,
        })
    except Exception as e:
        return jsonify({"error": f"读文件失败: {e}"}), 500


@app.route("/api/manifest_gen_params", methods=["POST"])
def api_set_manifest_gen_params():
    """保存「📋 新模型注册参数」 → 写项目内 config/ollama_manifest_generate_parameter.json
    body: {num_ctx, temperature, top_p, top_k, repeat_penalty}
    """
    data = request.get_json(silent=True) or {}
    valid_keys = set(_MANIFEST_GEN_PARAM_FIELDS)
    unknown = set(data.keys()) - valid_keys
    if unknown:
        return jsonify({"error": f"未知字段: {unknown}"}), 400
    # 验证 + 转为合法 int/float
    out = {}
    int_fields = {"num_ctx", "top_k"}
    for k in valid_keys:
        v = data.get(k)
        if v is None or v == "":
            return jsonify({"error": f"{k} 不能为空"}), 400
        try:
            if k in int_fields:
                out[k] = int(v)
            else:
                out[k] = float(v)
        except (TypeError, ValueError):
            return jsonify({"error": f"{k} 必须是数字"}), 400
    # num_ctx 范围
    if not (512 <= out["num_ctx"] <= 1048576):
        return jsonify({"error": f"num_ctx 越界 (512-1048576): {out['num_ctx']}"}), 400
    # 写文件 (只存 5 个参数, 不加 _meta)
    try:
        os.makedirs(PROJECT_CONFIG_DIR, exist_ok=True)
        with open(MANIFEST_GEN_PARAMS_FILE, "w") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
    except Exception as e:
        return jsonify({"error": f"写文件失败: {e}"}), 500
    audit_log("保存 新模型注册参数", f"params={out}", "ok")
    return jsonify({"status": "ok", "params": out, "file_path": MANIFEST_GEN_PARAMS_FILE})


# ── v1.1.18: 自动注册用户下载的 GGUF ─────────
@app.route("/api/ingest_gguf", methods=["POST"])
def api_ingest_gguf():
    """v1.1.18: 「📥 自动注册下载的模型」 按钮

    扫描 /data/ollama/models/blobs/ 中任意命名的 .gguf 文件
    (用户下载/放置的), 依次:
    1. 计算 sha256 (增量, 避免 OOM)
    2. 硬链接为 'sha256-{hash}' 命名 (同 fs)
    3. 删原文件 (硬链接保留)
    4. 解析 GGUF header (general.name + context_length)
    5. 读 「📋 新模型注册参数」, num_ctx = min(新参数, gguf.context_length)
    6. 生成 params blob + config blob + manifest
    7. tag 格式: '{general.name}-ctx{N}k'
    """
    result = _ingest_gguf()
    return jsonify(result)


# ── v1.6.2: beellama 端「自动注册下载的模型」 ─────────
@app.route("/api/ingest_beellama", methods=["POST"])
def api_ingest_beellama():
    """v1.6.2: 「📥 beellama 自动注册下载的模型」 按钮

    扫描 /data/ollama/models/blobs/ 中任意命名的 .gguf 文件,
    为 beellama 框架在 ~/models/<dir>/ 下建软链接 → ollama blob.

    不动 ollama manifest / modelfile, 不删原文件 (与 ollama 端 ingest 不一样).
    """
    result = _ingest_beellama()
    # 重新触发 get_beellama_models 缓存
    global _model_cache, _cache_timestamps
    _model_cache.pop("beellama", None)
    _cache_timestamps.pop("beellama", None)
    return jsonify(result)


@app.route("/api/restore_ollama_default_model_params", methods=["POST"])
def api_restore_ollama_default_model_params():
    """「🔄 恢复默认」按钮: 从 defaults.ollama 读该模型值 → 写 Modelfile → 重建 tag
    优先级: models[name] > _fallback (回退)
    v1.1.13: 修复 fallback 空 dict 时的处理 + num_ctx 默认值
    """
    if current_framework != "ollama":
        return jsonify({"error": "当前不是 Ollama 框架"}), 400
    data = request.get_json(silent=True) or {}
    model = data.get("model") or current_model
    if not model:
        return jsonify({"error": "未指定 model"}), 400
    base_name = model.split(":")[0]
    defaults = _load_defaults().get("ollama", {})
    fb = defaults.get("_fallback", {}) or {}
    models_cfg = defaults.get("models", {}) or {}
    # 优先用 per-model, 回退到 _fallback
    model_defaults = models_cfg.get(base_name)
    if not model_defaults:
        model_defaults = {k: v for k, v in fb.items() if v is not None}
    if not model_defaults:
        return jsonify({
            "error": f"ollama defaults 中没有「{base_name}」记录且 _fallback 也为空，请先在「🎯 ollama 默认值」卡中编辑",
            "short_name": base_name,
            "missing_in_defaults": True,
        }), 404
    # v1.1.13: num_ctx 必须有默认值 (否则 api_set_ollama_model_params 会报错)
    if 'num_ctx' not in model_defaults or not model_defaults['num_ctx']:
        model_defaults['num_ctx'] = 131072
    # 复用 set_ollama_model_params (内含 Modelfile 写 + ollama create)
    payload = dict(model_defaults)
    payload["model"] = model
    # 调内部函数 (避免走 api endpoint)
    from flask import Request
    with app.test_request_context(json=payload):
        # 直接调用 view function + 拿到 response
        resp = api_set_ollama_model_params()
        if hasattr(resp, 'get_json'):
            data_resp = resp.get_json()
            data_resp["restored_from_defaults"] = True
            data_resp["short_name"] = base_name
            return jsonify(data_resp), resp.status_code
        return resp

@app.route("/api/set_pending_model", methods=["POST"])
def api_set_pending_model():
    """设置 beellama 重启后自动加载的模型"""
    global _pending_model
    data = request.get_json(silent=True) or {}
    _pending_model = data.get("model") or None
    return jsonify({"status": "ok", "pending_model": _pending_model})

@app.route("/api/save_and_apply_model_params", methods=["POST"])
def api_save_and_apply_model_params():
    """保存模型参数 → 停止 beellama → 启动 beellama (用新参数) → 自动加载原模型
    同步执行，避免 Timer 引发的 500 错误
    """
    global current_model, current_framework
    if current_framework != "beellama":
        return jsonify({"error": "当前不是 beellama 框架"}), 400

    data = request.get_json(silent=True) or {}
    model_name = data.get("model") or current_model
    if not model_name:
        return jsonify({"error": "未指定模型"}), 400

    # 1) 保存参数
    config = load_config()
    if "framework_params" not in config:
        config["framework_params"] = {"beellama": {"global": {}, "models": {}}, "ollama": {}, "comfyui": {}}
    if "beellama" not in config["framework_params"]:
        config["framework_params"]["beellama"] = {"global": {}, "models": {}}
    if "models" not in config["framework_params"]["beellama"]:
        config["framework_params"]["beellama"]["models"] = {}
    if model_name not in config["framework_params"]["beellama"]["models"]:
        config["framework_params"]["beellama"]["models"][model_name] = {}
    if "ctx_size" in data:
        config["framework_params"]["beellama"]["models"][model_name]["ctx_size"] = int(data["ctx_size"]) if data["ctx_size"] else None
    if "parallel" in data:
        config["framework_params"]["beellama"]["models"][model_name]["parallel"] = int(data["parallel"]) if data["parallel"] else None
    if "ngpu_layers" in data:
        config["framework_params"]["beellama"]["models"][model_name]["ngpu_layers"] = int(data["ngpu_layers"]) if data["ngpu_layers"] else None
    save_config(config)
    audit_log("保存并应用参数", f"model={model_name}, ctx={data.get('ctx_size')}, parallel={data.get('parallel')}, ngl={data.get('ngpu_layers')}", "ok")

    # 2-5) 重启 + 重载
    return _apply_model_params(model_name)


def _apply_model_params(model_name):
    """内部函数: 停止 beellama → 启动 beellama → 重载模型。
    供 /api/save_and_apply_model_params 和 /api/restore_default_model_params 复用。
    假设 per-model 参数已经写入了 config。
    """
    global current_model

    # 2) 停止 beellama
    stop_service(BEELLAMA_SERVICE)
    run_cmd("kill -9 $(pgrep llama-server 2>/dev/null) 2>/dev/null; true", timeout=3)
    run_cmd("pkill -9 -f 'beellama-wrapper' 2>/dev/null; true", timeout=3)
    time.sleep(2)

    # 3) 写入 NONE flag (让 wrapper 启动但不自动加载模型)
    _write_beella_none_flag()

    # 4) 启动 beellama
    success = start_service(BEELLAMA_SERVICE)
    if not success:
        return jsonify({"error": "beellama 启动失败"}), 500

    # 5) 同步加载模型
    config = load_config()
    saved_params = config.get("framework_params", {}).get("beellama", {}).get("models", {}).get(model_name, {})
    ok, msg = load_model_for_framework(model_name)
    if ok:
        current_model = model_name
        audit_log("自动重载", f"model={model_name}", "ok")
        return jsonify({
            "status": "ok",
            "model": model_name,
            "params": saved_params,
            "message": f"已应用新参数并加载 {model_name}"
        })
    else:
        return jsonify({
            "status": "partial",
            "error": f"beellama 已启动但模型加载失败: {msg}",
            "params": saved_params
        }), 500


# ── 默认值系统 (v1.1.4 新增) ────────────────────────────────
# 独立 defaults.json, 只被「🎯 默认值」卡片读写
# 与 framework-manager.json 解耦, 启动时不被加载, 仅供「恢复默认」按钮读取

@app.route("/api/defaults", methods=["GET"])
def api_get_defaults():
    """读取默认值文件, 不存在则首次初始化"""
    defaults = _load_defaults()
    return jsonify(defaults)


@app.route("/api/defaults", methods=["POST"])
def api_set_defaults():
    """保存默认值文件 (被「🎯 默认值」卡片调用)
    v1.6.2-patch2: 支持部分更新
    - 只传 _fallback: 仅更新 _fallback, models 保留
    - 只传 models: 合并 models (传过的 key 被覆盖, 未传保留)
    - 两都传: 同 v1.6.2-patch1 行为
    """
    data = request.get_json(silent=True) or {}
    if "_fallback" not in data and "models" not in data:
        return jsonify({"error": "无效结构: 需包含 _fallback 或 models 至少之一"}), 400
    existing = _load_defaults()
    # _fallback: 验证 + 写 (只传 _fallback 不动 models)
    if "_fallback" in data:
        fb = data["_fallback"] or {}
        for k in ("ctx_size", "parallel", "ngpu_layers"):
            v = fb.get(k)
            if v is not None and not isinstance(v, int):
                return jsonify({"error": f"_fallback.{k} 必须是整数或 null"}), 400
        existing["_fallback"] = {
            "ctx_size": fb.get("ctx_size"),
            "parallel": fb.get("parallel"),
            "ngpu_layers": fb.get("ngpu_layers"),
        }
    # models: 验证 + 合并 (只传 models 不动 _fallback)
    if "models" in data:
        ms = data["models"] or {}
        if "models" not in existing or not isinstance(existing.get("models"), dict):
            existing["models"] = {}
        for name, p in ms.items():
            if not isinstance(p, dict):
                return jsonify({"error": f"models.{name} 必须是字典"}), 400
            for k in ("ctx_size", "parallel", "ngpu_layers"):
                v = p.get(k)
                if v is not None and not isinstance(v, int):
                    return jsonify({"error": f"models.{name}.{k} 必须是整数或 null"}), 400
            existing["models"][name] = {
                "ctx_size": p.get("ctx_size"),
                "parallel": p.get("parallel"),
                "ngpu_layers": p.get("ngpu_layers"),
            }
    if not _save_defaults(existing):
        return jsonify({"error": "保存失败"}), 500
    audit_log("保存默认值文件",
              f"fallback={existing.get('_fallback')}, models={list(existing.get('models',{}).keys())}",
              "ok")
    return jsonify({"status": "ok"})


@app.route("/api/restore_default_model_params", methods=["POST"])
def api_restore_default_model_params():
    """「🔄 恢复默认」按钮: 从 defaults 读该模型值→写入 per-model→重启 beellama
    如果 defaults 中没有该模型, 返回 404, 前端提示用户去「🎯 默认值」卡添加
    """
    global current_model, current_framework
    if current_framework != "beellama":
        return jsonify({"error": "当前不是 beellama 框架"}), 400

    data = request.get_json(silent=True) or {}
    model_name = data.get("model") or current_model
    if not model_name:
        return jsonify({"error": "未指定模型"}), 400

    short_name = _extract_short_model_name(model_name)
    defaults = _load_defaults()
    model_defaults = defaults.get("models", {}).get(short_name)
    if not model_defaults:
        return jsonify({
            "error": f"默认值文件中没有「{short_name}」记录, 请先在「🎯 默认值」卡中编辑",
            "short_name": short_name,
            "missing_in_defaults": True
        }), 404

    # 写入 per-model (使用 short_name 作为 key, 与 wrapper 读取一致)
    config = load_config()
    if "framework_params" not in config:
        config["framework_params"] = {"beellama": {"global": {}, "models": {}}, "ollama": {}, "comfyui": {}}
    if "beellama" not in config["framework_params"]:
        config["framework_params"]["beellama"] = {"global": {}, "models": {}}
    if "models" not in config["framework_params"]["beellama"]:
        config["framework_params"]["beellama"]["models"] = {}
    # 恢复默认时统一以 short_name 为 key, 保证与 wrapper 读取对齐
    config["framework_params"]["beellama"]["models"][short_name] = {
        "ctx_size": model_defaults.get("ctx_size"),
        "parallel": model_defaults.get("parallel"),
        "ngpu_layers": model_defaults.get("ngpu_layers"),
    }
    save_config(config)
    audit_log("恢复默认值",
              f"model={short_name}, ctx={model_defaults.get('ctx_size')}, parallel={model_defaults.get('parallel')}, ngl={model_defaults.get('ngpu_layers')}",
              "ok")

    # 重启 + 重载
    return _apply_model_params(model_name)


# ── 隐藏模型管理 (v1.1.7) ───────────────────────────────
# 从下拉框隐藏但不删除文件, 写入 ~/.openclaw/config/framework-manager-hidden.json

@app.route("/api/hidden_models", methods=["GET"])
def api_get_hidden_models():
    return jsonify(_load_hidden())


@app.route("/api/hide_model", methods=["POST"])
def api_hide_model():
    data = request.get_json(silent=True) or {}
    framework = data.get("framework")
    model = data.get("model")
    if framework not in ("beellama", "ollama", "comfyui"):
        return jsonify({"error": "framework 必须是 beellama/ollama/comfyui"}), 400
    if not model:
        return jsonify({"error": "未指定 model"}), 400
    hidden = _load_hidden()
    if model not in hidden[framework]:
        hidden[framework].append(model)
        _save_hidden(hidden)
    return jsonify({"status": "ok", "hidden": hidden})


@app.route("/api/unhide_model", methods=["POST"])
def api_unhide_model():
    data = request.get_json(silent=True) or {}
    framework = data.get("framework")
    model = data.get("model")
    if framework not in ("beellama", "ollama", "comfyui"):
        return jsonify({"error": "framework 必须是 beellama/ollama/comfyui"}), 400
    if not model:
        return jsonify({"error": "未指定 model"}), 400
    hidden = _load_hidden()
    if model in hidden[framework]:
        hidden[framework].remove(model)
        _save_hidden(hidden)
    return jsonify({"status": "ok", "hidden": hidden})


def _scan_framework_models(framework):
    """扫描指定框架的所有本地模型 (不过滤 hidden), 用于「➕ 添加模型进列表」"""
    if framework == "beellama":
        return get_beellama_models()
    elif framework == "ollama":
        return get_ollama_models()
    elif framework == "comfyui":
        return get_comfyui_models()
    return []


@app.route("/api/scan_for_addition", methods=["GET"])
def api_scan_for_addition():
    """v1.1.7-patch3: 「➕ 添加模型进列表」模态框扫描
    返回指定框架的所有本地模型 + 当前 visible 列表, 前端据此渲染复选框
    """
    framework = request.args.get("framework")
    if framework not in ("beellama", "ollama", "comfyui"):
        return jsonify({"error": "framework 必须是 beellama/ollama/comfyui"}), 400
    # 清缓存强制重扫 (避免 30s 缓存遗漏新文件)
    global _model_cache, _cache_timestamps
    _model_cache.pop(framework, None)
    _cache_timestamps.pop(framework, None)
    all_models = _scan_framework_models(framework)
    hidden = _load_hidden().get(framework, [])
    visible = [m for m in all_models if m not in hidden]
    audit_log("扫描可用模型", f"framework={framework}, total={len(all_models)}, visible={len(visible)}, hidden={len(hidden)}", "ok")
    return jsonify({
        "framework": framework,
        "all": all_models,
        "visible": visible,
        "hidden": hidden
    })


# ── v1.1.18: 解析 GGUF header (用于 ingest_gguf 提取 general.name 和 context_length) ─────
def _parse_gguf_header(gguf_path, max_bytes=10*1024*1024):
    """解析 GGUF v3 header, 提取 general.name 和 context_length

    GGUF v3 格式:
    - magic (4B) = "GGUF"
    - version (4B) = 3
    - tensor_count (8B)
    - kv_count (8B)
    - KV pairs: key_len(8B) + key (UTF-8) + value_type(4B) + value_data

    需要的字段:
    - general.name (GGUF_STRING=8): model name
    - <arch>.context_length (GGUF_UINT32=4): native context length
      (qwen2arch=llama → llama.context_length, qwen2 → qwen2.context_length 等)

    只读前 max_bytes 字节 (默认 10MB), 避开多 GB GGUF 文件.
    返回: {name: str|None, context_length: int|None} 或 失败时 {}
    """
    try:
        with open(gguf_path, "rb") as f:
            head = f.read(max_bytes)
        if len(head) < 24:
            return {}
        # magic (4) + version (4) + tensor_count (8) + kv_count (8) = 24
        import struct
        magic = head[0:4]
        if magic != b"GGUF":
            return {}
        # version = struct.unpack("<I", head[4:8])[0]  # v1.1.18 不严格检查, 3 是主流
        # tensor_count = struct.unpack("<Q", head[8:16])[0]
        kv_count = struct.unpack("<Q", head[16:24])[0]
        if kv_count > 10000:  # 防异常文件
            return {}

        # GGUF value types
        GGUF_STRING = 8
        GGUF_UINT32 = 4
        GGUF_INT32 = 5
        GGUF_UINT64 = 10
        GGUF_INT64 = 11
        GGUF_FLOAT32 = 6
        GGUF_ARRAY = 9

        result = {"name": None, "context_length": None}
        offset = 24
        for _ in range(int(kv_count)):
            if offset + 8 > len(head):
                break
            key_len = struct.unpack("<Q", head[offset:offset+8])[0]
            offset += 8
            if offset + key_len > len(head):
                break
            key = head[offset:offset+key_len].decode("utf-8", errors="ignore")
            offset += key_len
            if offset + 4 > len(head):
                break
            value_type = struct.unpack("<I", head[offset:offset+4])[0]
            offset += 4

            # 提取 name (general.name) 和 context_length
            if key == "general.name" and value_type == GGUF_STRING:
                if offset + 8 > len(head):
                    break
                str_len = struct.unpack("<Q", head[offset:offset+8])[0]
                offset += 8
                if offset + str_len > len(head):
                    break
                result["name"] = head[offset:offset+str_len].decode("utf-8", errors="ignore")
                offset += str_len
            elif key.endswith(".context_length") and value_type in (GGUF_UINT32, GGUF_INT32):
                if offset + 4 > len(head):
                    break
                result["context_length"] = struct.unpack("<I", head[offset:offset+4])[0]
                offset += 4
            elif key.endswith(".context_length") and value_type in (GGUF_UINT64, GGUF_INT64):
                if offset + 8 > len(head):
                    break
                result["context_length"] = struct.unpack("<Q", head[offset:offset+8])[0]
                offset += 8
            elif value_type == GGUF_STRING:
                if offset + 8 > len(head):
                    break
                str_len = struct.unpack("<Q", head[offset:offset+8])[0]
                offset += 8 + str_len
            elif value_type in (GGUF_UINT32, GGUF_INT32, GGUF_FLOAT32):
                offset += 4
            elif value_type in (GGUF_UINT64, GGUF_INT64):
                offset += 8
            elif value_type == GGUF_ARRAY:
                if offset + 12 > len(head):
                    break
                arr_type = struct.unpack("<I", head[offset:offset+4])[0]
                arr_len = struct.unpack("<Q", head[offset+4:offset+12])[0]
                offset += 12
                if arr_type == GGUF_STRING:
                    for _ in range(min(int(arr_len), 100)):  # 限 100 防跳出
                        if offset + 8 > len(head):
                            break
                        sl = struct.unpack("<Q", head[offset:offset+8])[0]
                        offset += 8 + sl
                elif arr_type in (GGUF_UINT32, GGUF_INT32, GGUF_FLOAT32):
                    offset += 4 * arr_len
                elif arr_type in (GGUF_UINT64, GGUF_INT64):
                    offset += 8 * arr_len
                else:
                    break  # 不支持的 array type, 跳出
            else:
                break  # 未知 type, 跳出
        return result
    except Exception as e:
        audit_log("GGUF 解析失败", f"path={gguf_path}, error={e}", "error")
        return {}


def _ingest_gguf():
    """v1.1.18: 扫描 /data/ollama/models/blobs/ 中任意命名的 .gguf 文件 (用户下载的)

    流程:
    1. 扫描 blobs/ 中不以 'sha256-' 开头的 .gguf 文件
    2. 计算 sha256 (增量, 避免 OOM)
    3. 硬链接为 'sha256-{hash}' 命名 (同 fs, 不复制)
    4. 删原文件 (硬链接保留, 原文件释放)
    5. 解析 GGUF header 得 general.name 和 context_length
    6. 读 「📋 新模型注册参数」 文件, num_ctx = min(新参数, gguf.context_length)
    7. 写 params blob + config blob + manifest, tag 格式 '{name}-ctx{N}k'

    返回: {scanned: int, registered: [...], skipped: [...], errors: [...]}
    """
    import json as _json
    blobs_dir = Path(OLLAMA_MODELS_DIR) / "blobs"
    manifests_dir = Path(OLLAMA_MODELS_DIR) / "manifests" / "registry.ollama.ai" / "library"
    if not blobs_dir.exists():
        return {"scanned": 0, "registered": [], "skipped": [], "errors": [f"blobs 目录不存在: {blobs_dir}"]}

    # 读 「📋 新模型注册参数」 文件
    manifest_params = _MANIFEST_GEN_PARAMS_DEFAULTS_FOR_INGEST  # 兑底 (若文件不存在)
    if os.path.exists(MANIFEST_GEN_PARAMS_FILE):
        try:
            with open(MANIFEST_GEN_PARAMS_FILE, "r") as f:
                loaded = _json.load(f)
            for k in _MANIFEST_GEN_PARAM_FIELDS:
                if k in loaded:
                    manifest_params[k] = loaded[k]
        except Exception as e:
            return {"scanned": 0, "registered": [], "skipped": [], "errors": [f"读新模型注册参数文件失败: {e}"]}

    user_num_ctx = int(manifest_params["num_ctx"])

    # 1. 扫描用户下载的 .gguf (任意命名, 不是 sha256-)
    user_files = []
    for f in blobs_dir.iterdir():
        if not f.is_file():
            continue
        if f.name.startswith("sha256-"):
            continue  # 跳过已 sha 命名的
        if not f.name.lower().endswith((".gguf", ".bin")):  # .bin 也是 GGUF 常见后缀
            continue
        user_files.append(f)
    if not user_files:
        return {"scanned": 0, "registered": [], "skipped": [], "errors": [], "params": manifest_params}

    # 2. 为每个用户文件计算 sha + 硬链接 + 解析 + 生成 manifest
    registered = []
    skipped = []
    errors = []
    for src in user_files:
        src_path = str(src)
        src_name = src.name
        try:
            # 2a. 计算 sha256 (增量)
            sha_hasher = hashlib.sha256()
            with open(src, "rb") as f:
                while True:
                    chunk = f.read(8 * 1024 * 1024)  # 8MB chunks
                    if not chunk:
                        break
                    sha_hasher.update(chunk)
            sha = sha_hasher.hexdigest()
            sha_blob = blobs_dir / f"sha256-{sha}"

            # 2b. 硬链接 (如果 sha 命名已存在则跳过)
            if not sha_blob.exists():
                try:
                    os.link(src_path, str(sha_blob))
                except OSError as e:
                    # 跨 fs 或其他原因, 退到 copy2
                    import shutil
                    shutil.copy2(src_path, str(sha_blob))
            size = sha_blob.stat().st_size

            # 2c. 删原文件 (硬链接保留, 源释放)
            try:
                os.unlink(src_path)
            except OSError:
                pass  # 即使删失败, manifest 仍可创建

            # 2d. 解析 GGUF header
            info = _parse_gguf_header(str(sha_blob))
            gguf_name = info.get("name") or f"gguf-{sha[:8]}"
            gguf_ctx = info.get("context_length")
            # num_ctx = min(user设置, gguf 原生 ctx)
            if gguf_ctx and 512 <= gguf_ctx <= 1048576:
                num_ctx = min(user_num_ctx, gguf_ctx)
            else:
                num_ctx = user_num_ctx
            ctx_k = f"ctx{num_ctx // 1024}k" if num_ctx % 1024 == 0 else f"ctx{num_ctx}"

            # 2e. 写 params blob (只写 num_ctx)
            params_data = _json.dumps({"num_ctx": num_ctx}).encode()
            params_sha = hashlib.sha256(params_data).hexdigest()
            params_blob = blobs_dir / f"sha256-{params_sha}"
            if not params_blob.exists():
                params_blob.write_bytes(params_data)

            # 2f. 写 config blob
            config_data = _json.dumps({
                "model_sha": sha,
                "model_size": size,
                "num_ctx": num_ctx,
                "gguf_name": gguf_name,
                "gguf_context_length": gguf_ctx,
            }).encode()
            config_sha = hashlib.sha256(config_data).hexdigest()
            config_blob = blobs_dir / f"sha256-{config_sha}"
            if not config_blob.exists():
                config_blob.write_bytes(config_data)

            # 2g. 检查 manifest 是否已存在 (幂等)
            model_dir = manifests_dir / gguf_name
            tag_file = model_dir / ctx_k
            if tag_file.exists():
                skipped.append(f"{gguf_name}:{ctx_k} (已存在)")
                continue

            # 2h. 写 manifest
            model_dir.mkdir(parents=True, exist_ok=True)
            manifest = {
                "schemaVersion": 2,
                "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
                "config": {
                    "mediaType": "application/vnd.docker.container.image.v1+json",
                    "digest": f"sha256:{config_sha}",
                    "size": len(config_data),
                },
                "layers": [
                    {
                        "mediaType": "application/vnd.ollama.image.model",
                        "digest": f"sha256:{sha}",
                        "size": size,
                    },
                    {
                        "mediaType": "application/vnd.ollama.image.params",
                        "digest": f"sha256:{params_sha}",
                        "size": len(params_data),
                    },
                ],
            }
            tag_file.write_text(_json.dumps(manifest, indent=2))
            registered.append(f"{gguf_name}:{ctx_k}")
            audit_log("ingest GGUF", f"name={gguf_name}:{ctx_k}, size={size}, sha={sha[:12]}, gguf_ctx={gguf_ctx}", "ok")
        except Exception as e:
            errors.append(f"{src_name}: {e}")
            audit_log("ingest GGUF 失败", f"file={src_name}, error={e}", "error")

    return {
        "scanned": len(user_files),
        "registered": registered,
        "skipped": skipped,
        "errors": errors,
        "params_used": manifest_params,
    }


def _init_per_model_for_ingest(short_name):
    """v1.6.2-patch1: beellama ingest 时调, 为新 short_name 写 per-model + defaults

    逻辑:
    - 读 _load_defaults 拿 _fallback
    - defaults.models[short_name] 不存在则创建 (用 _fallback 复制)
    - per-model (framework-manager.json 的 framework_params.beellama.models) 不存在则创建
    - 已存在则跳过, 不覆盖用户手动调过的值

    返回: {"created": bool, "ctx_size": N, "parallel": N, "ngpu_layers": N} 或 {"error": str}
    """
    try:
        defaults = _load_defaults()
        _fallback = defaults.get("_fallback", {})
        if not all(k in _fallback for k in ("ctx_size", "parallel", "ngpu_layers")):
            return {"error": f"defaults _fallback 缺字段: {list(_fallback)}"}

        # 1) defaults.models[short_name] 补齐 (已存在不覆盖)
        models_def = defaults.setdefault("models", {})
        created_in_defaults = False
        if short_name not in models_def:
            models_def[short_name] = _fallback.copy()
            created_in_defaults = True

        # 2) per-model 补齐 (已存在不覆盖)
        config = load_config()
        models_cfg = (
            config
            .setdefault("framework_params", {})
            .setdefault("beellama", {})
            .setdefault("models", {})
        )
        created_in_per_model = False
        if short_name not in models_cfg:
            models_cfg[short_name] = {
                "ctx_size": models_def[short_name].get("ctx_size"),
                "parallel": models_def[short_name].get("parallel"),
                "ngpu_layers": models_def[short_name].get("ngpu_layers"),
            }
            created_in_per_model = True

        # 3. 只在新建时落盘 (避免 ingest 幂等调用反复写文件)
        if created_in_defaults:
            if not _save_defaults(defaults):
                return {"error": "写 defaults.json 失败"}
        if created_in_per_model:
            save_config(config)

        return {
            "created": created_in_defaults or created_in_per_model,
            "ctx_size": models_def[short_name].get("ctx_size"),
            "parallel": models_def[short_name].get("parallel"),
            "ngpu_layers": models_def[short_name].get("ngpu_layers"),
        }
    except Exception as e:
        return {"error": str(e)}


def _ingest_beellama():
    """v1.6.2: 扫描 /data/ollama/models/blobs/ 中任意命名的 .gguf 文件 (用户下载的),
    为 beellama 框架在 ~/models/<dir>/ 下建立软链接 → ollama blob.

    设计:
    - beellama 不需要 ollama 那种 manifest, 加载走 "绝对路径" 机制
    - 用户在 ollama blobs 放任意命名 .gguf, 期望能被 beellama 看到 → 只要在 ~/models/ 下建软链接即可
    - 跨文件系统 (/home vs /data) 不能硬链接, 用软链接 (同 ollama 端"硬链接 + 删原文件" 不一样)
    - 不动 ollama manifest / modelfile (用户明确 "ollama 不要动")
    - 不删 ollama 端原文件 (保留原命名, 万一用户还想 ollama 用)

    流程:
    1. 扫描 ollama blobs/ 中非 sha256- 开头的 .gguf (任意命名)
    2. 计算 sha256 (增量, 避免 OOM)
    3. 在 blobs/ 软链接为 sha256-{hash} 命名 (避免与其他 sha 冲突; 也供 ollama 端使用)
    4. 解析 GGUF header (general.name + context_length) → 决定 short_name
    5. dir 名: 启发式 = "<模型族>-<size>b" (e.g. qwen3.6-35b, gemma-4-26b)
       复 用 alias_map 反向 + GGUF basename 推断, 与 _extract_short_model_name 保持一致
    6. ~/models/<dir>/<gguf_basename> → /data/ollama/models/blobs/sha256-{hash} (软链接)
    7. 同目录 mmproj-*.gguf 也建立软链接 (若用户在 ollama blobs 旁放了)
    8. 写 model_params (如不存在, 用 _fallback 初始化; per-model 走「🎯 默认值」手动配置)

    返回: {scanned, linked, skipped, errors, registered: [{gguf, short, dir, target}]}
    """
    global _model_cache, _cache_timestamps
    # v1.6.2-patch4: 清 beellama 缓存, 避免 ingest 后 30s 内 /api/status 仍返旧列表
    _model_cache["beellama"] = None
    _cache_timestamps["beellama"] = 0
    blobs_dir = Path(OLLAMA_MODELS_DIR) / "blobs"
    home_models = Path.home() / "models"
    if not blobs_dir.exists():
        return {"scanned": 0, "linked": [], "skipped": [], "errors": [f"blobs 目录不存在: {blobs_dir}"]}

    # 1. 扫描 ollama blobs/ 中非 sha256- 开头的 .gguf/.bin (用户下载的)
    user_files = []
    for f in blobs_dir.iterdir():
        if not f.is_file() and not f.is_symlink():
            continue
        if f.name.startswith("sha256-"):
            continue
        if not f.name.lower().endswith((".gguf", ".bin")):
            continue
        user_files.append(f)
    if not user_files:
        return {"scanned": 0, "linked": [], "skipped": [], "errors": []}

    # 5a. short_name → dir 映射 (与 alias_map 保持一致)
    # 这反映用户 ~/models/ 下的实际目录命名习惯
    short_to_dir = {
        'qwen3.6-q3': 'qwen3.6-35b',
        'qwen3.6-uncensored': 'qwen3.6-35b-uncensored',
        'qwen3.6-27b': 'qwen3.6-27b',
        'qwen3-14b': 'qwen3-14b',
        'qwen3-vl': 'qwen3-vl',
        'gemma-4-26b': 'gemma-4-26b',
        'gemma4': 'gemma-4-26b',
    }

    linked = []
    skipped = []
    errors = []
    for src in user_files:
        src_path = str(src)
        src_name = src.name
        try:
            # 2. 计算 sha256 (增量, 8MB chunks)
            sha_hasher = hashlib.sha256()
            with open(src, "rb") as f:
                while True:
                    chunk = f.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    sha_hasher.update(chunk)
            sha = sha_hasher.hexdigest()
            sha_blob = blobs_dir / f"sha256-{sha}"

            # 3. 在 blobs/ 软链接为 sha256-{hash} (幂等)
            if not sha_blob.exists():
                os.symlink(src_path, str(sha_blob))

            # 4. 解析 GGUF header → 推 short_name
            short_name = _extract_short_model_name(src_name)
            # 如果短名是文件名本身 (regex 没命中), fallback 使用目录里已有命名
            if short_name == src_name.replace('.gguf', '').replace('.bin', ''):
                # regex 未命中, 用 general.name 或 fallback
                info = _parse_gguf_header(str(sha_blob))
                gguf_name = info.get("name")
                if gguf_name:
                    short_name = gguf_name.lower().replace('-', '-')
                else:
                    short_name = f"gguf-{sha[:8]}"

            # 5b. 决定 dir 名
            dir_name = short_to_dir.get(short_name, short_name)
            target_dir = home_models / dir_name
            target_dir.mkdir(parents=True, exist_ok=True)
            target_link = target_dir / src_name

            # 6. ~/models/<dir>/<basename> → /data/ollama/models/blobs/sha256-{hash}
            # 指向 sha_blob (而非原文件) — 避免原文件被 ollama 改名/删 后链接失效
            if target_link.is_symlink() or target_link.exists():
                if target_link.is_symlink() and os.readlink(str(target_link)) == str(sha_blob):
                    skipped.append(f"{dir_name}/{src_name} (已存在, 指向同一目标)")
                else:
                    skipped.append(f"{dir_name}/{src_name} (已存在但指向不同目标)")
                continue

            os.symlink(str(sha_blob), str(target_link))

            # 7. mmproj: 同 dir (ollama blobs 旁) 扫 mmproj-*.gguf, 软链到 ~/models/<dir>/
            # 暂不处理: 实际 mmproj 通常与 GGUF 一起放在 ollama blobs, 需要 sha 链; 复杂,
            # 当前只处理 LLM GGUF, mmproj 由用户手动管理 (与现有 qwen3-vl/mmproj-F16.gguf 一致)
            mmproj_linked = 0
            for mmproj_src in blobs_dir.iterdir():
                if not (mmproj_src.is_file() or mmproj_src.is_symlink()):
                    continue
                if 'mmproj' not in mmproj_src.name.lower():
                    continue
                # 仅当 mmproj 与当前 GGUF basename 相关时 (启发式: 同名/同 base)
                # 简单: 不自动链, 避免误链
                # 如果用户需要 mmproj 自动链, 可手动 ln -s
                _ = mmproj_src  # suppress unused

            size = sha_blob.stat().st_size if sha_blob.exists() else src.stat().st_size

            # 8. v1.6.2-patch1: 自动写 per-model 字典 + defaults (避免加载时报"缺 per-model 配置")
            # 逻辑: 从 _load_defaults 读 _fallback, 为该 short_name 初始化 defaults + per-model
            # 已存在则跳过 (不覆盖用户手动调过的值)
            init_status = _init_per_model_for_ingest(short_name)
            if init_status.get("error"):
                # 初始化失败不阻断软链 (用户后续可在 WebUI 手动填)
                init_status = {"warning": init_status["error"]}

            linked.append({
                "src": src_name,
                "short": short_name,
                "dir": dir_name,
                "target": str(sha_blob),
                "link": str(target_link),
                "size": size,
                "sha": sha[:12],
                "per_model": init_status,
            })
            audit_log("ingest beellama",
                      f"src={src_name}, short={short_name}, dir={dir_name}, sha={sha[:12]}, per_model={init_status}", "ok")
        except Exception as e:
            errors.append(f"{src_name}: {e}")
            audit_log("ingest beellama 失败", f"file={src_name}, error={e}", "error")

    return {
        "scanned": len(user_files),
        "linked": linked,
        "skipped": skipped,
        "errors": errors,
    }


def _auto_register_gguf_for_ollama():
    """v1.1.15: 扫描 /data/ollama/models/blobs/ 中未被 manifest 引用的 GGUF,
    为每个自动创建 params blob (num_ctx=131072) + config blob + manifest.
    不解析 GGUF 内容, 直接用文件 sha256 作为 model layer digest. 秒级完成.
    返回: {"registered": [name,...], "skipped_existing": [...], "errors": [...]}
    """
    import json as _json
    blobs_dir = Path(OLLAMA_MODELS_DIR) / "blobs"
    manifests_dir = Path(OLLAMA_MODELS_DIR) / "manifests" / "registry.ollama.ai" / "library"
    if not blobs_dir.exists():
        return {"registered": [], "skipped_existing": [], "errors": [f"blobs 目录不存在: {blobs_dir}"]}

    # 1. 收集所有 manifest 已引用的 sha256
    referenced = set()
    if manifests_dir.exists():
        for mf in manifests_dir.rglob("*"):
            if not mf.is_file():
                continue
            try:
                d = _json.loads(mf.read_text())
                for layer in d.get("layers", []):
                    digest = layer.get("digest", "")
                    if digest.startswith("sha256:"):
                        referenced.add(digest.split(":", 1)[1])
                cfg = d.get("config", {}).get("digest", "")
                if cfg.startswith("sha256:"):
                    referenced.add(cfg.split(":", 1)[1])
            except Exception:
                continue

    # 2. 扫描 blobs/, 找未被引用的 GGUF
    candidates = []
    for blob in blobs_dir.iterdir():
        if not blob.is_file() or not blob.name.startswith("sha256-"):
            continue
        sha = blob.name.split("-", 1)[1]
        if sha in referenced:
            continue
        # 通过 magic 判断是否是 GGUF (前 4 字节: GGUF)
        try:
            with open(blob, "rb") as f:
                magic = f.read(4)
            if magic != b"GGUF":
                continue
        except Exception:
            continue
        size = blob.stat().st_size
        candidates.append((sha, size, blob.name))

    # 3. 为每个候选写 manifest
    registered = []
    errors = []
    for sha, size, blob_name in candidates:
        # 生成模型名: 取 sha 前 8 位避免冲突
        model_short = f"auto-{sha[:8]}"
        try:
            # 3a. 写 params blob (num_ctx=131072)
            params_data = _json.dumps({"num_ctx": 131072}).encode()
            params_sha = hashlib.sha256(params_data).hexdigest()
            params_blob = blobs_dir / f"sha256-{params_sha}"
            if not params_blob.exists():
                params_blob.write_bytes(params_data)

            # 3b. 写 config blob
            config_data = _json.dumps({
                "model_sha": sha,
                "model_size": size,
                "num_ctx": 131072,
            }).encode()
            config_sha = hashlib.sha256(config_data).hexdigest()
            config_blob = blobs_dir / f"sha256-{config_sha}"
            if not config_blob.exists():
                config_blob.write_bytes(config_data)

            # 3c. 写 manifest
            model_dir = manifests_dir / model_short
            model_dir.mkdir(parents=True, exist_ok=True)
            manifest = {
                "schemaVersion": 2,
                "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
                "config": {
                    "mediaType": "application/vnd.docker.container.image.v1+json",
                    "digest": f"sha256:{config_sha}",
                    "size": len(config_data),
                },
                "layers": [
                    {
                        "mediaType": "application/vnd.ollama.image.model",
                        "digest": f"sha256:{sha}",
                        "size": size,
                    },
                    {
                        "mediaType": "application/vnd.ollama.image.params",
                        "digest": f"sha256:{params_sha}",
                        "size": len(params_data),
                    },
                ],
            }
            (model_dir / "ctx128k").write_text(_json.dumps(manifest, indent=2))
            registered.append(f"{model_short}:ctx128k")
            audit_log("自动注册 GGUF", f"name={model_short}:ctx128k, size={size}, sha={sha[:12]}", "ok")
        except Exception as e:
            errors.append(f"{model_short}: {e}")
            audit_log("自动注册 GGUF 失败", f"sha={sha[:12]}, error={e}", "error")

    return {"registered": registered, "skipped_existing": [], "errors": errors}


@app.route("/api/auto_register_gguf", methods=["POST"])
def api_auto_register_gguf():
    """v1.1.15: 「➕ 添加/移除模型进列表」按钮的零配置注册 GGUF
    扫描 blobs/ 中未被 manifest 引用的 GGUF, 自动创建 manifest.
    可选 body: {"num_ctx": 131072} (默认 131072)
    """
    data = request.get_json(silent=True) or {}
    # 允许前端传入 num_ctx 覆盖, 当前后端固定 131072 但保留接口扩展性
    num_ctx = int(data.get("num_ctx", 131072))
    if not (1024 <= num_ctx <= 1048576):
        return jsonify({"error": f"num_ctx 越界: {num_ctx}"}), 400

    result = _auto_register_gguf_for_ollama()
    return jsonify({
        "status": "ok",
        "registered": result["registered"],
        "skipped_existing": result["skipped_existing"],
        "errors": result["errors"],
        "num_ctx": num_ctx,
    })


@app.route("/api/set_visible_models", methods=["POST"])
def api_set_visible_models():
    """v1.1.7-patch3: 提交「➕ 添加模型进列表」模态框勾选结果
    接受用户勾选的 visible 列表, 写 hidden 列表 (hidden = all - visible)
    """
    data = request.get_json(silent=True) or {}
    framework = data.get("framework")
    visible = data.get("visible", [])
    if framework not in ("beellama", "ollama", "comfyui"):
        return jsonify({"error": "framework 必须是 beellama/ollama/comfyui"}), 400
    if not isinstance(visible, list):
        return jsonify({"error": "visible 必须是列表"}), 400
    # 重新扫描拿全量 (避免遗漏新文件)
    global _model_cache, _cache_timestamps
    _model_cache.pop(framework, None)
    _cache_timestamps.pop(framework, None)
    all_models = _scan_framework_models(framework)
    # 计算新的 hidden (all - visible), 同时校验 visible 必须是 all 的子集
    all_set = set(all_models)
    visible_clean = [m for m in visible if m in all_set]
    new_hidden = sorted(all_set - set(visible_clean))
    hidden = _load_hidden()
    hidden[framework] = new_hidden
    _save_hidden(hidden)
    audit_log("设置可见模型列表",
              f"framework={framework}, total={len(all_models)}, visible={len(visible_clean)}, hidden={len(new_hidden)}", "ok")
    return jsonify({"status": "ok", "visible": visible_clean, "hidden": new_hidden, "total": len(all_models)})


@app.route("/api/refresh_models", methods=["POST"])
def api_refresh_models():
    """v1.1.7-patch2: 「➕ 添加模型进列表」按钮
    行为: 强制重新扫描所有默认位置 + 清空所有隐藏列表
    等同于"重新发现所有可用模型" (放下新文件/取消所有隐藏后用)
    """
    # 1) 清空 _model_cache (强制下次 get_framework_models 重新扫描)
    global _model_cache, _cache_timestamps
    _model_cache.clear()
    _cache_timestamps.clear()
    # 2) 清空 hidden 列表 (相当于"取消所有移除")
    empty_hidden = {"beellama": [], "ollama": [], "comfyui": []}
    _save_hidden(empty_hidden)
    # 3) 立即重新扫描并返回新列表
    results = {}
    for fw in ("beellama", "ollama", "comfyui"):
        results[fw] = get_framework_models(fw, force_refresh=True)
    audit_log("刷新模型列表",
              f"清空 hidden + 重扫; 各框架模型数: {[(k, len(v)) for k, v in results.items()]}", "ok")
    return jsonify({"status": "ok", "models": results, "hidden": empty_hidden})


@app.route("/api/models_by_framework")
def api_models_by_framework():
    """获取指定框架的模型列表（独立于当前框架）
    v1.6.2-patch3: 返回 display_names 字段 (short_name), 解决「默认设置卡下拉两个 qwen3.6 显示相同」bug
    """
    fw = request.args.get("framework", "beellama")
    if fw not in ["ollama", "beellama", "comfyui"]:
        return jsonify({"error": "无效的框架"}), 400
    models = get_framework_models(fw, force_refresh=True)
    # beellama 返回的是完整相对路径 (dir/basename), 需要 short_name 给下拉显示
    if fw == "beellama":
        display_names = [_extract_short_model_name(m) for m in models]
    else:
        display_names = list(models)  # ollama/comfyui 已是 short_name
    return jsonify({"framework": fw, "models": models, "display_names": display_names})

@app.route("/api/audit_logs")
def api_audit_logs():
    """返回最近的审计日志"""
    limit = request.args.get("limit", 20, type=int)
    try:
        if not os.path.exists(LOG_FILE):
            return jsonify([])
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
        return jsonify(lines[-limit:])
    except Exception:
        return jsonify([])

@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok"})

# ── 初始化 ───────────────────────────────────────────────────────
def initialize():
    global current_framework, current_model, last_activity_time
    config = load_config()

    # 0. 一次性迁移: 为 defaults.json 中列出的模型补全 per-model 缺失字段
    #    原因: 4 个老模型 wrapper 不再 case 兑底, per-model 缺字段会启动报错
    #    策略: 保留用户已设值, 只补 None 字段
    _migrate_legacy_models()

    # 1. 先检测当前实际运行的框架（不改动，只检测）
    detect_current_framework()

    # 2. 尝试恢复上次会话
    lf = config.get("last_framework")
    lm = config.get("last_model")

    # ⚡ 修复：只有在没有检测到任何运行中框架时，才执行默认启动
    # 如果已经有框架在运行（detect_current_framework 已设置），保留现有状态
    if current_framework:
        log.info(f"保留当前运行中的框架：{current_framework}，模型：{current_model}")
    elif lf and is_service_running(lf + ".service"):
        current_framework = lf
        if lm:
            current_model = lm
            log.info(f"恢复上次会话：框架 {lf} 模型 {lm}")
        else:
            log.info(f"恢复上次会话：框架 {lf} (无模型)")
    else:
        # 3. 没有运行中的框架 & 没有有效的上次会话 → 使用默认框架（不自动加载模型）
        df = config.get("default_framework", "beellama")
        if switch_framework_to(df):
            current_framework = df
            current_model = None
            log.info(f"使用默认框架 {df}（未加载模型，需手动加载）")

    # 4. 最终兜底：如果 still 没有 current_framework，再尝试推断
    if not current_framework:
        detect_current_framework()
        if current_framework:
            log.info(f"检测到运行中的框架：{current_framework}")

    # 初始化完成后重置加载状态（避免残留上次会话的状态）
    _loading_state.update({"status": "idle", "framework": None, "model": None,
                           "message": "", "progress": 0, "start_time": 0})
    last_activity_time = time.time()
    start_idle_thread()

def shutdown():
    stop_idle_thread_func()
    config = load_config()
    config["last_framework"] = current_framework
    config["last_model"] = current_model
    save_config(config)

# ── HTML 模板 ───────────────────────────────────────────────────────
INDEX_HTML = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<title>框架管理器 v1.1.19</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--border:#30363d;--text:#c9d1d9;--text-dim:#8b949e;--accent:#58a6ff;--green:#3fb950;--red:#f85149;--orange:#d29922}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);padding:24px}
.container{max-width:800px;margin:0 auto}
h1{font-size:1.6rem;font-weight:600;margin-bottom:20px;display:flex;align-items:center;gap:10px}
h1 small{font-size:0.85rem;color:var(--text-dim);font-weight:400}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:20px;margin-bottom:16px}
.card h2{font-size:1rem;font-weight:600;margin-bottom:14px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px}
.status-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.stat-item{display:flex;flex-direction:column;gap:4px}
.stat-label{font-size:0.78rem;color:var(--text-dim)}
.stat-value{font-size:1.1rem;font-weight:600}
.stat-value.ollama{color:var(--accent)}
.stat-value.beellama{color:var(--orange)}
.stat-value.comfyui{color:var(--green)}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:0.75rem;font-weight:600}
.badge.on{background:#1a3a2a;color:var(--green);border:1px solid #2d5a3e}
.badge.off{background:#3a1a1a;color:var(--red);border:1px solid #5a2d2d}
.btn-row{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.btn{display:inline-flex;align-items:center;gap:6px;padding:8px 18px;border:1px solid var(--border);border-radius:6px;font-size:0.88rem;font-weight:500;cursor:pointer;background:#21262d;color:var(--text);transition:all 0.15s}
.btn:hover{background:#30363d;border-color:var(--accent)}
.btn:disabled{opacity:0.5;cursor:not-allowed}
.btn.primary{background:#1f6feb;border-color:#1f6feb;color:#fff}
.btn.primary:hover{background:#388bfd}
.btn.danger{border-color:var(--red);color:var(--red)}
.btn.danger:hover{background:#3a1a1a}
.btn.success{border-color:var(--green);color:var(--green)}
.btn.success:hover{background:#1a3a2a}
.form-row{display:flex;flex-wrap:wrap;gap:12px;align-items:end;margin-top:14px}
.form-group{display:flex;flex-direction:column;gap:4px}
.form-group label{font-size:0.78rem;color:var(--text-dim)}
.form-group select,.form-group input{padding:6px 12px;border:1px solid var(--border);border-radius:6px;background:#21262d;color:var(--text);font-size:0.88rem}
.form-group select:focus,.form-group input:focus{outline:none;border-color:var(--accent)}
.spin{display:inline-block;width:16px;height:16px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin 0.8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.toast{position:fixed;top:20px;right:20px;padding:12px 20px;border-radius:8px;color:#fff;font-size:0.9rem;font-weight:500;z-index:999;animation:fadeIn 0.2s,fadeOut 0.3s 3s forwards}
.toast.success{background:#1a6b2a;border:1px solid #2d8a3e}
.toast.error{background:#6b1a1a;border:1px solid #8a2d2d}
.toast.info{background:#1a3a6b;border:1px solid #2d5a8a}
@keyframes fadeIn{from{opacity:0;transform:translateY(-10px)}to{opacity:1;transform:translateY(0)}}
@keyframes fadeOut{from{opacity:1}to{opacity:0}}
#log-area{margin-top:12px;background:#0a0e14;border:1px solid var(--border);border-radius:6px;padding:12px;font-family:'JetBrains Mono','Fira Code',monospace;font-size:0.78rem;max-height:200px;overflow-y:auto;color:var(--text-dim);white-space:pre-wrap;word-break:break-all}
.vram-bar{width:100%;height:8px;background:#21262d;border-radius:4px;overflow:hidden;margin-top:6px}
.vram-fill{height:100%;border-radius:4px;transition:width 0.5s}
.vram-fill.low{background:var(--green)}
.vram-fill.med{background:var(--orange)}
.vram-fill.high{background:var(--red)}
.inline-code{font-family:monospace;background:#21262d;padding:1px 6px;border-radius:3px;font-size:0.82rem}
.footer{text-align:center;color:var(--text-dim);font-size:0.75rem;margin-top:30px;display:flex;justify-content:space-between;align-items:center}
.processing-overlay{position:absolute;inset:0;background:rgba(13,17,23,0.85);display:flex;align-items:center;justify-content:center;gap:12px;border-radius:8px;font-size:0.9rem;color:var(--accent);font-weight:500;z-index:10}
.processing-overlay .spin{width:18px;height:18px;border-width:2px}
.relative-card{position:relative}
@media(max-width:600px){.status-grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="container">
<h1>⚙️ 框架管理器 <small>Ollama ↔ beellama ↔ ComfyUI</small></h1>
<div class="card">
<h2>📊 当前状态</h2>
<div class="status-grid" id="status-grid">
<div class="stat-item"><span class="stat-label">框架</span><span class="stat-value" id="sv-framework">—</span></div>
<div class="stat-item"><span class="stat-label">PID</span><span class="stat-value" id="sv-pid" style="font-size:0.9rem;font-family:monospace">—</span></div>
<div class="stat-item"><span class="stat-label">当前模型</span><span class="stat-value" id="sv-model" style="font-size:0.95rem">—</span></div>
<div class="stat-item"><span class="stat-label">VRAM 使用</span><span class="stat-value" id="sv-vram">—</span><div class="vram-bar"><div class="vram-fill low" id="vram-bar" style="width:0%"></div></div></div>
</div>
</div>
<div class="card">
<h2>🔄 框架切换</h2>
<div class="btn-row">
<button class="btn primary" onclick="switchFramework('ollama')" id="btn-ollama"><span>🟦</span> 切换到 Ollama</button>
<button class="btn success" onclick="switchFramework('beellama')" id="btn-beellama"><span>🟧</span> 切换到 beellama</button>
<button class="btn" onclick="switchFramework('comfyui')" id="btn-comfyui"><span>🟨</span> 切换到 ComfyUI</button>
<button class="btn danger" onclick="stopAllEngines()" id="btn-stop-all"><span>🛑</span> 停止所有框架</button>
</div>
</div>
<!-- ⚙️ beellama 参数设置 (仅当切换到 beellama 时显示) -->
<div class="card" id="beellama-params-card" style="display:none;">
<h2>⚙️ beellama 参数设置</h2>
<div class="form-row">
  <div class="form-group">
    <label>KV Cache 量化</label>
    <select id="beellama-turbo-level" style="min-width:150px;">
      <option value="">f16 (16-bit, 完整精度)</option>
      <option value="q8_0">q8_0 (8-bit, 折中)</option>
      <option value="4">turbo4 (4-bit)</option>
      <option value="3">turbo3 (3-bit, 推荐)</option>
      <option value="2">turbo2 (2-bit)</option>
    </select>
  </div>
  <div class="form-group">
    <label>Flash Attention</label>
    <select id="beellama-flash-attn" style="min-width:120px;">
      <option value="true">开启</option>
      <option value="false">关闭</option>
    </select>
  </div>
  <div class="form-group">
    <label>Reasoning 输出</label>
    <select id="beellama-reasoning-off" style="min-width:120px;">
      <option value="true">关闭 (合并到 content)</option>
      <option value="false">开启 (分离到 reasoning_content)</option>
    </select>
  </div>
  <div class="form-group" style="justify-content:flex-end;">
    <button class="btn success" onclick="saveBeellamaParams()" id="btn-save-beellama-params">💾 保存并重启 beellama</button>
  </div>
</div>
<p style="font-size:0.75rem;color:var(--text-dim);margin-top:8px;">
💡 <b>turbo3</b>: 速度快/功耗低 (~100W)，但长对话可能乱码 · <b>f16</b>: 稳定不乱码/功耗高 (~200W) · 修改后需重启 beellama
</p>
</div>
<!-- 📥 beellama 自动注册下载的模型 (v1.6.2 新增, 切到 beellama 时显示) -->
<div class="card" id="ingest-beellama-card" style="display:none;">
<h2>📥 自动注册下载的模型</h2>
<p style="font-size:0.78rem;color:var(--text-dim);margin-top:4px;margin-bottom:10px;">
  <b>扫描 <code>/data/ollama/models/blobs/</code> 中任意命名的 .gguf</b> · 计算 sha256 · 在 <code>~/models/&lt;dir&gt;/</code> 下建立软链接 → ollama blob · 同时初始化 per-model 参数 (ctx/parallel/ngl) · 加载 beellama 后即可用 · <b style="color:#4ade80;">不影响 ollama manifest / modelfile</b> · <b style="color:#4ade80;">不删除 ollama blobs 里的原文件</b>
</p>
<div class="form-row">
  <div class="form-group" style="flex:1;">
    <button class="btn primary" onclick="ingestBeellama()" id="btn-ingest-beellama" style="font-size:0.95rem;padding:8px 16px;">📥 扫描并注册进 beellama</button>
  </div>
</div>
<div id="ingest-beellama-result" style="margin-top:10px;font-size:0.82rem;color:var(--text-dim);"></div>
<p style="font-size:0.75rem;color:var(--text-dim);margin-top:8px;">
💡 <b>使用流程</b>：从 HuggingFace 等下载的 .gguf 文件 (任意名称) 放到 <code>/data/ollama/models/blobs/</code> → 点击按钮 → 注册到 <code>~/models/&lt;short_dir&gt;/</code> → 在「模型 & 参数」中可见 → beellama 加载
</p>
<p style="font-size:0.75rem;color:var(--text-dim);margin-top:4px;">
💡 <b>short_dir 映射</b>：qwen3.6-q3→qwen3.6-35b / qwen3.6-uncensored→qwen3.6-35b-uncensored / qwen3-vl→qwen3-vl / gemma-4-26b→gemma-4-26b / 其他→short_name
</p>
</div>
<!-- 🎛️ Ollama 进程参数 (v1.1.16 简化, 仅留 GPU_LAYERS) -->
<div class="card" id="ollama-params-card" style="display:none;">
<h2>🎛️ Ollama 进程参数</h2>
<p style="font-size:0.78rem;color:var(--text-dim);margin-top:4px;margin-bottom:10px;">
  KEEP_ALIVE / NUM_PARALLEL / BATCH_SIZE / FLASH_ATTENTION 已锁定为最优值，无需调整。<br>
  仅 <b>GPU_LAYERS</b>（多少层 offload 到 GPU）依显卡而异，需要手动设。修改后重启 Ollama。
</p>
<div class="form-row">
  <div class="form-group">
    <label>GPU_LAYERS（0=全 CPU, 空=不限/全 GPU, 35=~22.5GB 卡上常用值）</label>
    <input type="number" id="ollama-gpu-layers" placeholder="留空=不限" min="0" max="999" style="min-width:120px;">
  </div>
  <div class="form-group" style="justify-content:flex-end;">
    <button class="btn success" onclick="saveOllamaGlobalParams()" id="btn-save-ollama-global">💾 保存并重启 Ollama</button>
  </div>
</div>
<p style="font-size:0.75rem;color:var(--text-dim);margin-top:8px;">
💡 <b>常见显卡推荐 GPU_LAYERS</b>：<br>
&nbsp;&nbsp;· 2080Ti / 22GB：<b>35</b>（推荐，避免 128K 上下文 OOM）<br>
&nbsp;&nbsp;· 3090 / 24GB：<b>99</b>（35B MoE Q3 可全 GPU）<br>
&nbsp;&nbsp;· 4090 / 24GB：<b>99</b><br>
&nbsp;&nbsp;· A100 40-80GB / H100：<b>99</b>（大模型全 GPU）<br>
&nbsp;&nbsp;· 无 GPU / CPU only：<b>0</b>
</p>
</div>
<!-- 📦 Ollama 模型专属参数 (v1.1.8-patch2 新增, 加载 ollama 模型后显示) -->
<div class="card relative-card" id="ollama-model-params-card" style="display:none;">
<h2>📦 Ollama 模型专属参数：<span id="ollama-model-params-name"></span></h2>
<div id="ollama-model-params-overlay" class="processing-overlay" style="display:none;">
  <div class="spin"></div>
  <span>正在保存 Modelfile 并重建 tag...</span>
</div>
<div class="form-row">
  <div class="form-group">
    <label>num_ctx (决定 tag 后缀, 必填)</label>
    <select id="ollama-num-ctx" style="min-width:150px;">
      <option value="8192">8K (省显存)</option>
      <option value="32768">32K</option>
      <option value="65536">64K</option>
      <option value="65536" selected>64K ⭐推荐</option>
      <option value="262144">256K</option>
    </select>
  </div>
  <div class="form-group">
    <label>temperature (留空=默认)</label>
    <input type="number" id="ollama-temperature" step="0.1" min="0" max="2" placeholder="0.8" style="min-width:80px;">
  </div>
  <div class="form-group">
    <label>top_p (留空=默认)</label>
    <input type="number" id="ollama-top-p" step="0.05" min="0" max="1" placeholder="0.9" style="min-width:80px;">
  </div>
  <div class="form-group">
    <label>top_k (留空=默认)</label>
    <input type="number" id="ollama-top-k" min="1" max="100" placeholder="40" style="min-width:80px;">
  </div>
  <div class="form-group">
    <label>repeat_penalty (留空=默认)</label>
    <input type="number" id="ollama-repeat-penalty" step="0.05" min="0" max="2" placeholder="1.1" style="min-width:80px;">
  </div>
  <div class="form-group" style="justify-content:flex-end;">
    <button class="btn" onclick="resetOllamaModelParams()" id="btn-reset-ollama-model-params">🔄 恢复默认值</button>
    <button class="btn success" onclick="saveOllamaModelParams()" id="btn-save-ollama-model-params" style="margin-left:8px;">💾 保存并重建 tag</button>
  </div>
</div>
<p style="font-size:0.75rem;color:var(--text-dim);margin-top:8px;">
💡 <b>优先级最高</b> · 修改 <b>num_ctx</b> 会创建新 tag (如 qwen3.6-q3:ctx128k), 旧 tag 保留 · 其他字段改后 tag 名不变 · 保存后请手动 <code>ollama run 新tag</code> 加载
</p>
</div>
<!-- 📋 新模型注册参数 (v1.1.17 新增, 切到 ollama 时显示) -->
<div class="card" id="manifest-gen-params-card" style="display:none;">
<h2>📋 新模型注册参数</h2>
<p style="font-size:0.78rem;color:var(--text-dim);margin-top:4px;margin-bottom:10px;">
  <b>手动下载的模型放到指定位置后, 自动扫描加载到 ollama 框架下进行管理前, 需生成相应的 manifests, 自动生成时调用这里设置的相关参数</b> · 不影响现有模型 · 保存在 <code>framework-manager/config/ollama_manifest_generate_parameter.json</code> · 下拉中 ⭐ 为推荐值
</p>
<div class="form-row">
  <div class="form-group">
    <label>num_ctx (上下文)</label>
    <select id="mgen-num-ctx" style="min-width:200px;">
      <option value="4096">4K (小模型/embedding)</option>
      <option value="8192">8K (bge-m3 专用)</option>
      <option value="16384">16K</option>
      <option value="32768">32K</option>
      <option value="65536">64K (qwen3:14b / gemma4)</option>
      <option value="131072" selected>⭐ 128K (推荐, qwen3.6 / qwen3-vl)</option>
      <option value="262144">256K (上限, 可能 OOM)</option>
    </select>
  </div>
  <div class="form-group">
    <label>temperature</label>
    <select id="mgen-temperature" style="min-width:180px;">
      <option value="0.0">0.0 (完全确定性)</option>
      <option value="0.3">0.3 (保守/代码)</option>
      <option value="0.7" selected>⭐ 0.7 (推荐, 平衡)</option>
      <option value="1.0">1.0 (标准)</option>
      <option value="1.5">1.5 (发散/创作)</option>
    </select>
  </div>
  <div class="form-group">
    <label>top_p</label>
    <select id="mgen-top-p" style="min-width:160px;">
      <option value="0.5">0.5 (保守)</option>
      <option value="0.8">0.8</option>
      <option value="0.9">0.9</option>
      <option value="0.95" selected>⭐ 0.95 (推荐)</option>
      <option value="0.99">0.99 (发散)</option>
    </select>
  </div>
  <div class="form-group">
    <label>top_k</label>
    <select id="mgen-top-k" style="min-width:150px;">
      <option value="10">10 (严格)</option>
      <option value="20" selected>⭐ 20 (推荐)</option>
      <option value="40">40</option>
      <option value="80">80 (发散)</option>
    </select>
  </div>
  <div class="form-group">
    <label>repeat_penalty</label>
    <select id="mgen-repeat-penalty" style="min-width:160px;">
      <option value="1" selected>⭐ 1.0 (推荐)</option>
      <option value="1.1">1.1 (轻微)</option>
      <option value="1.2">1.2 (中等)</option>
      <option value="1.3">1.3 (强)</option>
    </select>
  </div>
  <div class="form-group" style="justify-content:flex-end;">
    <button class="btn success" onclick="saveManifestGenParams()" id="btn-save-mgen-params">💾 保存</button>
  </div>
</div>
</div>
<!-- 📥 自动注册下载的模型 (v1.1.18 新增, 切到 ollama 时显示) -->
<div class="card" id="ingest-gguf-card" style="display:none;">
<h2>📥 自动注册下载的模型</h2>
<p style="font-size:0.78rem;color:var(--text-dim);margin-top:4px;margin-bottom:10px;">
  <b>扫描 <code>/data/ollama/models/blobs/</code> 中任意命名的 .gguf</b> · 自动计算 sha256 · 硬链接为 <code>sha256-xxx</code> · 删除原文件 · 解析 GGUF header · 生成 manifest · 使用「📋 新模型注册参数」中的设置 · <b style="color:#4ade80;">不影响已注册模型</b>
</p>
<div class="form-row">
  <div class="form-group" style="flex:1;">
    <button class="btn primary" onclick="ingestGguf()" id="btn-ingest-gguf" style="font-size:0.95rem;padding:8px 16px;">📥 扫描并自动注册用户下载的模型</button>
  </div>
</div>
<div id="ingest-gguf-result" style="margin-top:10px;font-size:0.82rem;color:var(--text-dim);"></div>
<p style="font-size:0.75rem;color:var(--text-dim);margin-top:8px;">
💡 <b>使用流程</b>：从 HuggingFace 等下载的 .gguf 文件 (任意名称) 放到 <code>/data/ollama/models/blobs/</code> → 点击按钮 → 自动生成 manifest → 在「模型 & 参数」中可见
</p>
</div>
<!-- 🎯 Ollama 默认值 (v1.1.8-patch2 新增, 切到 ollama 时显示) -->
<div class="card" id="ollama-defaults-card" style="display:none;">
<h2>🎯 Ollama 默认值 <span id="ollama-defaults-current-badge" style="font-size:0.78rem;color:var(--text-dim);font-weight:normal;">(未加载模型)</span></h2>
<p style="font-size:0.78rem;color:var(--text-dim);margin-top:4px;margin-bottom:10px;">
<b>仅用于初始化/恢复</b> · 不参与 runtime 优先级 · 保存在 <code>~/.openclaw/config/framework-manager-defaults.json</code> 的 <code>ollama</code> 段 · 点「🔄 恢复默认」会把值写入模型专属参数
</p>
<div style="background:#1a2a3a;padding:8px 12px;border-radius:4px;margin-bottom:10px;">
  <div style="color:var(--accent);font-size:0.82rem;margin-bottom:6px;">⚙️ Ollama 统一默认 (_fallback)</div>
  <div class="form-row" style="margin:0;">
    <div class="form-group" style="margin:0;">
      <label>num_ctx</label>
      <input type="number" id="ollama-defaults-fallback-num-ctx" placeholder="131072" min="512" max="1048576" step="512" style="min-width:110px;">
    </div>
    <div class="form-group" style="margin:0;">
      <label>temperature</label>
      <input type="number" id="ollama-defaults-fallback-temp" step="0.1" min="0" max="2" placeholder="0.8" style="min-width:80px;">
    </div>
    <div class="form-group" style="margin:0;">
      <label>top_p</label>
      <input type="number" id="ollama-defaults-fallback-top-p" step="0.05" min="0" max="1" placeholder="0.9" style="min-width:80px;">
    </div>
  </div>
</div>
<div style="background:#1a2a3a;padding:8px 12px;border-radius:4px;margin-bottom:10px;">
  <div style="color:var(--accent);font-size:0.82rem;margin-bottom:6px;">📋 当前模型默认值: <span id="ollama-defaults-current-name">—</span></div>
  <div id="ollama-defaults-current-row" style="font-size:0.85rem;">
    <div style="color:var(--text-dim);padding:6px 0;">加载 ollama 模型后, 在此编辑该模型的默认值</div>
  </div>
</div>
<div class="form-group" style="justify-content:flex-end;">
  <button class="btn success" onclick="saveOllamaDefaults()" id="btn-save-ollama-defaults">💾 保存 ollama defaults</button>
</div>
</div>
<!-- ⚙️ ComfyUI 参数设置 (v1.1.8 新增, 切换到 comfyui 时显示) -->
<div class="card" id="comfyui-params-card" style="display:none;">
<h2>⚙️ ComfyUI 启动参数</h2>
<div class="form-row">
  <div class="form-group">
    <label><input type="checkbox" id="comfyui-lowvram" style="width:auto;margin-right:6px;">LowVRAM 模式</label>
  </div>
  <div class="form-group">
    <label><input type="checkbox" id="comfyui-gpu-only" style="width:auto;margin-right:6px;">GPU only</label>
  </div>
  <div class="form-group">
    <label><input type="checkbox" id="comfyui-listen" style="width:auto;margin-right:6px;">对外监听 (0.0.0.0)</label>
  </div>
  <div class="form-group">
    <label>预览方式</label>
    <select id="comfyui-preview-method" style="min-width:140px;">
      <option value="auto">auto (默认)</option>
      <option value="latent2rgb">latent2rgb (快)</option>
      <option value="taesd">taesd (质量高)</option>
      <option value="none">none (不预览)</option>
    </select>
  </div>
  <div class="form-group" style="justify-content:flex-end;">
    <button class="btn success" onclick="saveComfyuiParams()" id="btn-save-comfyui-params">💾 保存并重启 ComfyUI</button>
  </div>
</div>
<p style="font-size:0.75rem;color:var(--text-dim);margin-top:8px;">
💡 <b>LowVRAM</b>: 分块加载, 22GB 卡开 17GB 模型建议开启 · <b>GPU only</b>: 一切丢 GPU (需 ≥24GB) · 修改后重启 ComfyUI
</p>
</div>
<!-- 📂 ComfyUI 模型路径 (v1.1.8 新增, 切换到 comfyui 时显示) -->
<div class="card" id="comfyui-paths-card" style="display:none;">
<h2>📂 ComfyUI 模型路径</h2>
<p style="font-size:0.78rem;color:var(--text-dim);margin-top:4px;margin-bottom:10px;">
配置文件: <code>/data/ComfyUI/extra_model_paths.yaml</code> · 修改后重启 ComfyUI 并自动重扫模型列表
</p>
<div class="form-row" style="margin-top:0;">
  <div class="form-group" style="flex:1;">
    <label>base_path (模型根目录, 自动扫 models/{checkpoints,gguf,diffusion_models,loras})</label>
    <input type="text" id="comfyui-base-path" placeholder="/data/ComfyUI" style="min-width:300px;width:100%;">
  </div>
</div>
<div class="form-row" style="margin-top:8px;">
  <div class="form-group" style="flex:1;">
    <label>custom_paths (额外分类路径, 格式: <code>分类: 绝对路径</code> 一行一条)</label>
    <textarea id="comfyui-custom-paths" rows="4" style="min-width:300px;width:100%;font-family:monospace;font-size:0.85rem;" placeholder="checkpoints: /data/models/extra_checkpoints
loras: /home/wangyc/my_loras"></textarea>
  </div>
</div>
<div class="form-group" style="justify-content:flex-end;margin-top:8px;">
  <button class="btn" onclick="loadComfyuiPaths()" id="btn-reload-comfyui-paths">🔄 从 yaml 重读</button>
  <button class="btn success" onclick="saveComfyuiPaths()" id="btn-save-comfyui-paths" style="margin-left:8px;">💾 保存并重启 ComfyUI</button>
</div>
<p style="font-size:0.75rem;color:var(--text-dim);margin-top:8px;">
💡 <b>base_path</b> 必填 (绝对路径) · <b>custom_paths</b> 可选, 每行 <code>key: path</code>, key 需在 ComfyUI 已知分类中 (checkpoints/loras/vae/controlnet 等)
</p>
</div>
<!-- 📦 模型专属参数卡片 (加载模型后显示) -->
<div class="card relative-card" id="beellama-model-params-card" style="display:none;">
<h2>📦 模型专属参数：<span id="model-params-model-name"></span></h2>
<div id="model-params-overlay" class="processing-overlay" style="display:none;">
  <div class="spin"></div>
  <span id="model-params-overlay-text">正在重启 beellama 并重载模型...</span>
</div>
<div class="form-row">
  <div class="form-group">
    <label>上下文宽度</label>
    <select id="model-ctx-size" style="min-width:150px;">
      <option value="">使用 wrapper 默认</option>
      <option value="8192">8K (省显存)</option>
      <option value="32768">32K</option>
      <option value="65536">64K</option>
      <option value="131072">128K ⭐推荐</option>
    </select>
  </div>
  <div class="form-group">
    <label>并发数</label>
    <select id="model-parallel" style="min-width:120px;">
      <option value="">使用 wrapper 默认</option>
      <option value="1">1 (单用户) ⭐推荐</option>
      <option value="2">2 (默认)</option>
      <option value="4">4 (多用户)</option>
    </select>
  </div>
  <div class="form-group">
    <label>GPU 层数 (-ngl)</label>
    <select id="model-ngpu-layers" style="min-width:120px;">
      <option value="">使用默认值</option>
      <option value="0">0 (纯 CPU)</option>
      <option value="60">60 (平衡)</option>
      <option value="99">99 (全 GPU)</option>
    </select>
  </div>
  <div class="form-group" style="justify-content:flex-end;">
    <button class="btn" onclick="resetModelParams()" id="btn-reset-model-params">🔄 恢复默认值</button>
    <button class="btn success" onclick="saveModelParams()" id="btn-save-model-params">💾 保存模型参数</button>
  </div>
</div>
<p style="font-size:0.75rem;color:var(--text-dim);margin-top:8px;">
💡 🔄 恢复默认 = 从 defaults.models 复制到 per-model · 留空保存 = 清除该字段（wrapper 启动会报错）
</p>

<div style="background:#1a2a3a;padding:8px 12px;border-radius:4px;margin-top:14px;">
  <div style="color:var(--orange);font-size:0.82rem;margin-bottom:6px;">📋 当前模型默认值（仅保存到 defaults.json，不重启 beellama）</div>
  <div id="model-defaults-current-row" style="font-size:0.85rem;">
    <div style="color:var(--text-dim);padding:6px 0;">加载中…</div>
  </div>
  <div class="form-group" style="justify-content:flex-end;margin-top:6px;">
    <button class="btn success" onclick="saveDefaultsCurrentModel()" id="btn-save-defaults-current" style="font-size:0.85rem;">💾 保存默认</button>
  </div>
</div>
</div>
<div class="card" id="defaults-card">
<h2>🎯 统一默认值</h2>
<p style="font-size:0.78rem;color:var(--text-dim);margin-top:4px;margin-bottom:10px;">
⚙️ <b>统一默认 (_fallback)</b>：未来「➕ 添加新模型」会用此值初始化。保存后立即生效（仅改 <code>_fallback</code>，不影响现有模型默认值）。
</p>
<div style="background:#1a2a3a;padding:8px 12px;border-radius:4px;margin-bottom:10px;">
  <div style="color:var(--orange);font-size:0.82rem;margin-bottom:6px;">⚙️ 统一默认 (_fallback)</div>
  <div class="form-row" style="margin:0;">
    <div class="form-group" style="margin:0;">
      <label>上下文 (-c)</label>
      <input type="number" id="defaults-fallback-ctx" placeholder="131072" min="512" max="1048576" step="512" style="min-width:120px;">
    </div>
    <div class="form-group" style="margin:0;">
      <label>并发 (--parallel)</label>
      <input type="number" id="defaults-fallback-parallel" placeholder="2" min="1" max="16" style="min-width:100px;">
    </div>
    <div class="form-group" style="margin:0;">
      <label>GPU 层数 (-ngl)</label>
      <input type="number" id="defaults-fallback-ngl" placeholder="99" min="0" max="200" style="min-width:100px;">
    </div>
  </div>
</div>
<div class="form-group" style="justify-content:flex-end;">
  <button class="btn success" onclick="saveDefaultsFallback()" id="btn-save-defaults-fallback">💾 保存统一默认</button>
</div>
</div>

<!-- 「➕ 添加新模型」确认模态框 -->
<div id="init-model-modal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.6);z-index:9999;align-items:center;justify-content:center;">
  <div style="background:var(--bg-card,#1e2a3a);border-radius:8px;padding:24px;max-width:500px;width:90%;">
    <h3 style="margin-top:0;color:var(--orange);">➕ 初始化新模型</h3>
    <p id="init-model-modal-text" style="font-size:0.95rem;line-height:1.6;"></p>
    <div style="background:#1a2a3a;padding:10px 14px;border-radius:4px;margin:12px 0;font-size:0.85rem;">
      <div style="color:var(--text-dim);">即将写入 defaults.json 和 per-model:</div>
      <div id="init-model-preview" style="margin-top:6px;font-family:monospace;"></div>
    </div>
    <div class="form-group" style="justify-content:flex-end;gap:8px;margin:0;">
      <button class="btn" onclick="cancelInitModel()" style="background:#5a5a5a;border-color:#7a7a7a;">取消</button>
      <button class="btn success" onclick="confirmInitModel()" id="btn-confirm-init">✨ 初始化并启动</button>
    </div>
  </div>
</div>

<!-- 「➕ 添加模型进列表」复选框模态框 (v1.1.7-patch3) -->
<div id="add-models-modal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.6);z-index:9999;align-items:center;justify-content:center;">
  <div style="background:var(--bg-card,#1e2a3a);border-radius:8px;padding:24px;max-width:640px;width:90%;max-height:80vh;display:flex;flex-direction:column;">
    <h3 style="margin-top:0;color:var(--orange);">➕ 添加模型到 <span id="add-models-modal-fw">—</span> 列表</h3>
    <p style="font-size:0.85rem;color:var(--text-dim);margin:4px 0 8px;">
      勾选 = 出现在下拉列表，不勾 = 不出现。已下拉列表中的默认勾选。本地下载的模型（未被下拉的）也列出供选择。
    </p>
    <div style="display:flex;gap:6px;align-items:center;margin-bottom:8px;">
      <button class="btn" onclick="addModelsSelectAll()" style="padding:3px 10px;font-size:0.78rem;">✅ 全选</button>
      <button class="btn" onclick="addModelsSelectNone()" style="padding:3px 10px;font-size:0.78rem;background:#5a5a5a;border-color:#7a7a7a;">⛔ 全不选</button>
      <button class="btn" onclick="addModelsSelectInvert()" style="padding:3px 10px;font-size:0.78rem;">🔄 反选</button>
      <span id="add-models-count" style="margin-left:auto;font-size:0.78rem;color:var(--text-dim);"></span>
    </div>
    <div id="add-models-list" style="flex:1;overflow-y:auto;background:#1a2a3a;padding:8px 12px;border-radius:4px;font-size:0.88rem;min-height:200px;">
      <div style="color:var(--text-dim);padding:6px 0;">扫描中…</div>
    </div>
    <div class="form-group" style="justify-content:flex-end;gap:8px;margin:12px 0 0;">
      <button class="btn" onclick="cancelAddModels()" style="background:#5a5a5a;border-color:#7a7a7a;">取消</button>
      <button class="btn success" onclick="confirmAddModels()" id="btn-confirm-add-models">✅ 确定</button>
    </div>
  </div>
</div>
<div class="card">
<h2>🎯 模型 & 参数</h2>
<div style="background:#1a2a3a;padding:8px 12px;border-radius:4px;margin-bottom:10px;font-size:0.78rem;color:var(--text-dim);line-height:1.7;">
  <div>📂 <b>ollama / beellama</b>（共用）: <code>/data/ollama/models/blobs/</code> → 放完点 <b>➕ 添加/移除模型进列表</b> 自动注册</div>
  <div>📂 <b>comfyui</b>: <code>/data/ComfyUI/models/</code>（<code>checkpoints/loras/diffusion_models/</code> 等子目录）</div>
</div>
<div class="form-row">
<div class="form-group"><label>模型</label><select id="model-select" style="min-width:380px"><option value="">— 加载模型到当前框架 —</option></select></div>
<button class="btn primary" onclick="loadModel()" id="btn-load-model">📥 加载模型</button>
<button class="btn" onclick="addModelsToList()" id="btn-add-models" title="弹窗列出本地所有模型, 勾选 = 加入下拉列表, 不勾 = 移出下拉列表" style="background:#2a5a2a;border-color:#3a7a3a;">➕ 添加/移除模型进列表</button>
</div>
<!-- 加载状态指示器 -->
<div id="load-status-area" style="margin-top:10px;display:none;">
  <div style="display:flex;align-items:center;gap:10px;background:#1a2a3a;border:1px solid #2d5a8a;border-radius:6px;padding:10px 14px;">
    <div class="spin" id="load-spinner"></div>
    <div style="flex:1;min-width:0;">
      <div id="load-status-message" style="font-size:0.85rem;color:var(--accent);font-weight:500;">正在加载...</div>
      <div id="load-status-time" style="font-size:0.72rem;color:var(--text-dim);margin-top:2px;"></div>
    </div>
    <div style="text-align:right;min-width:40px;">
      <span id="load-status-progress-text" style="font-size:0.9rem;font-weight:600;color:var(--accent);">5%</span>
    </div>
  </div>
  <div class="vram-bar" style="margin-top:0;border-radius:0 0 6px 6px;border:1px solid #2d5a8a;border-top:none;">
    <div id="load-progress-bar" class="vram-fill" style="width:5%;background:var(--accent);border-radius:0 0 6px 6px;"></div>
  </div>
</div>
<p style="font-size:0.75rem;color:var(--text-dim);margin-top:8px">💡 切换框架时模型列表会自动更新</p>
</div>
<div class="card">
<h2>🔍 VRAM 显存监测</h2>
<div style="margin-bottom:12px;">
  <div style="display:flex;justify-content:space-between;font-size:0.85rem;color:var(--text-dim);margin-bottom:6px;">
    <span>GPU 显存使用</span>
    <span id="vram-pct-text">--</span>
  </div>
  <div style="background:#2a2a35;border-radius:4px;height:14px;overflow:hidden;">
    <div id="vram-bar" style="background:linear-gradient(90deg,#4ade80,#fbbf24,#ef4444);height:100%;width:0%;transition:width 0.5s;"></div>
  </div>
  <div style="font-size:0.75rem;color:var(--text-dim);margin-top:6px;" id="vram-detail">--</div>
</div>
<div style="font-size:0.85rem;color:var(--text-dim);margin-bottom:8px;">🟢 显存中的模型</div>
<div id="vram-models" style="display:flex;flex-direction:column;gap:8px;">
  <div style="color:var(--text-dim);font-style:italic;">加载中…</div>
</div>
<div style="font-size:0.7rem;color:var(--text-dim);margin-top:10px;text-align:right;" id="vram-age">--</div>
</div>
<div class="card">
<h2>📋 活跃任务 <span id="active-task-count" style="font-size:0.75rem;color:var(--text-dim);font-weight:normal;">(0)</span></h2>
<div id="active-tasks" style="display:flex;flex-direction:column;gap:8px;">
<div style="color:var(--text-dim);font-style:italic;">加载中…</div>
</div>
<div style="font-size:0.7rem;color:var(--text-dim);margin-top:10px;">
💡 Skill 启动 GPU 任务前调 <code>POST /api/task_register</code>, 完成后 <code>POST /api/task_done</code>
</div>
</div>
<div class="card">
<h2>⚙️ 默认设置</h2>
<div class="form-row">
<div class="form-group">
<label>默认框架</label>
<select id="default-framework-select" style="min-width:150px;">
<option value="ollama">Ollama</option>
<option value="beellama">beellama</option>
<option value="comfyui">ComfyUI</option>
</select>
</div>
<div class="form-group">
<label>默认模型</label>
<select id="default-model-select" style="min-width:200px;">
<option value="">(无)</option>
</select>
</div>
<div class="form-group">
<label>空闲超时 (秒)</label>
<input type="number" id="idle-timeout-input" min="0" max="3600" step="60" style="width:100px;" value="300">
</div>
<button class="btn primary" onclick="saveDefaultSettings()">💾 保存设置</button>
<button class="btn" onclick="loadDefaultSettings()">🔄 加载当前</button>
</div>
<p style="font-size:0.75rem;color:var(--text-dim);margin-top:8px;">
💡 空闲超时后自动切换到默认框架和模型。设为 0 禁用自动回退。
</p>
</div>
<div style="background:#1a2a3a;padding:8px 12px;border-radius:4px;margin-bottom:10px;font-size:0.85rem;">
  <div style="color:var(--orange);font-size:0.82rem;margin-bottom:6px;">🗑 隐藏的模型（点 ↩️ 恢复显示）</div>
  <div id="hidden-models-list" style="font-size:0.85rem;">
    <div style="color:var(--text-dim);">加载中…</div>
  </div>
</div>
</div>
<div class="card">
<h2>📝 操作日志</h2>
<div id="log-area">就绪。</div>
</div>
<div class="footer">
<span>framework-manager v1.5.1 · :{{ port }}</span>
<a href="/api/health" style="color:#484;text-decoration:none;font-size:0.65rem">/api/health</a>
</div>
</div>
<script>
var currentFramework = null;
var currentModel = null;
var saveInProgress = false;  // 保存/重置模型参数期间为 true, 防止卡片被 refresh() 隐藏
var isSwitching = false;
// 缓存默认值文件的内存副本, 编辑期间与后端脱联
var defaultsCache = { _fallback: {ctx_size:131072, parallel:2, ngpu_layers:99}, models: {} };
async function fetchJSON(url, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  try {
    const resp = await fetch(url, opts);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    return await resp.json();
  } catch (e) {
    throw e;
  }
}
async function refresh() {
  try {
    const data = await fetchJSON('/api/status');
    document.getElementById('sv-framework').textContent = data.framework_key || '—';
    const fw = data.framework_key;
    if (fw === 'ollama') document.getElementById('sv-framework').style.color = 'var(--accent)';
    else if (fw === 'beellama') document.getElementById('sv-framework').style.color = 'var(--orange)';
    else if (fw === 'comfyui') document.getElementById('sv-framework').style.color = 'var(--green)';
    else document.getElementById('sv-framework').style.color = 'var(--text-dim)';
    document.getElementById('sv-pid').textContent = data.pid || '—';
    document.getElementById('sv-model').textContent = data.model || '—';
    // ⚙️ 同步 JS 全局 currentFramework + currentModel, 供下游按钮用
    // v1.1.7-patch4: 同步 currentFramework (之前遗漏, 导致 addModelsToList/removeModelFromList 报"未加载框架")
    if (fw && fw !== '—' && fw !== '\u2014') {
      currentFramework = fw;
    } else {
      currentFramework = null;
    }
    if (data.model && data.model !== '—' && data.model !== '\u2014') {
      // v1.1.7-patch7: 检测到 currentModel 变化时重新渲染「默认值」卡片
      // 之前: 加载不同模型后 defaults 卡片不刷新, 仍显示旧模型
      if (data.model !== currentModel) {
        currentModel = data.model;
        if (typeof renderDefaults === 'function') renderDefaults();
      }
    } else {
      if (currentModel !== null) {
        currentModel = null;
        if (typeof renderDefaults === 'function') renderDefaults();
      }
    }
    document.getElementById('sv-vram').textContent = (data.vram_used_mb/1024).toFixed(0) + ' / ' + (data.vram_total_mb/1024).toFixed(0) + ' GB (' + data.vram_percent + '%)';
    const bar = document.getElementById('vram-bar');
    bar.style.width = data.vram_percent + '%';
    bar.className = 'vram-fill ' + (data.vram_percent < 50 ? 'low' : data.vram_percent < 80 ? 'med' : 'high');
    ['ollama','beellama','comfyui'].forEach(function(f) {
      var btn = document.getElementById('btn-' + f);
      if (btn) btn.disabled = (isSwitching || fw === f);
    });
    // ⚙️ 显示/隐藏 beellama 参数卡片
    var paramsCard = document.getElementById('beellama-params-card');
    if (paramsCard) {
      if (fw === 'beellama') {
        paramsCard.style.display = 'block';
        loadBeellamaParams();
      } else {
        paramsCard.style.display = 'none';
      }
    }
    // ⚙️ 显示/隐藏 comfyui 参数卡片 (v1.1.8)
    var comfyuiParamsCard = document.getElementById('comfyui-params-card');
    var comfyuiPathsCard = document.getElementById('comfyui-paths-card');
    if (comfyuiParamsCard && comfyuiPathsCard) {
      if (fw === 'comfyui') {
        comfyuiParamsCard.style.display = 'block';
        comfyuiPathsCard.style.display = 'block';
        loadComfyuiParams();
        loadComfyuiPaths();
      } else {
        comfyuiParamsCard.style.display = 'none';
        comfyuiPathsCard.style.display = 'none';
      }
    }
    // 🎯 默认值卡片 (通用, beellama 专用) — ollama/comfyui 时隐藏
    var defaultsCard = document.getElementById('defaults-card');
    var ingestBeellamaCard = document.getElementById('ingest-beellama-card');  // v1.6.2
    if (defaultsCard) {
      if (fw === 'beellama') {
        defaultsCard.style.display = 'block';
        if (ingestBeellamaCard) ingestBeellamaCard.style.display = 'block';
      } else {
        defaultsCard.style.display = 'none';
        if (ingestBeellamaCard) ingestBeellamaCard.style.display = 'none';
      }
    }
    // ⚙️ 显示/隐藏 ollama 参数卡片 (v1.1.8-patch2)
    var ollamaParamsCard = document.getElementById('ollama-params-card');
    var ollamaModelParamsCard = document.getElementById('ollama-model-params-card');
    var ollamaDefaultsCard = document.getElementById('ollama-defaults-card');
    var manifestGenParamsCard = document.getElementById('manifest-gen-params-card');  // v1.1.17
    var ingestGgufCard = document.getElementById('ingest-gguf-card');  // v1.1.18
    if (ollamaParamsCard) {
      if (fw === 'ollama') {
        ollamaParamsCard.style.display = 'block';
        ollamaDefaultsCard.style.display = 'block';
        if (manifestGenParamsCard) {
          manifestGenParamsCard.style.display = 'block';
          loadManifestGenParams();
        }
        if (ingestGgufCard) ingestGgufCard.style.display = 'block';
        loadOllamaGlobalParams();
        loadOllamaDefaults();
      } else {
        ollamaParamsCard.style.display = 'none';
        ollamaDefaultsCard.style.display = 'none';
        if (manifestGenParamsCard) manifestGenParamsCard.style.display = 'none';
        if (ingestGgufCard) ingestGgufCard.style.display = 'none';
      }
    }
    if (ollamaModelParamsCard) {
      if (fw === 'ollama' && currentModel) {
        ollamaModelParamsCard.style.display = 'block';
        loadOllamaModelParams();
      } else {
        ollamaModelParamsCard.style.display = 'none';
      }
    }
    // 📦 模型专属参数卡片：仅当加载了 beellama 模型时显示（保存中保持可见）
    var modelParamsCard = document.getElementById('beellama-model-params-card');
    if (modelParamsCard) {
      if (fw === 'beellama' && currentModel) {
        modelParamsCard.style.display = 'block';
        loadModelParams();
      } else if (!saveInProgress) {
        // 保存/重置中保持卡片可见，避免视觉断点
        modelParamsCard.style.display = 'none';
      }
    }
    // 原"队列情况"已被 v1.3.0 的 VRAM 实时监测取代
    // VRAM 刷新逻辑见 refreshVram() 函数 + setInterval 每 5s 调用
    if (typeof refreshVram === 'function') refreshVram();
    // 状态轮询不写日志，避免刷屏
    updateModelSelect(data.available_models, data.available_display_names);
  } catch (e) {
    log('刷新失败：' + e.message, 'error');
  }
}

// v1.3.0: VRAM Dashboard 刷新逻辑（独立函数, 被 refresh() 调用 + setInterval 每 5s 调用）
const VRAM_STATE_COLORS = {
  'processing': '#fbbf24',
  'running': '#fbbf24',
  'queued': '#60a5fa',
  'loaded': '#4ade80',
  'idle': '#4ade80',
  'unknown': '#888',
};
const VRAM_FW_ICONS = {
  'ollama': '🦙',
  'beellama': '🐝',
  'comfyui': '🎨',
  'unknown': '❓',
};
function vramColorFor(pct) {
  if (pct < 60) return '#4ade80';
  if (pct < 85) return '#fbbf24';
  return '#ef4444';
}
async function refreshVram() {
  try {
    const r = await fetch('/api/vram_status');
    if (!r.ok) return;
    const d = await r.json();
    // 进度条 + 文本
    const pct = d.gpu_used_pct || 0;
    const bar = document.getElementById('vram-bar');
    if (bar) {
      bar.style.width = pct + '%';
      bar.style.background = vramColorFor(pct);
    }
    const pctText = document.getElementById('vram-pct-text');
    if (pctText) {
      pctText.textContent = pct + '% (' + d.gpu_used_mb + ' / ' + d.gpu_total_mb + ' MB)';
      pctText.style.color = vramColorFor(pct);
    }
    const detail = document.getElementById('vram-detail');
    if (detail) {
      detail.textContent = 'GPU 利用率: ' + d.gpu_util_pct + '% · 活跃框架: ' + (d.active_fw || 'none') + (d.active_model ? ' / ' + d.active_model : '');
    }
    // 模型列表
    const list = document.getElementById('vram-models');
    if (list) {
      if (d.error) {
        list.innerHTML = '<div style="color:#ef4444;">⚠️ ' + d.error + '</div>';
      } else if (!d.models || d.models.length === 0) {
        list.innerHTML = '<div style="color:var(--text-dim);font-style:italic;">GPU 空闲</div>';
      } else {
        list.innerHTML = d.models.map(m => {
          const color = VRAM_STATE_COLORS[m.task_state] || '#888';
          const icon = VRAM_FW_ICONS[m.framework] || '❓';
          const modelShort = (m.model || m.process).split('/').pop().slice(0, 40);
          return '<div style="background:#2a2a35;border-radius:4px;padding:6px 8px;border-left:3px solid ' + color + ';">' +
            '<div style="display:flex;justify-content:space-between;align-items:center;">' +
              '<span style="font-weight:500;">' + icon + ' ' + (m.framework || 'unknown') + '</span>' +
              '<span style="font-size:10px;color:#888;">' + m.used_mb + ' MB</span>' +
            '</div>' +
            '<div style="font-size:11px;color:#bbb;margin-top:2px;word-break:break-all;">' + modelShort + '</div>' +
            '<div style="font-size:10px;color:var(--text-dim);margin-top:2px;">PID ' + m.pid + ' · <span style="color:' + color + ';">●</span> ' + (m.task_state || 'unknown') + (m.task_info ? ' · ' + m.task_info : '') + '</div>' +
          '</div>';
        }).join('');
      }
    }
    const age = document.getElementById('vram-age');
    if (age) {
      age.textContent = d.age_sec != null ? ('更新于 ' + d.age_sec + ' 秒前 · 每 5s 自动刷新') : '更新中…';
    }
    // v1.4.0: 活跃任务列表渲染
    const taskList = document.getElementById('active-tasks');
    const taskCount = document.getElementById('active-task-count');
    const tasks = d.tasks || [];
    if (taskCount) {
      taskCount.textContent = '(' + tasks.length + ')';
    }
    if (taskList) {
      if (tasks.length === 0) {
        taskList.innerHTML = '<div style="color:var(--text-dim);font-style:italic;">无活跃任务</div>';
      } else {
        taskList.innerHTML = tasks.map(t => {
          const fwIcon = VRAM_FW_ICONS[t.framework] || '❓';
          const estTxt = t.estimated_duration_sec ? (' / 预计 ' + t.estimated_duration_sec + 's') : '';
          const progressPct = t.estimated_duration_sec ? Math.min(100, Math.round(t.duration_sec * 100 / t.estimated_duration_sec)) : 0;
          const progressBar = t.estimated_duration_sec ? (
            '<div style="background:#2a2a35;border-radius:3px;height:4px;overflow:hidden;margin-top:4px;">' +
              '<div style="background:' + (progressPct < 80 ? '#4ade80' : '#fbbf24') + ';height:100%;width:' + progressPct + '%;transition:width 1s;"></div>' +
            '</div>'
          ) : '';
          const metaTxt = t.metadata && Object.keys(t.metadata).length > 0 ?
            '<div style="font-size:10px;color:#666;margin-top:3px;">' + JSON.stringify(t.metadata) + '</div>' : '';
          // v1.5.0: 自动检测标记
          const autoBadge = t.auto_detect ? 
            '<span title="框架原生信号自动检测 (ComfyUI history / Ollama /api/ps)" style="background:#4f46e5;color:#fff;font-size:9px;padding:1px 5px;border-radius:3px;margin-left:6px;">🤖 自动检测</span>' : '';
          return '<div style="background:#2a2a35;border-radius:4px;padding:8px 10px;border-left:3px solid #fbbf24;">' +
            '<div style="display:flex;justify-content:space-between;align-items:center;">' +
              '<span style="font-weight:500;">' + fwIcon + ' ' + (t.framework || 'unknown') + autoBadge + '</span>' +
              '<span style="font-size:10px;color:#888;">● ' + t.state + '</span>' +
            '</div>' +
            '<div style="font-size:12px;color:#bbb;margin-top:3px;">' + (t.model || 'unknown') + '</div>' +
            '<div style="font-size:11px;color:#888;margin-top:3px;">' +
              '⏱️ ' + t.duration_sec + 's' + estTxt +
              ' · 来源: ' + t.source +
            '</div>' +
            progressBar + metaTxt +
          '</div>';
        }).join('');
      }
    }
  } catch (e) {
    console.error('refreshVram error:', e);
  }
}
// 首次加载 + 每 5s 刷新
refreshVram();
setInterval(refreshVram, 5000);
function updateModelSelect(models, displayNames) {
  // v1.6.2-patch4: displayNames 由后端 _extract_short_model_name 提供 (beellama)
  // 主下拉仍显示完整路径 (与历史一致), 但顺便同步到「默认设置」下拉
  var sel = document.getElementById('model-select');
  var prevValue = sel.value;  // 保存用户当前选中的值
  sel.innerHTML = '<option value="">— 加载模型到当前框架 —</option>';
  models.forEach(function(m, i) {
    var opt = document.createElement('option');
    opt.value = m;
    opt.textContent = m + '  🗑';
    opt.dataset.modelPath = m;
    opt.dataset.shortName = (displayNames && displayNames[i]) || '';
    sel.appendChild(opt);
  });
  // 恢复之前选中的值（如果新列表里还有的话）
  if (prevValue) {
    sel.value = prevValue;
  }
  // 同步隐藏区状态
  loadHiddenModels();
  // v1.6.2-patch4: 同步「默认设置」下拉, 复用同一份数据 (避免两处维护)
  syncDefaultModelSelect(models, displayNames || []);
}

// v1.1.7-patch5: removeModelFromList 函数已删除 (功能被「➕ 添加/移除模型」模态框覆盖)
//   移除 = 模态框里取消勾选即可
//   保留: /api/hide_model 后端端点 (API 保留, 不影响其他功能)
//   保留: 「⚙️ 默认设置」卡片的「🗑 隐藏的模型」区 + ↩️ 恢复按钮 (兜底恢复路径)

// v1.1.7-patch3: 「➕ 添加模型进列表」= 弹模态框 + 复选框选择
let _addModelsAll = [];
let _addModelsVisible = [];

async function addModelsToList() {
  if (!currentFramework) {
    showToast('未加载框架', 'error');
    return;
  }
  const btn = document.getElementById('btn-add-models');
  btn.disabled = true;
  btn.textContent = '⏳ 扫描中...';
  try {
    const resp = await fetchJSON('/api/scan_for_addition?framework=' + encodeURIComponent(currentFramework));
    _addModelsAll = resp.all || [];
    _addModelsVisible = resp.visible || [];

    // v1.1.15: ollama 框架下, 扫描后检查未注册 GGUF → 弹进度遮罩 → 自动注册
    if (currentFramework === 'ollama') {
      let regResult = null;
      try {
        showLoadStatus(true);
        updateLoadStatusUI({ status: 'loading', message: '检查未注册 GGUF...', progress: 30, elapsed_seconds: 0 });
        regResult = await fetchJSON('/api/auto_register_gguf', 'POST', {});
        if (regResult.registered && regResult.registered.length > 0) {
          updateLoadStatusUI({ status: 'loading', message: '注册 ' + regResult.registered.length + ' 个 GGUF...', progress: 70, elapsed_seconds: 1 });
          // 重新扫描
          const resp2 = await fetchJSON('/api/scan_for_addition?framework=' + encodeURIComponent(currentFramework));
          _addModelsAll = resp2.all || [];
          _addModelsVisible = resp2.visible || [];
          updateLoadStatusUI({ status: 'done', message: '✅ 已注册: ' + regResult.registered.join(', '), progress: 100, elapsed_seconds: 2 });
          showToast('✅ 自动注册 ' + regResult.registered.length + ' 个模型: ' + regResult.registered.join(', '), 'success', 5000);
          setTimeout(function() { showLoadStatus(false); }, 3000);
        } else {
          showLoadStatus(false);
        }
        if (regResult.errors && regResult.errors.length > 0) {
          showToast('⚠️ 部分注册失败: ' + regResult.errors.join('; '), 'error', 8000);
        }
      } catch (e) {
        updateLoadStatusUI({ status: 'error', message: '自动注册失败: ' + e.message, progress: 100, elapsed_seconds: 0 });
        setTimeout(function() { showLoadStatus(false); }, 5000);
        showToast('自动注册失败: ' + e.message, 'error');
      }
    }

    document.getElementById('add-models-modal-fw').textContent = currentFramework;
    renderAddModelsList();
    document.getElementById('add-models-modal').style.display = 'flex';
  } catch (e) {
    showToast('扫描失败: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '➕ 添加模型进列表';
  }
}

function renderAddModelsList() {
  const el = document.getElementById('add-models-list');
  const countEl = document.getElementById('add-models-count');
  if (!_addModelsAll || _addModelsAll.length === 0) {
    el.innerHTML = '<div style="color:var(--orange);padding:6px 0;">⚠️ 本地未发现模型, 请检查默认位置/扫描路径。</div>';
    countEl.textContent = '';
    return;
  }
  let html = '';
  for (const m of _addModelsAll) {
    const checked = _addModelsVisible.includes(m);
    html += '<label style="display:flex;align-items:center;gap:8px;padding:5px 4px;border-bottom:1px solid #2a3a4a;cursor:pointer;">'
          + '<input type="checkbox" class="add-model-cb" data-model="' + escapeHtml(m) + '" ' + (checked ? 'checked' : '') + ' style="cursor:pointer;">'
          + '<span style="flex:1;font-family:monospace;font-size:0.85rem;">' + escapeHtml(m) + '</span>'
          + '</label>';
  }
  el.innerHTML = html;
  const checkedCount = el.querySelectorAll('.add-model-cb:checked').length;
  countEl.textContent = '共 ' + _addModelsAll.length + ' 个, 已选 ' + checkedCount + ' 个';
  el.querySelectorAll('.add-model-cb').forEach(cb => {
    cb.addEventListener('change', () => {
      const c = el.querySelectorAll('.add-model-cb:checked').length;
      countEl.textContent = '共 ' + _addModelsAll.length + ' 个, 已选 ' + c + ' 个';
    });
  });
}

function addModelsSelectAll() {
  document.querySelectorAll('.add-model-cb').forEach(cb => cb.checked = true);
  document.getElementById('add-models-count').textContent = '共 ' + _addModelsAll.length + ' 个, 已选 ' + _addModelsAll.length + ' 个';
}

function addModelsSelectNone() {
  document.querySelectorAll('.add-model-cb').forEach(cb => cb.checked = false);
  document.getElementById('add-models-count').textContent = '共 ' + _addModelsAll.length + ' 个, 已选 0 个';
}

function addModelsSelectInvert() {
  document.querySelectorAll('.add-model-cb').forEach(cb => cb.checked = !cb.checked);
  const c = document.querySelectorAll('.add-model-cb:checked').length;
  document.getElementById('add-models-count').textContent = '共 ' + _addModelsAll.length + ' 个, 已选 ' + c + ' 个';
}

function cancelAddModels() {
  document.getElementById('add-models-modal').style.display = 'none';
  _addModelsAll = [];
  _addModelsVisible = [];
}

async function confirmAddModels() {
  const visible = Array.from(document.querySelectorAll('.add-model-cb:checked')).map(cb => cb.getAttribute('data-model'));
  const btn = document.getElementById('btn-confirm-add-models');
  btn.disabled = true;
  btn.textContent = '⏳ 保存中...';
  try {
    const resp = await fetchJSON('/api/set_visible_models', 'POST', {
      framework: currentFramework,
      visible: visible
    });
    showToast('✅ 已更新: ' + resp.visible.length + ' 个可见, ' + resp.hidden.length + ' 个隐藏', 'success', 5000);
    document.getElementById('add-models-modal').style.display = 'none';
    if (typeof updateModelsForCurrentFramework === 'function') {
      updateModelsForCurrentFramework(true);
    } else {
      var r = await fetchJSON('/api/models_by_framework?framework=' + encodeURIComponent(currentFramework));
      updateModelSelect(r.models || []);
    }
    loadHiddenModels();
    _addModelsAll = [];
    _addModelsVisible = [];
  } catch (e) {
    showToast('保存失败: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '✅ 确定';
  }
}

async function loadHiddenModels() {
  try {
    const data = await fetchJSON('/api/hidden_models');
    const el = document.getElementById('hidden-models-list');
    let total = (data.beellama || []).length + (data.ollama || []).length + (data.comfyui || []).length;
    if (total === 0) {
      el.innerHTML = '<div style="color:var(--text-dim);padding:4px 0;">无隐藏模型</div>';
      return;
    }
    let html = '';
    for (const fw of ['beellama', 'ollama', 'comfyui']) {
      const items = data[fw] || [];
      if (items.length === 0) continue;
      html += '<div style="margin-top:6px;"><b style="color:var(--accent);">' + fw + '</b> (' + items.length + '):</div>';
      for (const m of items) {
        html += '<div style="display:flex;align-items:center;gap:6px;padding:2px 0 2px 16px;">'
              + '<span style="flex:1;font-family:monospace;font-size:0.8rem;">' + escapeHtml(m) + '</span>'
              + '<button class="btn" onclick="unhideModel(\'' + fw + '\', \'' + escapeHtml(m).replace(/'/g, "\\'") + '\')" style="padding:2px 8px;font-size:0.75rem;background:#2a5a2a;border-color:#3a7a3a;">↩️ 恢复</button>'
              + '</div>';
      }
    }
    el.innerHTML = html;
  } catch (e) {
    console.error('加载隐藏列表失败:', e);
  }
}

async function unhideModel(framework, model) {
  if (!confirm(`恢复显示「${model}」?`)) return;
  try {
    await fetchJSON('/api/unhide_model', 'POST', { framework, model });
    showToast('✅ 已恢复「' + model + '」', 'success', 3000);
    if (currentFramework === framework) {
      var r = await fetchJSON('/api/models_by_framework?framework=' + encodeURIComponent(framework));
      updateModelSelect(r.models || []);
    }
    loadHiddenModels();
  } catch (e) {
    showToast('恢复失败: ' + e.message, 'error');
  }
}

function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
async function switchFramework(fw) {
  if (isSwitching) return;
  isSwitching = true;
  log('切换到框架：' + fw);
  stopLoadStatusPoll();
  showLoadStatus(false);
  try {
    var resp = await fetchJSON('/api/set_framework', 'POST', { framework: fw });
    if (resp.status === 'ok') {
      showToast('已切换到 ' + fw, 'success');
      refresh();
    } else {
      showToast('切换失败：' + (resp.error || '未知错误'), 'error');
    }
  } catch (e) {
    showToast('请求失败：' + e.message, 'error');
  } finally {
    isSwitching = false;
  }
}
async function stopAllEngines() {
  if (isSwitching) return;
  if (!confirm('确定要停止所有框架吗？')) return;
  isSwitching = true;
  log('正在停止所有框架...');
  // 清理加载状态
  stopLoadStatusPoll();
  showLoadStatus(false);
  try {
    var resp = await fetchJSON('/api/stop_all', 'POST');
    if (resp.status === 'ok') {
      showToast('已停止：' + (resp.stopped || []).join(', '), 'success');
      refresh();
    } else {
      showToast('停止失败', 'error');
    }
  } catch (e) {
    showToast('请求失败：' + e.message, 'error');
  } finally {
    isSwitching = false;
  }
}
// ── 模型加载状态轮询 ──────────────────────────────────────
var loadStatusTimer = null;

function showLoadStatus(show) {
  var area = document.getElementById('load-status-area');
  var btn = document.getElementById('btn-load-model');
  var sel = document.getElementById('model-select');
  if (area) area.style.display = show ? 'block' : 'none';
  if (btn) btn.disabled = show;
  if (sel) sel.disabled = show;
}

function updateLoadStatusUI(status) {
  var msgEl = document.getElementById('load-status-message');
  var timeEl = document.getElementById('load-status-time');
  var progText = document.getElementById('load-status-progress-text');
  var progBar = document.getElementById('load-progress-bar');
  var spinner = document.getElementById('load-spinner');
  if (!msgEl) return;

  msgEl.textContent = status.message || '加载中...';
  var pct = Math.min(100, Math.max(0, status.progress || 0));
  if (progText) progText.textContent = pct + '%';
  if (progBar) progBar.style.width = pct + '%';
  if (timeEl) timeEl.textContent = '已用 ' + (status.elapsed_seconds || 0) + 's';

  if (status.status === 'loading') {
    if (spinner) spinner.style.display = '';
    msgEl.style.color = 'var(--accent)';
    if (progBar) progBar.style.background = 'var(--accent)';
  } else if (status.status === 'done') {
    if (spinner) spinner.style.display = 'none';
    msgEl.style.color = 'var(--green)';
    if (progBar) { progBar.style.width = '100%'; progBar.style.background = 'var(--green)'; }
  } else if (status.status === 'error') {
    if (spinner) spinner.style.display = 'none';
    msgEl.style.color = 'var(--red)';
    if (progBar) progBar.style.background = 'var(--red)';
  }
}

function stopLoadStatusPoll() {
  if (loadStatusTimer) {
    clearInterval(loadStatusTimer);
    loadStatusTimer = null;
  }
}

async function pollLoadStatus() {
  try {
    var status = await fetchJSON('/api/load_status');
    updateLoadStatusUI(status);
    if (status.status === 'done' || status.status === 'error') {
      stopLoadStatusPoll();
      if (status.status === 'done') {
        showToast(status.message || '模型已加载', 'success');
      } else {
        showToast(status.message || '加载失败', 'error');
      }
      refresh();
      setTimeout(function() {
        showLoadStatus(false);
        stopLoadStatusPoll();
      }, 5000);
    }
  } catch (e) {
    log('加载状态轮询失败：' + e.message, 'error');
  }
}

async function loadModel() {
  var sel = document.getElementById('model-select');
  var model = sel.value;
  if (!model) { showToast('请先选择模型', 'info'); return; }

  showLoadStatus(true);
  updateLoadStatusUI({ status: 'loading', message: '正在使用 ' + document.getElementById('sv-framework').textContent + ' 加载 ' + model + ' 中...', progress: 5, elapsed_seconds: 0 });
  log('加载模型：' + model);

  stopLoadStatusPoll();
  loadStatusTimer = setInterval(pollLoadStatus, 2000);

  try {
    var resp = await fetchJSON('/api/load_model', 'POST', { model: model });
    // v1.1.5: 处理 missing_in_defaults: 弹模态框让用户确认是否用 _fallback 初始化
    if (resp && resp.missing_in_defaults) {
      stopLoadStatusPoll();
      showLoadStatus(false);
      showInitModelModal(model, resp.short_name, resp.error);
      return;
    }
  } catch (e) {
    stopLoadStatusPoll();
    showLoadStatus(false);
    showToast('请求失败：' + e.message, 'error');
    log('加载请求失败：' + e.message, 'error');
  }
}

// ── 默认设置：框架切换时刷新模型列表 ──────────────────────
document.addEventListener('DOMContentLoaded', function() {
  var fwSelect = document.getElementById('default-framework-select');
  fwSelect.addEventListener('change', function() {
    // v1.6.2-patch4: 根据默认框架加载对应下拉
    // - 默认框架 == 当前框架: 复用主下拉 (避免两处维护)
    // - 默认框架 != 当前框架: 独立拉 (覆盖 "空闲后回退到其他框架" 场景)
    var newFw = this.value;
    window.currentDefaultModel = '';
    if (newFw === currentFramework) {
      // 复用主下拉: 只清选中, 等待 updateModelSelect 同步
      var sel = document.getElementById('default-model-select');
      if (sel) sel.value = '';
      log('已切换默认框架: ' + newFw + ' (复用主下拉)', 'info');
    } else {
      // 独立拉
      fetchJSON('/api/models_by_framework?framework=' + encodeURIComponent(newFw))
        .then(function(r) {
          syncDefaultModelSelect(r.models || [], r.display_names || [], '');
          log('已加载默认框架 ' + newFw + ' 的模型列表 (独立拉)', 'info');
        })
        .catch(function(e) {
          log('获取默认框架模型列表失败：' + e.message, 'error');
        });
    }
  });
  // 页面加载时自动加载默认设置
  loadDefaultSettings();
});

// ── 默认设置管理 ──────────────────────────────────────────────
async function loadDefaultSettings() {
  log('加载默认设置...');
  try {
    var resp = await fetchJSON('/api/default_config');
    var config = resp.config || resp;
    var defaultFw = config.default_framework || 'beellama';
    document.getElementById('default-framework-select').value = defaultFw;
    document.getElementById('idle-timeout-input').value = config.idle_timeout || 300;
    // v1.6.2-patch4: 复用主下拉数据 (仅当默认框架 == 当前框架, 避免主下拉下拉不同步)
    window.currentDefaultModel = config.default_model || '';
    if (defaultFw === currentFramework) {
      // 复用主下拉 (由 updateModelSelect 同步), 只更新选中
      var sel = document.getElementById('default-model-select');
      if (sel && window.currentDefaultModel) sel.value = window.currentDefaultModel;
    } else {
      // 默认框架 != 当前框架, 独立拉 (覆盖如 "现在用 beellama, 空闲后回退到 ollama" 场景)
      var modelsResp = await fetchJSON('/api/models_by_framework?framework=' + encodeURIComponent(defaultFw));
      syncDefaultModelSelect(modelsResp.models || [], modelsResp.display_names || [], config.default_model || '');
    }

    log('默认设置已加载：框架=' + defaultFw + ' 模型=' + (config.default_model||'无') + ' 超时=' + (config.idle_timeout||300) + 's');
  } catch (e) {
    log('加载设置失败：' + e.message, 'error');
  }
  // v1.1.4: 加载「🎯 默认值」卡片
  loadDefaults();
}

function updateDefaultModelSelect(models, displayNames, selectedModel) {
  // v1.6.2-patch3: displayNames 由后端 _extract_short_model_name 提供
  // v1.6.2-patch4: 该函数已废弃, 逻辑被 syncDefaultModelSelect 替代 (复用主下拉数据)
  // 保留为勾子函数防止被使用, 内部走 syncDefaultModelSelect
  syncDefaultModelSelect(models, displayNames, selectedModel);
}

// v1.6.2-patch4: 「默认模型」下拉从主下拉同步, 不再独立拉 API
function syncDefaultModelSelect(models, displayNames, selectedModel) {
  // 入参: models=主下拉可用模型列表, displayNames=后端给的 short_name
  // 如果 selectedModel 未传, 从主下拉当前选中读 (保留用户选择)
  var sel = document.getElementById('default-model-select');
  if (!sel) return;
  sel.innerHTML = '<option value="">(无)</option>';
  (models || []).forEach(function(m, i) {
    var opt = document.createElement('option');
    opt.value = m;
    opt.textContent = (displayNames && displayNames[i]) || m;
    sel.appendChild(opt);
  });
  // 恢复选中: 优先用 selectedModel 参数, 其次读全局 currentDefaultModel
  if (selectedModel === undefined) {
    selectedModel = window.currentDefaultModel || '';
  } else {
    window.currentDefaultModel = selectedModel;
  }
  if (selectedModel) {
    sel.value = selectedModel;
  }
}

async function saveDefaultSettings() {
  var fw = document.getElementById('default-framework-select').value;
  var model = document.getElementById('default-model-select').value;
  var timeout = parseInt(document.getElementById('idle-timeout-input').value) || 300;
  
  log('保存默认设置：框架=' + fw + ' 模型=' + (model||'无') + ' 超时=' + timeout + 's');
  
  try {
    var resp = await fetchJSON('/api/set_default_config', 'POST', {
      default_framework: fw,
      default_model: model,
      idle_timeout: timeout
    });
    if (resp.status === 'ok') {
      showToast('设置已保存', 'success');
      log('设置保存成功');
      refresh();
    } else {
      showToast('保存失败：' + (resp.error || '未知错误'), 'error');
      log('保存失败：' + (resp.error || '未知错误'), 'error');
    }
  } catch (e) {
    showToast('请求失败：' + e.message, 'error');
    log('保存失败：' + e.message, 'error');
  }
}

function showToast(msg, type) {
  var t = document.createElement('div');
  t.className = 'toast ' + (type || 'info');
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(function() { t.remove(); }, 3500);
}
var logArea = document.getElementById('log-area');
function log(msg, level) {
  var ts = new Date().toLocaleTimeString();
  logArea.textContent = '[' + ts + '] ' + msg + '\n' + logArea.textContent;
  var lines = logArea.textContent.split('\n');
  if (lines.length > 100) logArea.textContent = lines.slice(0, 100).join('\n');
}

// 从后端拉取审计日志并显示（仅主要事件，不做无事件轮询显示）
var lastAuditTimestamp = '';
async function pullAuditLogs() {
  try {
    var resp = await fetch('/api/audit_logs?limit=1');
    var logs = await resp.json();
    if (logs && logs.length > 0) {
      var latest = logs[0].trim();
      if (!latest) return;
      // 与上次已显示的日志对比，相同则不追加
      if (latest === lastAuditTimestamp) return;
      // 判断是否为主要事件
      if (latest.includes('空闲回退') || latest.includes('切换框架') || latest.includes('加载模型')) {
        logArea.textContent = latest + '\n' + logArea.textContent;
        var lines = logArea.textContent.split('\n');
        if (lines.length > 100) logArea.textContent = lines.slice(0, 100).join('\n');
        lastAuditTimestamp = latest;
      }
    }
  } catch (e) {
    // 静默失败，不影响主轮询
  }
}

refresh();
setInterval(refresh, 5000);
setInterval(pullAuditLogs, 10000);

// ⚙️ 防呆：每 10 秒检查 isSwitching 是否卡住
setInterval(function() {
  if (isSwitching) {
    console.warn('⚠️ isSwitching 卡住，自动重置');
    isSwitching = false;
    // 恢复按钮
    ['ollama','beellama','comfyui'].forEach(function(f) {
      var btn = document.getElementById('btn-' + f);
      if (btn) btn.disabled = false;
    });
  }
}, 10000);

// ⚙️ beellama 参数管理
async function loadBeellamaParams() {
  try {
    const data = await fetchJSON('/api/beellama_params');
    document.getElementById('beellama-turbo-level').value = data.turbo_level || '';
    document.getElementById('beellama-flash-attn').value = (data.flash_attn ? 'true' : 'false');
    document.getElementById('beellama-reasoning-off').value = (data.reasoning_off ? 'true' : 'false');
  } catch (e) {
    console.error('加载 beellama 参数失败:', e);
  }
}

async function saveBeellamaParams() {
  const turboLevel = document.getElementById('beellama-turbo-level').value;
  const flashAttn = document.getElementById('beellama-flash-attn').value === 'true';
  const reasoningOff = document.getElementById('beellama-reasoning-off').value === 'true';

  const btn = document.getElementById('btn-save-beellama-params');
  btn.disabled = true;
  btn.textContent = '⏳ 重启中...';

  try {
    const resp = await fetchJSON('/api/beellama_params', 'POST', {
      turbo_level: turboLevel,
      flash_attn: flashAttn,
      reasoning_off: reasoningOff
    });
    if (resp.status === 'ok') {
      showToast('全局参数已保存，beellama 重启中...', 'success');
      await fetchJSON('/api/set_framework', 'POST', {framework: 'beellama'});
      setTimeout(() => {
        btn.disabled = false;
        btn.textContent = '💾 保存并重启 beellama';
        refresh();
      }, 3000);
    } else {
      showToast('保存失败：' + (resp.error || '未知错误'), 'error');
      btn.disabled = false;
      btn.textContent = '💾 保存并重启 beellama';
    }
  } catch (e) {
    showToast('保存失败：' + e.message, 'error');
    btn.disabled = false;
    btn.textContent = '💾 保存并重启 beellama';
  }
}

// ⚙️ ComfyUI 启动参数 (v1.1.8)
async function loadComfyuiParams() {
  try {
    const data = await fetchJSON('/api/comfyui_params');
    document.getElementById('comfyui-lowvram').checked = !!data.lowvram;
    document.getElementById('comfyui-gpu-only').checked = !!data.gpu_only;
    document.getElementById('comfyui-listen').checked = !!data.listen;
    document.getElementById('comfyui-preview-method').value = data.preview_method || 'auto';
  } catch (e) {
    console.error('加载 ComfyUI 参数失败:', e);
  }
}

async function saveComfyuiParams() {
  const btn = document.getElementById('btn-save-comfyui-params');
  btn.disabled = true;
  btn.textContent = '⏳ 重启中...';
  try {
    const resp = await fetchJSON('/api/comfyui_params', 'POST', {
      lowvram: document.getElementById('comfyui-lowvram').checked,
      gpu_only: document.getElementById('comfyui-gpu-only').checked,
      listen: document.getElementById('comfyui-listen').checked,
      preview_method: document.getElementById('comfyui-preview-method').value,
    });
    if (resp.status === 'ok') {
      showToast('✅ ' + (resp.message || 'ComfyUI 参数已保存并重启'), 'success', 5000);
      setTimeout(refresh, 3000);
    } else {
      showToast('保存失败：' + (resp.error || '未知错误'), 'error');
    }
  } catch (e) {
    showToast('保存失败：' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '💾 保存并重启 ComfyUI';
  }
}

// 📂 ComfyUI 模型路径 (v1.1.8)
async function loadComfyuiPaths() {
  try {
    const data = await fetchJSON('/api/comfyui_extra_paths');
    document.getElementById('comfyui-base-path').value = data.base_path || data.default_base || '';
    // custom_paths dict → textarea 格式 (key: path 一行一条)
    const lines = [];
    for (const [k, v] of Object.entries(data.custom_paths || {})) {
      lines.push(k + ': ' + v);
    }
    document.getElementById('comfyui-custom-paths').value = lines.join('\n');
    if (!data.exists) {
      showToast('ℹ️ extra_model_paths.yaml 不存在, 保存将创建默认', 'info', 3000);
    }
  } catch (e) {
    console.error('加载 ComfyUI 路径失败:', e);
    showToast('加载失败: ' + e.message, 'error');
  }
}

function _parseCustomPaths(text) {
  // 解析 textarea 为 {key: path, ...}
  // 格式: 每行 "key: path", 忽略空行和 # 开头注释
  const result = {};
  for (const raw of (text || '').split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const idx = line.indexOf(':');
    if (idx < 0) continue;
    const key = line.slice(0, idx).trim();
    const path = line.slice(idx + 1).trim();
    if (key && path) result[key] = path;
  }
  return result;
}

async function saveComfyuiPaths() {
  const btn = document.getElementById('btn-save-comfyui-paths');
  btn.disabled = true;
  btn.textContent = '⏳ 重启中...';
  try {
    const basePath = document.getElementById('comfyui-base-path').value.trim();
    if (!basePath) {
      showToast('base_path 不能为空', 'error');
      return;
    }
    const customPaths = _parseCustomPaths(document.getElementById('comfyui-custom-paths').value);
    const resp = await fetchJSON('/api/comfyui_extra_paths', 'PUT', {
      base_path: basePath,
      custom_paths: customPaths,
    });
    if (resp.status === 'ok') {
      showToast('✅ ' + (resp.message || '路径已保存'), 'success', 5000);
      // 重扫后模型列表会变, 触发全局 refresh
      setTimeout(refresh, 3000);
    } else {
      showToast('保存失败：' + (resp.error || '未知错误'), 'error');
    }
  } catch (e) {
    showToast('保存失败：' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '💾 保存并重启 ComfyUI';
  }
}

// 🎛️ Ollama 进程参数 (v1.1.16 简化, 只动 GPU_LAYERS)
async function loadOllamaGlobalParams() {
  try {
    const data = await fetchJSON('/api/ollama_global_params');
    // v1.1.16: 只显示 GPU_LAYERS, 其他 4 个字段已锁定无需 UI 调整
    document.getElementById('ollama-gpu-layers').value = data.gpu_layers ?? '';
  } catch (e) {
    console.error('加载 Ollama 进程参数失败:', e);
  }
}

async function saveOllamaGlobalParams() {
  const btn = document.getElementById('btn-save-ollama-global');
  btn.disabled = true;
  btn.textContent = '⏳ 重启中...';
  try {
    // v1.1.16: 只发送 GPU_LAYERS, 后端会用硬编码最优值补齐其他 4 个字段
    const payload = {
      gpu_layers: document.getElementById('ollama-gpu-layers').value || null,
    };
    const resp = await fetchJSON('/api/ollama_global_params', 'POST', payload);
    if (resp.status === 'ok') {
      showToast('✅ ' + (resp.message || 'Ollama 进程参数已保存并重启'), 'success', 5000);
      setTimeout(refresh, 3000);
    } else {
      showToast('保存失败：' + (resp.error || '未知错误'), 'error');
    }
  } catch (e) {
    showToast('保存失败：' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '💾 保存并重启 Ollama';
  }
}

// 📦 Ollama per-model 参数 (v1.1.8-patch2)
async function loadOllamaModelParams() {
  if (!currentModel || currentFramework !== 'ollama') return;
  try {
    const data = await fetchJSON('/api/ollama_model_params?model=' + encodeURIComponent(currentModel));
    const p = data.params || {};
    document.getElementById('ollama-num-ctx').value = p.num_ctx || 131072;
    document.getElementById('ollama-temperature').value = p.temperature ?? '';
    document.getElementById('ollama-top-p').value = p.top_p ?? '';
    document.getElementById('ollama-top-k').value = p.top_k ?? '';
    document.getElementById('ollama-repeat-penalty').value = p.repeat_penalty ?? '';
    document.getElementById('ollama-model-params-name').textContent = currentModel;
  } catch (e) {
    console.error('加载 Ollama 模型参数失败:', e);
  }
}

async function saveOllamaModelParams() {
  if (!currentModel) { showToast('未加载 ollama 模型', 'error'); return; }
  const overlay = document.getElementById('ollama-model-params-overlay');
  const btn = document.getElementById('btn-save-ollama-model-params');
  btn.disabled = true;
  btn.textContent = '⏳ 保存中...';
  if (overlay) overlay.style.display = 'flex';
  try {
    const payload = {
      model: currentModel,
      num_ctx: document.getElementById('ollama-num-ctx').value,
      temperature: document.getElementById('ollama-temperature').value || null,
      top_p: document.getElementById('ollama-top-p').value || null,
      top_k: document.getElementById('ollama-top-k').value || null,
      repeat_penalty: document.getElementById('ollama-repeat-penalty').value || null,
    };
    const resp = await fetchJSON('/api/ollama_model_params', 'POST', payload);
    if (resp.status === 'ok') {
      const autoMsg = resp.auto_loaded ? '✅ 已保存并自动加载新 tag' : '✅ 已保存，新 tag 已就绪';
      showToast(autoMsg, 'success', 5000);
      // 如果自动加载成功，刷新状态
      if (resp.auto_loaded && resp.tag) {
        currentModel = resp.tag;  // 更新前端 currentModel
        await refresh();  // 刷新 UI
      }
    } else if (resp.status === 'partial') {
      showToast('⚠️ ' + (resp.warning || '部分成功'), 'error', 6000);
    } else {
      showToast('保存失败：' + (resp.error || '未知错误'), 'error');
    }
  } catch (e) {
    showToast('保存失败：' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '💾 保存并重建 tag';
    if (overlay) overlay.style.display = 'none';
  }
}

async function resetOllamaModelParams() {
  if (!currentModel) { showToast('未加载 ollama 模型', 'error'); return; }
  if (!confirm('确定要将 "' + currentModel + '" 的 per-model 参数恢复为 ollama defaults 中设置的值吗？\n\n将自动写 Modelfile 并重建 tag。')) return;
  const overlay = document.getElementById('ollama-model-params-overlay');
  const btn = document.getElementById('btn-reset-ollama-model-params');
  btn.disabled = true;
  btn.textContent = '⏳ 重置中...';
  if (overlay) overlay.style.display = 'flex';
  try {
    const resp = await fetchJSON('/api/restore_ollama_default_model_params', 'POST', {model: currentModel});
    if (resp.status === 'ok') {
      showToast('✅ ' + (resp.message || '已恢复默认'), 'success', 5000);
      // 重新拉参数刷卡片
      await loadOllamaModelParams();
    } else {
      showToast('恢复失败：' + (resp.error || '未知错误'), 'error');
    }
  } catch (e) {
    showToast('恢复失败：' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '🔄 恢复默认值';
    if (overlay) overlay.style.display = 'none';
  }
}

// 🎯 Ollama defaults 卡片 (v1.1.8-patch2)
// v1.1.11: 无 per-model 记录时, 自动从 _fallback 填充输入框 + save 时自动创建 models entry
// v1.1.15: 添加 userModified 标记, refresh() 不覆盖用户已修改的值
let ollamaDefaultsCache = { _fallback: {}, models: {} };
let ollamaFallbackOverride = {}; // 用户手动改 fallback 时的临时值
let ollamaUserModified = false; // 用户是否手动改过当前模型行的输入框

// 📋 新模型注册参数 (v1.1.17, 改用 select 后 v1.1.17-patch2)
async function loadManifestGenParams() {
  try {
    const data = await fetchJSON('/api/manifest_gen_params');
    const p = data.params || {};
    // select 在所有 option 都不匹配 value 时会默认到第一个 option, 所以先设 selected 再校验
    if (p.num_ctx) document.getElementById('mgen-num-ctx').value = String(p.num_ctx);
    if (p.temperature !== undefined) document.getElementById('mgen-temperature').value = String(p.temperature);
    if (p.top_p !== undefined) document.getElementById('mgen-top-p').value = String(p.top_p);
    if (p.top_k) document.getElementById('mgen-top-k').value = String(p.top_k);
    if (p.repeat_penalty !== undefined) document.getElementById('mgen-repeat-penalty').value = String(p.repeat_penalty);
  } catch (e) {
    console.error('加载 新模型注册参数 失败:', e);
  }
}

async function saveManifestGenParams() {
  const btn = document.getElementById('btn-save-mgen-params');
  btn.disabled = true;
  btn.textContent = '⏳ 保存中...';
  try {
    const payload = {
      num_ctx: document.getElementById('mgen-num-ctx').value,
      temperature: document.getElementById('mgen-temperature').value,
      top_p: document.getElementById('mgen-top-p').value,
      top_k: document.getElementById('mgen-top-k').value,
      repeat_penalty: document.getElementById('mgen-repeat-penalty').value,
    };
    const resp = await fetchJSON('/api/manifest_gen_params', 'POST', payload);
    if (resp.status === 'ok') {
      showToast('✅ 已保存: ' + JSON.stringify(resp.params), 'success', 3000);
    } else {
      showToast('保存失败: ' + (resp.error || '未知错误'), 'error');
    }
  } catch (e) {
    showToast('保存失败: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '💾 保存';
  }
}

// 📥 beellama 自动注册下载的模型 (v1.6.2)
async function ingestBeellama() {
  const btn = document.getElementById('btn-ingest-beellama');
  const resultDiv = document.getElementById('ingest-beellama-result');
  btn.disabled = true;
  btn.textContent = '⏳ 扫描中...';
  resultDiv.innerHTML = '正在扫描 <code>/data/ollama/models/blobs/</code>...';
  try {
    showLoadStatus(true);
    updateLoadStatusUI({ status: 'loading', message: '扫描并注册进 beellama...', progress: 10, elapsed_seconds: 0 });
    const r = await fetchJSON('/api/ingest_beellama', 'POST', {});
    updateLoadStatusUI({ status: 'loading', message: '注册中...', progress: 60, elapsed_seconds: 1 });
    let html = `<b>扫描到 ${r.scanned} 个未注册 .gguf</b><br>`;
    if (r.linked && r.linked.length > 0) {
      html += '✅ <b>已注册进 beellama</b>：' + r.linked.map(item => 
        `<code>${item.dir}/${item.src}</code> → <code>${item.target.split('/').pop()}</code>`
      ).join('<br>') + '<br>';
    }
    if (r.skipped && r.skipped.length > 0) {
      html += '⏭️ <b>已跳过</b>：' + r.skipped.map(n => `<code>${n}</code>`).join(', ') + '<br>';
    }
    if (r.errors && r.errors.length > 0) {
      html += '❌ <b>错误</b>：' + r.errors.map(e => `<code>${e}</code>`).join(', ') + '<br>';
    }
    resultDiv.innerHTML = html;
    updateLoadStatusUI({
      status: r.errors && r.errors.length > 0 ? 'error' : 'done',
      message: r.errors && r.errors.length > 0 ? `⚠️ ${r.linked.length} 成功, ${r.errors.length} 失败` : `✅ 注册 ${r.linked.length} 个模型到 beellama`,
      progress: 100,
      elapsed_seconds: 2
    });
    showToast(r.linked && r.linked.length > 0 ? `✅ 已注册 ${r.linked.length} 个模型到 beellama` : 'ℹ️ 扫描完成 (无新文件)', r.errors && r.errors.length > 0 ? 'warning' : 'success', 5000);
    setTimeout(function() { showLoadStatus(false); }, 3000);
    // 重新拉取模型列表
    setTimeout(refresh, 1000);
    // v1.6.2-patch3: 同时刷新默认设置卡的下拉列表 (使新注册的模型可见)
    if (typeof loadDefaultSettings === 'function') loadDefaultSettings();
  } catch (e) {
    resultDiv.innerHTML = '<span style="color:#f88;">❌ 错误: ' + e.message + '</span>';
    updateLoadStatusUI({ status: 'error', message: '❌ ' + e.message, progress: 100, elapsed_seconds: 1 });
    showToast('扫描失败: ' + e.message, 'error');
    setTimeout(function() { showLoadStatus(false); }, 3000);
  } finally {
    btn.disabled = false;
    btn.textContent = '📥 扫描并注册进 beellama';
  }
}

// 📥 自动注册下载的模型 (v1.1.18)
async function ingestGguf() {
  const btn = document.getElementById('btn-ingest-gguf');
  const resultDiv = document.getElementById('ingest-gguf-result');
  btn.disabled = true;
  btn.textContent = '⏳ 扫描中...';
  resultDiv.innerHTML = '正在扫描 <code>/data/ollama/models/blobs/</code>...';
  try {
    showLoadStatus(true);
    updateLoadStatusUI({ status: 'loading', message: '扫描并注册用户下载的 GGUF...', progress: 10, elapsed_seconds: 0 });
    const resp = await fetchJSON('/api/ingest_gguf', 'POST', {});
    updateLoadStatusUI({ status: 'loading', message: '注册中...', progress: 60, elapsed_seconds: 1 });
    const r = resp;
    let html = `<b>扫描到 ${r.scanned} 个未注册 .gguf</b><br>`;
    if (r.registered && r.registered.length > 0) {
      html += '✅ <b>已注册</b>：' + r.registered.map(n => `<code>${n}</code>`).join(', ') + '<br>';
    }
    if (r.skipped && r.skipped.length > 0) {
      html += '⏭️ <b>已跳过</b>：' + r.skipped.map(n => `<code>${n}</code>`).join(', ') + '<br>';
    }
    if (r.errors && r.errors.length > 0) {
      html += '❌ <b>错误</b>：' + r.errors.map(e => `<code>${e}</code>`).join(', ') + '<br>';
    }
    if (r.params_used) {
      html += `<br>使用参数：<code>${JSON.stringify(r.params_used)}</code>`;
    }
    resultDiv.innerHTML = html;
    updateLoadStatusUI({
      status: r.errors && r.errors.length > 0 ? 'error' : 'done',
      message: r.errors && r.errors.length > 0 ? `⚠️ ${r.registered.length} 成功, ${r.errors.length} 失败` : `✅ 注册 ${r.registered.length} 个模型`,
      progress: 100,
      elapsed_seconds: 2
    });
    showToast(r.registered && r.registered.length > 0 ? `✅ 已注册 ${r.registered.length} 个模型` : 'ℹ️ 扫描完成 (无新模型)', r.errors && r.errors.length > 0 ? 'warning' : 'success', 5000);
    setTimeout(function() { showLoadStatus(false); }, 3000);
  } catch (e) {
    resultDiv.innerHTML = '<span style="color:#f88;">❌ 错误: ' + e.message + '</span>';
    updateLoadStatusUI({ status: 'error', message: '❌ ' + e.message, progress: 100, elapsed_seconds: 1 });
    showToast('扫描失败: ' + e.message, 'error');
    setTimeout(function() { showLoadStatus(false); }, 3000);
  } finally {
    btn.disabled = false;
    btn.textContent = '📥 扫描并自动注册用户下载的模型';
  }
}

async function loadOllamaDefaults() {
  try {
    const data = await fetchJSON('/api/ollama_defaults');
    ollamaDefaultsCache = data || { _fallback: {}, models: {} };
    console.log('[DEBUG] loadOllamaDefaults called, cache:', JSON.stringify(ollamaDefaultsCache));
    renderOllamaDefaults();
  } catch (e) {
    showToast('加载 ollama defaults 失败：' + e.message, 'error');
  }
}

function renderOllamaDefaults() {
  const fb = ollamaDefaultsCache._fallback || {};
  document.getElementById('ollama-defaults-fallback-num-ctx').value = fb.num_ctx ?? '';
  document.getElementById('ollama-defaults-fallback-temp').value = fb.temperature ?? '';
  document.getElementById('ollama-defaults-fallback-top-p').value = fb.top_p ?? '';

  const badge = document.getElementById('ollama-defaults-current-badge');
  const nameEl = document.getElementById('ollama-defaults-current-name');
  const rowEl = document.getElementById('ollama-defaults-current-row');

  if (!currentModel) {
    badge.textContent = '(未加载 ollama 模型)';
    nameEl.textContent = '—';
    rowEl.innerHTML = '<div style="color:var(--text-dim);padding:6px 0;">加载 ollama 模型后, 在此编辑该模型的默认值</div>';
    // 重置 modified 标记，因为 DOM 被清空了
    window._odf_nc = null; window._odf_tm = null; window._odf_tp = null;
    return;
  }
  const baseName = currentModel.split(':')[0];
  badge.textContent = `(当前: ${baseName})`;

  // v1.1.17: 统一渲染——始终只更新已有 DOM, 绝不 innerHTML
  const matchedParams = (ollamaDefaultsCache.models || {})[baseName];
  nameEl.textContent = baseName + (matchedParams ? ' ✓' : ' (使用 _fallback)');

  // v1.1.17: 全局引用 input 元素, 避免每次 getElementById
  let ncElGlobal = window._odf_nc || null;
  let tmElGlobal = window._odf_tm || null;
  let tpElGlobal = window._odf_tp || null;

  if (!ncElGlobal) {
    // 首次渲染: 创建 input 元素并追加到 row
    rowEl.innerHTML = `
      <div class="ollama-defaults-row" data-name="${baseName}" style="display:flex;gap:8px;align-items:center;padding:6px 0;flex-wrap:wrap;">
        <input type="number" id="odf-num-ctx-current" placeholder="num_ctx" min="512" max="1048576" step="512" style="width:110px;">
        <input type="number" id="odf-temp-current" placeholder="temp" step="0.1" min="0" max="2" style="width:80px;">
        <input type="number" id="odf-top-p-current" placeholder="top_p" step="0.05" min="0" max="1" style="width:80px;">
        <span class="odf-status-text" style="color:var(--text-dim);font-size:0.78rem;margin-left:8px;"></span>
      </div>
    `;
    ncElGlobal = document.getElementById('odf-num-ctx-current');
    tmElGlobal = document.getElementById('odf-temp-current');
    tpElGlobal = document.getElementById('odf-top-p-current');
    window._odf_nc = ncElGlobal;
    window._odf_tm = tmElGlobal;
    window._odf_tp = tpElGlobal;
    // 绑定 oninput (只绑一次)
    ncElGlobal.oninput = () => {
      ollamaFallbackOverride.num_ctx = parseInt(ncElGlobal.value) || null;
      ollamaUserModified = true;
    };
    tmElGlobal.oninput = () => {
      ollamaFallbackOverride.temperature = parseFloat(tmElGlobal.value) || null;
      ollamaUserModified = true;
    };
    tpElGlobal.oninput = () => {
      ollamaFallbackOverride.top_p = parseFloat(tpElGlobal.value) || null;
      ollamaUserModified = true;
    };
  }
  // 每次渲染都更新 input value (v1.1.18 修复：之前后续渲染不更新 value，导致用户输入被清空)
  const initValNumCtx = matchedParams?.num_ctx ?? fb.num_ctx;
  const initValTemp = matchedParams?.temperature ?? fb.temperature;
  const initValTopP = matchedParams?.top_p ?? fb.top_p;
  if (ncElGlobal) ncElGlobal.value = (initValNumCtx !== null && initValNumCtx !== '') ? String(initValNumCtx) : '';
  if (tmElGlobal) tmElGlobal.value = (initValTemp !== null && initValTemp !== '') ? String(initValTemp) : '';
  if (tpElGlobal) tpElGlobal.value = (initValTopP !== null && initValTopP !== '') ? String(initValTopP) : '';

  // 更新 status text
  const statusSpan = rowEl.querySelector('.odf-status-text');
  if (statusSpan) {
    statusSpan.textContent = matchedParams ? `(将保存到 <code>${baseName}</code>)` : '(将创建 <code>' + baseName + '</code> 记录)';
  }
}

async function saveOllamaDefaults() {
  // v1.1.13: 先同步当前输入框的值到 ollamaFallbackOverride
  const curNc = document.getElementById('odf-num-ctx-current');
  const curTm = document.getElementById('odf-temp-current');
  const curTp = document.getElementById('odf-top-p-current');
  if (curNc) ollamaFallbackOverride.num_ctx = parseInt(curNc.value) || null;
  if (curTm) ollamaFallbackOverride.temperature = parseFloat(curTm.value) || null;
  if (curTp) ollamaFallbackOverride.top_p = parseFloat(curTp.value) || null;

  const btn = document.getElementById('btn-save-ollama-defaults');
  btn.disabled = true;
  btn.textContent = '⏳ 保存中...';
  try {
    // _fallback
    const fb = {
      num_ctx: parseInt(document.getElementById('ollama-defaults-fallback-num-ctx').value) || null,
      temperature: parseFloat(document.getElementById('ollama-defaults-fallback-temp').value) || null,
      top_p: parseFloat(document.getElementById('ollama-defaults-fallback-top-p').value) || null,
    };
    // v1.1.17: 不重置 ollamaFallbackOverride (saveOllamaDefaults 里不该覆盖用户输入)
    // models: 保留所有已有记录
    const models = {};
    for (const k of Object.keys(ollamaDefaultsCache.models || {})) {
      models[k] = ollamaDefaultsCache.models[k];
    }
    // 当前模型行: 优先用 id, 其次用 class
    const row = document.querySelector('.ollama-defaults-row');
    if (row) {
      const name = row.getAttribute('data-name');
      let ncVal, tmVal, tpVal;
      const iNc = row.querySelector('#odf-num-ctx-current');
      const iTm = row.querySelector('#odf-temp-current');
      const iTp = row.querySelector('#odf-top-p-current');
      if (iNc) {
        ncVal = parseInt(iNc.value);
        tmVal = parseFloat(iTm.value);
        tpVal = parseFloat(iTp.value);
      } else {
        ncVal = parseInt(row.querySelector('.odf-num-ctx')?.value);
        tmVal = parseFloat(row.querySelector('.odf-temp')?.value);
        tpVal = parseFloat(row.querySelector('.odf-top-p')?.value);
      }
      models[name] = {
        num_ctx: isNaN(ncVal) ? null : ncVal,
        temperature: isNaN(tmVal) ? null : tmVal,
        top_p: isNaN(tpVal) ? null : tpVal,
      };
    }
    const resp = await fetchJSON('/api/ollama_defaults', 'POST', {
      _fallback: fb,
      models: models,
    });
    if (resp.status === 'ok') {
      showToast('✅ ollama defaults 已保存', 'success', 4000);
      await loadOllamaDefaults();
    } else {
      showToast('保存失败：' + (resp.error || '未知错误'), 'error');
    }
  } catch (e) {
    showToast('保存失败：' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '💾 保存 ollama defaults';
  }
}

// 📦 模型专属参数管理
let lastLoadedModel = null;

async function loadModelParams() {
  if (!currentModel || currentFramework !== 'beellama') return;
  try {
    const data = await fetchJSON('/api/beellama_model_params');
    document.getElementById('model-ctx-size').value = data.ctx_size || '';
    document.getElementById('model-parallel').value = data.parallel || '';
    document.getElementById('model-ngpu-layers').value = data.ngpu_layers || '';
    document.getElementById('model-params-model-name').textContent = currentModel;
    lastLoadedModel = currentModel;

    const card = document.getElementById('beellama-model-params-card');
    if (card) card.style.display = 'block';
    // v1.6.2-patch2: 同步渲染「当前模型默认值」块
    if (typeof renderModelDefaultsCurrent === 'function') renderModelDefaultsCurrent();
    console.log('✅ 模型专属参数卡片已显示:', currentModel);
  } catch (e) {
    console.error('加载模型参数失败:', e);
  }
}

async function saveModelParams() {
  if (!currentModel) {
    showToast('未加载模型，无法保存', 'error');
    return;
  }
  const ctxSize = document.getElementById('model-ctx-size').value;
  const parallel = document.getElementById('model-parallel').value;
  const ngl = document.getElementById('model-ngpu-layers').value;
  
  const btn = document.getElementById('btn-save-model-params');
  const overlay = document.getElementById('model-params-overlay');
  btn.disabled = true;
  btn.textContent = '⏳ 保存并重启中...';
  saveInProgress = true;
  if (overlay) overlay.style.display = 'flex';
  
  try {
    // 一个端点完成: 保存 → 停止 → 启动 → 重载模型
    const resp = await fetchJSON('/api/save_and_apply_model_params', 'POST', {
      model: currentModel,
      ctx_size: ctxSize || null,
      parallel: parallel || null,
      ngpu_layers: ngl || null
    });
    if (resp.status === 'ok') {
      showToast('✅ ' + (resp.message || '已应用新参数并加载模型'), 'success', 6000);
    } else {
      showToast('保存失败：' + (resp.error || '未知错误'), 'error');
    }
  } catch (e) {
    showToast('保存失败：' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '💾 保存模型参数';
    saveInProgress = false;
    if (overlay) overlay.style.display = 'none';
    refresh();
  }
}

async function resetModelParams() {
  if (!currentModel) {
    showToast('未加载模型，无法恢复', 'error');
    return;
  }
  if (!confirm('确定要将 "' + currentModel + '" 的 per-model 参数恢复为「默认值」卡中设置的值吗？\n\n将自动重启 beellama 并重载模型。')) return;

  const btn = document.getElementById('btn-reset-model-params');
  const overlay = document.getElementById('model-params-overlay');
  btn.disabled = true;
  btn.textContent = '⏳ 重置并重启中...';
  saveInProgress = true;
  if (overlay) overlay.style.display = 'flex';

  try {
    // 调新端点: 从 defaults.json 读值 → 写入 per-model → 重启 beellama
    const resp = await fetchJSON('/api/restore_default_model_params', 'POST', {
      model: currentModel
    });
    if (resp.status === 'ok') {
      // 用后端返回的 params 刷新输入框
      const p = resp.params || {};
      document.getElementById('model-ctx-size').value = p.ctx_size || '';
      document.getElementById('model-parallel').value = p.parallel || '';
      document.getElementById('model-ngpu-layers').value = p.ngpu_layers || '';
      showToast('✅ ' + (resp.message || '已恢复默认并重载模型'), 'success', 6000);
    } else {
      showToast('恢复失败：' + (resp.error || '未知错误'), 'error');
    }
  } catch (e) {
    showToast('恢复失败：' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '🔄 恢复默认值';
    saveInProgress = false;
    if (overlay) overlay.style.display = 'none';
    refresh();
  }
}

// ── 「🎯 默认值」卡片 (v1.1.5: 只显示当前加载模型) ──────────────────────────

async function loadDefaults() {
  try {
    const data = await fetchJSON('/api/defaults');
    defaultsCache = data;
    renderDefaults();
    renderModelDefaultsCurrent();
  } catch (e) {
    showToast('加载默认值文件失败：' + e.message, 'error');
  }
}

function renderDefaults() {
  // _fallback 永远显示 (统一默认值卡)
  const fb = defaultsCache._fallback || {};
  document.getElementById('defaults-fallback-ctx').value = fb.ctx_size ?? '';
  document.getElementById('defaults-fallback-parallel').value = fb.parallel ?? '';
  document.getElementById('defaults-fallback-ngl').value = fb.ngpu_layers ?? '';
}

// v1.6.2-patch2: 渲染「当前模型默认值」块 (在「模型专属参数」卡片内)
function renderModelDefaultsCurrent() {
  const rowEl = document.getElementById('model-defaults-current-row');
  if (!rowEl) return;

  if (!currentModel || currentFramework !== 'beellama') {
    rowEl.innerHTML = '<div style="color:var(--text-dim);padding:6px 0;">加载 beellama 模型后, 在此编辑该模型的默认值</div>';
    return;
  }

  // 查找 currentModel 对应的 defaults.models key
  let matchedKey = currentModel;
  let matchedParams = defaultsCache.models && defaultsCache.models[matchedKey];
  if (!matchedParams) {
    for (const k of Object.keys(defaultsCache.models || {})) {
      if (currentModel.includes(k) || k.includes(currentModel)) {
        matchedKey = k;
        matchedParams = defaultsCache.models[k];
        break;
      }
    }
  }

  if (matchedParams) {
    rowEl.innerHTML = `
      <div class="defaults-row" data-name="${matchedKey}" style="display:flex;gap:8px;align-items:center;padding:6px 0;">
        <input type="number" class="df-ctx" placeholder="ctx" value="${matchedParams.ctx_size ?? ''}" min="512" max="1048576" step="512" style="width:110px;">
        <input type="number" class="df-parallel" placeholder="parallel" value="${matchedParams.parallel ?? ''}" min="1" max="16" style="width:80px;">
        <input type="number" class="df-ngl" placeholder="ngl" value="${matchedParams.ngpu_layers ?? ''}" min="0" max="200" style="width:80px;">
        <span style="color:var(--text-dim);font-size:0.78rem;margin-left:8px;">→ <code>${matchedKey}</code></span>
      </div>
    `;
  } else {
    rowEl.innerHTML = `
      <div style="color:var(--orange);padding:6px 0;font-size:0.85rem;">
        ⚠️ 当前模型「${currentModel}」无默认值记录。<br>
        加载时会自动用 _fallback 初始化 (弹模态框确认)。<br>
        初始化后下次保存即可在此编辑。
      </div>
    `;
  }
}

async function saveDefaultsFallback() {
  // v1.6.2-patch2: 仅保存 _fallback, 不动 models
  const btn = document.getElementById('btn-save-defaults-fallback');
  btn.disabled = true;
  btn.textContent = '⏳ 保存中...';
  try {
    const payload = {
      _fallback: {
        ctx_size: parseInt(document.getElementById('defaults-fallback-ctx').value) || null,
        parallel: parseInt(document.getElementById('defaults-fallback-parallel').value) || null,
        ngpu_layers: parseInt(document.getElementById('defaults-fallback-ngl').value) || null,
      }
    };
    await fetchJSON('/api/defaults', 'POST', payload);
    showToast('✅ 统一默认值已保存 (_fallback)', 'success', 4000);
    await loadDefaults();
  } catch (e) {
    showToast('保存失败：' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '💾 保存统一默认';
  }
}

async function saveDefaultsCurrentModel() {
  // v1.6.2-patch2: 仅保存当前模型的 defaults.models[currentModel], 不动 _fallback 和其他模型
  if (!currentModel) {
    showToast('未加载模型，无法保存', 'error');
    return;
  }
  const btn = document.getElementById('btn-save-defaults-current');
  const row = document.querySelector('#model-defaults-current-row .defaults-row');
  if (!row) {
    showToast('当前模型无默认值记录, 请先加载模型初始化', 'error');
    return;
  }
  btn.disabled = true;
  btn.textContent = '⏳ 保存中...';
  try {
    const name = row.getAttribute('data-name');
    const payload = {
      models: {
        [name]: {
          ctx_size: parseInt(row.querySelector('.df-ctx').value) || null,
          parallel: parseInt(row.querySelector('.df-parallel').value) || null,
          ngpu_layers: parseInt(row.querySelector('.df-ngl').value) || null,
        }
      }
    };
    await fetchJSON('/api/defaults', 'POST', payload);
    showToast('✅ 已保存当前模型默认值 (→ defaults.models.' + name + ')', 'success', 4000);
    await loadDefaults();
  } catch (e) {
    showToast('保存失败：' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '💾 保存默认';
  }
}

// ── 「➕ 添加新模型」模态框 (v1.1.5) ──────────────────────────

let _pendingInitModel = null;

async function showInitModelModal(model, shortName, errorMsg) {
  _pendingInitModel = { model, shortName };
  try {
    const defaults = await fetchJSON('/api/defaults');
    const fb = defaults._fallback || {};
    document.getElementById('init-model-modal-text').innerHTML =
      `模型 <code style="background:#0a1a2a;padding:2px 6px;border-radius:3px;">${shortName}</code> 还没有配置: <br>` +
      `<span style="color:var(--text-dim);font-size:0.85rem;">${errorMsg || '缺 ctx/parallel/ngpu_layers'}</span>`;
    document.getElementById('init-model-preview').innerHTML =
      `ctx_size:     <b>${fb.ctx_size ?? '?'}</b><br>` +
      `parallel:     <b>${fb.parallel ?? '?'}</b><br>` +
      `ngpu_layers:  <b>${fb.ngpu_layers ?? '?'}</b>`;
    document.getElementById('init-model-modal').style.display = 'flex';
  } catch (e) {
    showToast('读取默认值失败: ' + e.message, 'error');
  }
}

function cancelInitModel() {
  document.getElementById('init-model-modal').style.display = 'none';
  _pendingInitModel = null;
}

async function confirmInitModel() {
  if (!_pendingInitModel) return;
  const btn = document.getElementById('btn-confirm-init');
  btn.disabled = true;
  btn.textContent = '⏳ 初始化并启动中...';
  try {
    const resp = await fetchJSON('/api/init_model_with_fallback', 'POST', {
      model: _pendingInitModel.model
    });
    if (resp.status === 'ok') {
      showToast('✅ 已初始化「' + _pendingInitModel.shortName + '」并加载', 'success', 6000);
      document.getElementById('init-model-modal').style.display = 'none';
      _pendingInitModel = null;
      // 重新拉 defaults 卡片 (新模型已加入)
      await loadDefaults();
      // 重新拉全局状态
      setTimeout(refresh, 1500);
    } else {
      showToast('初始化失败: ' + (resp.error || '未知错误'), 'error');
    }
  } catch (e) {
    showToast('初始化失败: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '✨ 初始化并启动';
  }
}

</script>
<script>console.log('[v1.1.17-hotfix] JS loaded at', new Date().toISOString());</script>
</body>
</html>'''

# ── v1.2.0: 推理请求队列 + 自动 VRAM 轮换 ────────────────────────
# append-only: 不修改现有任何函数/路由，仅新增
# 目的：让 OpenClaw (/model) 或其它工具通过 /api/qrun 提交推理请求，
#       framework-manager 自动维护队列 → 比对当前显存 → 必要时切框架/模型 → 转发 → 返回结果。
import base64 as _qr_base64
import uuid as _qr_uuid
import urllib.request as _urlreq
import urllib.error as _urlerr

_qrun_queue = []          # FIFO list of task ids pending to be picked up by worker
_qrun_tasks = {}          # task_id -> task dict (唯一可信源，含 queued/running/done/error/cancelled)
_qrun_lock = threading.Lock()
_qrun_event = threading.Event()
_qrun_worker_started = False
_qrun_worker_lock = threading.Lock()

# 每个框架的转发上游基址 + 允许转发的路径白名单
_QRUN_FORWARD_BASE = {
    "ollama":   "http://127.0.0.1:11434",
    "beellama": "http://127.0.0.1:8080",
    "comfyui":  "http://127.0.0.1:8188",
}
_QRUN_FORWARD_PATHS = {
    "ollama":   ["/api/generate", "/api/chat", "/api/embeddings", "/api/show"],
    "beellama": ["/v1/chat/completions", "/v1/completions", "/v1/embeddings"],
    # ComfyUI 是异步工作流提交，v1 不透传（需切换框架后由调用方自行交互）
    "comfyui":  [],
}


def _qrun_normalize_framework(fw):
    if not fw:
        return None
    fw = str(fw).lower().strip()
    return fw if fw in ("ollama", "beellama", "comfyui") else None


def _qrun_new_task(framework, model, upstream_path, method, body, headers, source):
    task = {
        "task_id": _qr_uuid.uuid4().hex[:12],
        "framework": framework,
        "model": model or "",
        "path": upstream_path,
        "method": (method or "POST").upper(),
        "body": body if body is not None else {},
        "headers": headers or {},
        "source": source or "unknown",
        "created_at": time.time(),
        "status": "queued",  # queued / running / done / error / cancelled
        "result": None,
        "error": None,
        "started_at": None,
        "finished_at": None,
        "switched": False,
    }
    with _qrun_lock:
        _qrun_queue.append(task["task_id"])
        _qrun_tasks[task["task_id"]] = task
    _qrun_event.set()
    return task


def _qrun_forward(framework, path, method, body, timeout=600):
    """转发到活跃框架的 HTTP 端点。返回 (status, bytes, content_type)。"""
    base = _QRUN_FORWARD_BASE.get(framework)
    if not base:
        return 501, json.dumps({"error": f"framework {framework} not supported for forwarding"}).encode("utf-8"), "application/json"
    url = base.rstrip("/") + path
    payload = json.dumps(body).encode("utf-8") if body is not None else b""
    req = _urlreq.Request(url, data=payload, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with _urlreq.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type", "application/json")
    except _urlerr.HTTPError as e:
        return e.code, e.read(), e.headers.get("Content-Type", "application/json")
    except Exception as e:
        return 502, json.dumps({"error": f"forward failed: {e}"}).encode("utf-8"), "application/json"


def _qrun_wait_for_framework_ready(framework, model, timeout=180):
    """等待 current_framework/current_model 与目标一致。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if current_framework == framework:
            if not model:
                return True
            cur_norm = _normalize_model_name(current_model) if current_model else ""
            tgt_norm = _normalize_model_name(model) if model else ""
            if cur_norm and cur_norm == tgt_norm:
                return True
        time.sleep(1)
    return False


def _qrun_worker_loop():
    """单 worker 线程，顺序处理队列（与「显存轮换」语义一致：同一时刻一个模型）。"""
    global last_activity_time
    log.info("[qrun] worker started")
    while True:
        _qrun_event.wait()
        _qrun_event.clear()
        while True:
            with _qrun_lock:
                if not _qrun_queue:
                    break
                tid = _qrun_queue.pop(0)
                task = _qrun_tasks.get(tid)
            if not task:
                continue  # 已被取消
            task["status"] = "running"
            task["started_at"] = time.time()
            log.info(f"[qrun] {task['task_id']} start fw={task['framework']} model={task['model']} {task['method']} {task['path']}")
            try:
                fw = task["framework"]
                model = task["model"]
                # 1. 比对当前是否已就绪
                need_switch = False
                if current_framework != fw:
                    need_switch = True
                elif model:
                    cur_norm = _normalize_model_name(current_model) if current_model else ""
                    tgt_norm = _normalize_model_name(model) if model else ""
                    if cur_norm != tgt_norm:
                        need_switch = True
                # 2. 切换
                if need_switch:
                    task["switched"] = True
                    log.info(f"[qrun] {task['task_id']} switch {current_framework}/{current_model} → {fw}/{model}")
                    if not switch_framework_to(fw):
                        raise RuntimeError(f"switch_framework_to({fw}) failed")
                    if model:
                        ok, msg = load_model_for_framework(model)
                        if not ok:
                            raise RuntimeError(f"load_model_for_framework failed: {msg}")
                # 3. 等就绪
                if not _qrun_wait_for_framework_ready(fw, model, timeout=180):
                    raise RuntimeError(f"timeout waiting {fw}/{model} ready")
                # 4. 转发（保持活动计时，防止空闲回退误触发）
                last_activity_time = time.time()
                status, data, ctype = _qrun_forward(fw, task["path"], task["method"], task["body"], timeout=600)
                task["result"] = {
                    "status": status,
                    "content_type": ctype,
                    "body_b64": _qr_base64.b64encode(data).decode("ascii"),
                }
                task["status"] = "done" if status < 400 else "error"
                if status >= 400:
                    task["error"] = f"upstream returned {status}"
                log.info(f"[qrun] {task['task_id']} done upstream_status={status}")
            except Exception as e:
                task["status"] = "error"
                task["error"] = str(e)
                log.error(f"[qrun] {task['task_id']} error: {e}")
            finally:
                task["finished_at"] = time.time()
                # task 已在 _qrun_tasks 中，状态已更新；仅通知 worker 检查下一个
                _qrun_event.set()
                time.sleep(0.05)


def _ensure_qrun_worker():
    global _qrun_worker_started
    with _qrun_worker_lock:
        if _qrun_worker_started:
            return
        t = threading.Thread(target=_qrun_worker_loop, name="qrun-worker", daemon=True)
        t.start()
        _qrun_worker_started = True
        log.info("[qrun] worker thread spawned")


def _qrun_task_to_response(task):
    """把 task dict 包装成 Flask JSON 响应。"""
    out = {
        "task_id": task["task_id"],
        "status": task["status"],
        "framework": task["framework"],
        "model": task["model"],
        "path": task["path"],
        "switched": task.get("switched", False),
        "created_at": task["created_at"],
        "started_at": task.get("started_at"),
        "finished_at": task.get("finished_at"),
        "source": task.get("source"),
    }
    if task.get("error"):
        out["error"] = task["error"]
    if task.get("result"):
        out["upstream_status"] = task["result"]["status"]
        out["upstream_content_type"] = task["result"]["content_type"]
        out["upstream_body_b64"] = task["result"]["body_b64"]
        # 便利字段：若 JSON 响应则直接解码
        try:
            body_bytes = _qr_base64.b64decode(task["result"]["body_b64"])
            if (task["result"]["content_type"] or "").startswith("application/json"):
                out["upstream_body"] = json.loads(body_bytes)
        except Exception:
            pass
    return jsonify(out)


@app.route("/api/qrun", methods=["POST"])
def api_qrun():
    """入队推理请求。
    Body: {"framework":"ollama|beellama|comfyui",
           "model":"...",      // 可选；省略则只切框架不加载模型
           "path":"/api/chat", // 默认 ollama→/api/chat, beellama→/v1/chat/completions
           "method":"POST",
           "body":{...},       // 透传给上游的 JSON body
           "source":"openclaw" // 标识调用方，便于审计
          }
    Query: ?wait=true&timeout=600 同步等结果
    """
    global last_activity_time
    last_activity_time = time.time()
    _ensure_qrun_worker()

    data = request.get_json(silent=True) or {}
    fw = _qrun_normalize_framework(data.get("framework"))
    if not fw:
        return jsonify({"error": "framework must be one of ollama/beellama/comfyui"}), 400
    if fw == "comfyui":
        return jsonify({
            "error": "comfyui forwarding not implemented in v1; please switch framework manually first",
            "hint": "POST /api/set_framework {\"framework\":\"comfyui\"} then call comfyui's own endpoints directly"
        }), 501

    model = data.get("model") or ""
    upstream_path = data.get("path")
    if not upstream_path:
        upstream_path = "/api/chat" if fw == "ollama" else "/v1/chat/completions"
    if upstream_path not in _QRUN_FORWARD_PATHS.get(fw, []):
        return jsonify({
            "error": f"path {upstream_path} not allowed for framework {fw}",
            "allowed": _QRUN_FORWARD_PATHS.get(fw, [])
        }), 400
    method = (data.get("method") or "POST").upper()
    body = data.get("body")
    source = data.get("source") or request.headers.get("X-Source") or "unknown"

    task = _qrun_new_task(fw, model, upstream_path, method, body, {}, source)

    wait = request.args.get("wait", "").lower() in ("1", "true", "yes")
    if wait:
        try:
            timeout_s = float(request.args.get("timeout", "600"))
        except ValueError:
            timeout_s = 600.0
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            with _qrun_lock:
                t = _qrun_tasks.get(task["task_id"])
            if t and t["status"] in ("done", "error", "cancelled"):
                return _qrun_task_to_response(t)
            time.sleep(0.2)
        return jsonify({"task_id": task["task_id"], "status": "timeout_waiting"}), 202

    return jsonify({"task_id": task["task_id"], "status": "queued"}), 202


@app.route("/api/qrun/<task_id>", methods=["GET"])
def api_qrun_get(task_id):
    with _qrun_lock:
        t = _qrun_tasks.get(task_id)
    if not t:
        return jsonify({"error": "task not found"}), 404
    return _qrun_task_to_response(t)


@app.route("/api/qrun/<task_id>", methods=["DELETE"])
def api_qrun_cancel(task_id):
    with _qrun_lock:
        t = _qrun_tasks.get(task_id)
        if not t:
            return jsonify({"error": "task not found"}), 404
        if t["status"] != "queued":
            return jsonify({"error": f"task not cancellable (status={t['status']})"}), 409
        # 从 _qrun_queue 移除
        try:
            _qrun_queue.remove(task_id)
        except ValueError:
            pass
        t["status"] = "cancelled"
        t["finished_at"] = time.time()
        return jsonify({"task_id": task_id, "status": "cancelled"})


@app.route("/api/qstatus", methods=["GET"])
def api_qstatus():
    """队列状态（不返回任务 body，避免泄密）。"""
    with _qrun_lock:
        queued_count = len(_qrun_queue)
        running_count = 0
        by_framework = {}
        by_model = {}
        # 清理 5 分钟前已结束的记录
        cutoff = time.time() - 300
        for tid in list(_qrun_tasks.keys()):
            t = _qrun_tasks[tid]
            st = t.get("status")
            if st in ("done", "error", "cancelled") and t.get("finished_at", 0) < cutoff:
                _qrun_tasks.pop(tid, None)
                continue
            if st == "queued":
                by_framework[t["framework"]] = by_framework.get(t["framework"], 0) + 1
                key = t["model"] or "—"
                by_model[key] = by_model.get(key, 0) + 1
            elif st == "running":
                running_count += 1
        return jsonify({
            "queued": queued_count,
            "running": running_count,
            "by_framework": by_framework,
            "by_model": by_model,
            "current_framework": current_framework,
            "current_model": current_model,
            "worker_started": _qrun_worker_started,
        })


# ── v1.2.2: OpenAI 兼容端点 ────────────────────────────────────────
# 目的：让 Agent (OpenClaw/Claude Code/Cursor/Cherry Studio) 用标准 OpenAI 协议接入
# base_url = http://localhost:9528/v1
# model 格式: "framework/modelname" (如 "ollama/qwen3.6-35b" / "beellama/qwen3.6-q3")
# append-only: 不改任何现有函数/路由

def _openai_chat_ollama_to_openai(ollama_resp, model_str):
    """ollama /api/chat 响应 → OpenAI /v1/chat/completions 响应"""
    msg = ollama_resp.get("message", {}) or {}
    return {
        "id": f"chatcmpl-{ollama_resp.get('created_at', '').replace(':', '').replace('.', '').replace('-', '')[:24] or 'fm'}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_str,
        "choices": [{
            "index": 0,
            "message": {
                "role": msg.get("role", "assistant"),
                "content": msg.get("content", "")
            },
            "finish_reason": "stop" if ollama_resp.get("done") else "length"
        }],
        "usage": {
            "prompt_tokens": ollama_resp.get("prompt_eval_count", 0) or 0,
            "completion_tokens": ollama_resp.get("eval_count", 0) or 0,
            "total_tokens": (ollama_resp.get("prompt_eval_count", 0) or 0) +
                            (ollama_resp.get("eval_count", 0) or 0)
        }
    }


@app.route("/v1/chat/completions", methods=["POST"])
def openai_chat_completions():
    """OpenAI 兼容聊天端点
    接收标准 OpenAI 格式请求, 内部转给 /api/qrun 队列, 把响应转回 OpenAI 格式
    """
    global last_activity_time
    last_activity_time = time.time()

    data = request.get_json(silent=True) or {}
    model_str = (data.get("model") or "").strip()
    messages = data.get("messages") or []
    if not model_str:
        return jsonify({"error": {"message": "model is required", "type": "invalid_request_error"}}), 400
    if not messages:
        return jsonify({"error": {"message": "messages is required", "type": "invalid_request_error"}}), 400

    # 解析 model: "framework/modelname"
    # v1.2.2-patch1: 支持 "framework-manager/current" — 用当前显存里的模型, 不需切换
    if model_str == "framework-manager/current":
        if not current_framework or not current_model:
            return jsonify({
                "error": {
                    "message": "no model currently loaded; please load one via 9528 webui or /api/qrun",
                    "type": "no_model_loaded"
                }
            }), 503
        framework = current_framework
        model_name = current_model
        log.info(f"[openai-compat] framework-manager/current → use {framework}/{model_name}")
    elif "/" in model_str:
        framework_raw, model_name = model_str.split("/", 1)
        framework = _qrun_normalize_framework(framework_raw)
    else:
        # 兼容: 没有前缀默认 ollama
        framework_raw, model_name = "ollama", model_str
        framework = _qrun_normalize_framework(framework_raw)
    if framework is None and model_str != "framework-manager/current":
        return jsonify({
            "error": {
                "message": f"unsupported framework: {framework_raw}. Use ollama/ or beellama/ prefix.",
                "type": "invalid_request_error"
            }
        }), 400
    if framework == "comfyui":
        return jsonify({
            "error": {
                "message": "comfyui not supported via OpenAI API in v1.2.2; please call /api/qrun directly",
                "type": "invalid_request_error"
            }
        }), 501

    # 构造上游请求 body
    if framework == "ollama":
        upstream_path = "/api/chat"
        # ollama /api/chat body 格式
        body = {
            "model": model_name,
            "messages": messages,
            "stream": False,
        }
        # 透传 ollama 特定参数 (options / format / keep_alive)
        for k in ("options", "format", "keep_alive"):
            if k in data:
                body[k] = data[k]
    elif framework == "beellama":
        upstream_path = "/v1/chat/completions"
        # beellama 接收 OpenAI 格式, 直接透传 + 修正 model
        body = dict(data)
        body["model"] = model_name
        body["stream"] = False

    # 调 /api/qrun 队列（同步等结果, OpenAI 协议默认同步）
    _ensure_qrun_worker()
    task = _qrun_new_task(framework, model_name, upstream_path, "POST", body,
                          {"X-Source": "openai-compat"}, "openai-compat")

    timeout_s = float(data.get("timeout", 600))
    deadline = time.time() + timeout_s
    t = None
    while time.time() < deadline:
        with _qrun_lock:
            t = _qrun_tasks.get(task["task_id"])
        if t and t["status"] in ("done", "error", "cancelled"):
            break
        time.sleep(0.2)

    if not t or t["status"] not in ("done", "error", "cancelled"):
        return jsonify({
            "error": {"message": f"task timeout after {timeout_s}s", "type": "timeout"},
            "task_id": task["task_id"]
        }), 504

    if t["status"] == "error":
        return jsonify({
            "error": {
                "message": t.get("error", "unknown error"),
                "type": "framework_error",
                "task_id": t["task_id"]
            }
        }), 500

    # 解析上游响应, 转 OpenAI 格式
    result = t.get("result", {})
    body_b64 = result.get("body_b64", "")
    if not body_b64:
        return jsonify({
            "error": {"message": "empty upstream response", "type": "framework_error"},
            "task_id": t["task_id"]
        }), 500

    import base64 as _oa_b64
    upstream_data = json.loads(_oa_b64.b64decode(body_b64))

    if framework == "ollama":
        openai_resp = _openai_chat_ollama_to_openai(upstream_data, model_str)
    elif framework == "beellama":
        # beellama 已经是 OpenAI 格式, 修正 model 字段后直接返回
        upstream_data["model"] = model_str
        if "created" not in upstream_data:
            upstream_data["created"] = int(time.time())
        openai_resp = upstream_data

    # 附加 framework-manager 内部信息（不影响 OpenAI 兼容性）
    openai_resp["_task_id"] = t["task_id"]
    openai_resp["_framework"] = framework
    openai_resp["_switched"] = t.get("switched", False)
    return jsonify(openai_resp)


@app.route("/v1/models", methods=["GET"])
def openai_list_models():
    """OpenAI 兼容模型列表端点
    返回所有可用模型 (ollama + beellama)
    """
    models = []
    for fw_name in ("ollama", "beellama"):  # comfyui 暂不支持
        try:
            fw_models = get_framework_models(fw_name, force_refresh=True)
            for m in fw_models:
                models.append({
                    "id": f"{fw_name}/{m}",
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": fw_name
                })
        except Exception as e:
            log.warning(f"[openai-compat] failed to list {fw_name} models: {e}")
    return jsonify({"object": "list", "data": models})


# ── v1.3.0: VRAM 监测模块 ─────────────────────────────────────────
# 目的: 被动观测 GPU 显存中所有进程 + 各 framework 任务状态
#       数据源唯一 = nvidia-smi (物理真理) + 各 framework API (语义补充)
#       不预估、不调度、不 stop 服务
import subprocess as _vram_subprocess

_vram_state = {
    "gpu_total_mb": 0,
    "gpu_used_mb": 0,
    "gpu_used_pct": 0,
    "gpu_util_pct": 0,
    "models": [],          # [{pid, process, used_mb, framework, model, task_state, task_info}]
    "active_fw": None,     # 与 current_framework 同步
    "active_model": None,  # 与 current_model 同步
    "updated_at": 0,
    "error": None,
}

_vram_monitor_started = False
_vram_monitor_lock = threading.Lock()


def _vram_scan_nvidia_smi():
    """调用 nvidia-smi 拿 GPU 总体 + 每个进程。返回 dict 或带 _err 字段的错误 dict。
    注: nvidia-smi 不支持同时 --query-gpu + --query-compute-apps, 拆两次调用。
    """
    try:
        # 1. GPU 总体
        gpu_out = _vram_subprocess.check_output([
            "nvidia-smi",
            "--query-gpu=memory.total,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits"
        ], text=True, timeout=5).strip()
        # 2. 每个进程
        proc_out = _vram_subprocess.check_output([
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader,nounits"
        ], text=True, timeout=5).strip()
    except FileNotFoundError:
        return {"_err": "nvidia-smi not installed"}
    except _vram_subprocess.TimeoutExpired:
        return {"_err": "nvidia-smi timeout"}
    except Exception as e:
        return {"_err": f"nvidia-smi failed: {e}"}

    # 解析 GPU 总体
    try:
        parts = [x.strip() for x in gpu_out.split(",")]
        gpu_total = int(parts[0])
        gpu_used = int(parts[1])
        gpu_util = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    except Exception:
        return {"_err": f"parse gpu line failed: {gpu_out}"}

    # 解析每个进程
    models = []
    for line in proc_out.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = [x.strip() for x in line.split(",")]
        if len(parts) >= 3:
            try:
                models.append({
                    "pid": int(parts[0]),
                    "process": parts[1],
                    "used_mb": int(parts[2]),
                })
            except Exception:
                continue

    return {
        "gpu_total_mb": gpu_total,
        "gpu_used_mb": gpu_used,
        "gpu_util_pct": gpu_util,
        "models": models,
    }


def _vram_enrich_ollama(models):
    """Ollama: /api/ps 拿当前 loaded models + 正在处理的请求数"""
    try:
        req = _urlreq.Request("http://localhost:11434/api/ps", method="GET")
        with _urlreq.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
    except Exception:
        return

    ollama_models = data.get("models", []) or []
    # 按进程名匹配 ollama 进程
    ollama_procs = [m for m in models if m["process"].lower() in ("ollama", "ollama_llama_server")]
    if not ollama_procs:
        return

    # 每个 loaded model 分配给它对应的进程 (按 used_mb 排序匹配)
    ollama_models_sorted = sorted(ollama_models, key=lambda x: x.get("size_vram", 0), reverse=True)
    ollama_procs_sorted = sorted(ollama_procs, key=lambda x: x["used_mb"], reverse=True)

    for i, proc in enumerate(ollama_procs_sorted):
        if i < len(ollama_models_sorted):
            m = ollama_models_sorted[i]
            ctx_tokens = sum(c.get("n_tokens", 0) for c in m.get("context", []) or [])
            proc["framework"] = "ollama"
            proc["model"] = m.get("name", "unknown")
            proc["vram_size_mb"] = m.get("size_vram", 0) // (1024 * 1024)
            if ctx_tokens > 0:
                proc["task_state"] = "processing"
                proc["task_info"] = f"正在处理 (ctx={ctx_tokens} tokens)"
            else:
                proc["task_state"] = "loaded"
                proc["task_info"] = "已加载, 空闲"
        else:
            proc["framework"] = "ollama"
            proc["model"] = "unknown"
            proc["task_state"] = "loaded"
            proc["task_info"] = "ollama 进程"


def _vram_enrich_comfyui(models):
    """ComfyUI: /queue 拿当前 running + pending 任务数"""
    try:
        req = _urlreq.Request("http://localhost:8188/queue", method="GET")
        with _urlreq.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
    except Exception:
        return

    running = data.get("queue_running", []) or []
    pending = data.get("queue_pending", []) or []

    # 匹配 comfyui 相关进程
    for proc in models:
        pname = proc["process"].lower()
        if "comfy" in pname or "main.py" in pname or proc["pid"] in [r.get("pid") for r in running if isinstance(r, dict) and "pid" in r]:
            proc["framework"] = "comfyui"
            if running:
                proc["task_state"] = "running"
                proc["task_info"] = f"queue={len(running) + len(pending)} ({len(running)} running, {len(pending)} pending)"
            elif pending:
                proc["task_state"] = "queued"
                proc["task_info"] = f"pending={len(pending)}"
            else:
                proc["task_state"] = "idle"
                proc["task_info"] = "ComfyUI 空闲"


def _vram_enrich_beellama(models):
    """beellama / embedding: 看进程名是否含 llama-server, 再看参数区分
    - 含 --embedding 或 --port 11999 → embedding 服务 (bge-m3 等)
    - 其余 llama-server → beellama LLM
    """
    for proc in models:
        pname = proc["process"].lower()
        if "beellama" not in pname and "llama-server" not in pname and "wrapper" not in pname:
            continue
        # 读 /proc/PID/cmdline 区分服务类型
        cmdline = ""
        try:
            with open(f'/proc/{proc["pid"]}/cmdline', 'rb') as f:
                cmdline = f.read().decode('utf-8', errors='ignore').replace('\x00', ' ')
        except Exception:
            pass
        # embedding 服务识别: --embedding 参数 或端口 11999
        if '--embedding' in cmdline or '--port 11999' in cmdline or '11999' in cmdline:
            if "framework" not in proc:
                proc["framework"] = "embedding"
                if "task_state" not in proc:
                    proc["task_state"] = "loaded"
                    proc["task_info"] = "embedding 服务 (memory_search)"
            continue
        # 其余 = beellama LLM
        if "framework" not in proc:
            proc["framework"] = "beellama"
            if "task_state" not in proc:
                proc["task_state"] = "loaded"
                proc["task_info"] = "beellama 进程"


def _vram_enrich_unknown(models):
    """未识别的进程: 标记 unknown"""
    for proc in models:
        if "framework" not in proc:
            proc["framework"] = "unknown"
            proc["task_state"] = "unknown"
            proc["task_info"] = f"未识别进程 {proc['process']}"


def _vram_monitor_loop():
    """每 5s 扫一次。错误时不退出, 持续重试。"""
    global _vram_state
    log.info("[vram] monitor thread started")
    while True:
        try:
            with _vram_monitor_lock:
                raw = _vram_scan_nvidia_smi()

                if raw and "_err" in raw:
                    _vram_state["error"] = raw["_err"]
                    _vram_state["updated_at"] = time.time()
                elif raw:
                    models = raw.pop("models", [])
                    # framework 推断 (各框架互不冲突, 都尝试)
                    _vram_enrich_ollama(models)
                    _vram_enrich_comfyui(models)
                    _vram_enrich_beellama(models)
                    _vram_enrich_unknown(models)

                    gpu_total = raw.get("gpu_total_mb", 0)
                    gpu_used = raw.get("gpu_used_mb", 0)
                    used_pct = int(gpu_used * 100 / gpu_total) if gpu_total > 0 else 0

                    _vram_state.update({
                        "gpu_total_mb": gpu_total,
                        "gpu_used_mb": gpu_used,
                        "gpu_used_pct": used_pct,
                        "gpu_util_pct": raw.get("gpu_util_pct", 0),
                        "models": models,
                        "active_fw": current_framework,
                        "active_model": current_model,
                        "updated_at": time.time(),
                        "error": None,
                    })
        except Exception as e:
            log.error(f"[vram] monitor error: {e}")
            _vram_state["error"] = str(e)
            _vram_state["updated_at"] = time.time()
        time.sleep(5)


def _ensure_vram_monitor():
    global _vram_monitor_started
    with _vram_monitor_lock:
        if _vram_monitor_started:
            return
        t = threading.Thread(target=_vram_monitor_loop, name="vram-monitor", daemon=True)
        t.start()
        _vram_monitor_started = True
        log.info("[vram] monitor thread spawned")


@app.route("/api/vram_status", methods=["GET"])
def api_vram_status():
    """VRAM 状态端点 (v1.3.0 + v1.4.0 task_register 增强)
    数据源: nvidia-smi (物理) + 各 framework API (语义) + task_register (精确)
    返回: GPU 总体 + 所有进程 + 每个进程的 framework/model/task_state + 所有活跃任务

    v1.6.0-patch3: 去掉 _ensure_vram_monitor() 调用 (避免死锁)
        原代码每次 API 调用都拿 _vram_monitor_lock, monitor thread 跑 nvidia-smi hang 时
        所有 API 都会卡在锁上。monitor 启动后是 daemon thread, 不需要每次都"确保启动"
    """
    age = int(time.time() - _vram_state.get("updated_at", 0)) if _vram_state.get("updated_at") else None
    active_tasks = _list_active_tasks()
    return jsonify({
        **_vram_state,
        "age_sec": age,
        "tasks": active_tasks,           # v1.4.0 新增: task_register 报告的活跃任务
        "task_count": len(active_tasks),
    })


# ── v1.4.0: 任务追踪 (task_register / task_done) ───────────────────────
# 目的: 精确追踪 GPU 任务。Skill 启动任务前 register, 完成后 done.
#       数据存内存 (重启后丢失), 不持久化.
#       不修改任何现有函数/路由, 仅新增
import uuid as _task_uuid

_tasks = {}               # task_id → task dict
_tasks_lock = threading.RLock()  # v1.6.0-patch5: 改 RLock (允许 watcher 嵌套持锁调 _auto_task_done)
_TASK_HISTORY_MAX = 200   # 内存中最多保留 200 个已完成任务


def _list_active_tasks():
    """返回当前运行中/排队的任务列表 (不含已完成/失败)"""
    now = time.time()
    out = []
    with _tasks_lock:
        for t in _tasks.values():
            if t["state"] in ("running", "queued"):
                started = t.get("started_at")
                duration = (now - started) if started else (now - t["registered_at"])
                out.append({
                    "task_id": t["task_id"],
                    "framework": t["framework"],
                    "model": t["model"],
                    "state": t["state"],
                    "source": t["source"],
                    "registered_at": t["registered_at"],
                    "started_at": t.get("started_at"),
                    "duration_sec": round(duration, 1),
                    "estimated_duration_sec": t.get("estimated_duration_sec"),
                    "metadata": t.get("metadata", {}),
                    "auto_detect": t.get("auto_detect", False),  # v1.5.0: 暴露给前端
                })
    return out


@app.route("/api/task_register", methods=["POST"])
def api_task_register():
    """注册一个 GPU 任务 (v1.4.0)
    Body (v1.5.0 加 framework_ref 自动检测):
        {
            "task_id": "可选, 不传则生成 uuid",
            "framework": "ollama|beellama|comfyui|embedding",  # 必填
            "model": "qwen3.6-q3",                             # 必填
            "estimated_duration_sec": 300,                      # 可选
            "source": "video-gen-skill",                       # 可选, 调用方标识
            "metadata": {},                                    # 可选, 附加信息
            "framework_ref": {                                  # v1.5.0 新增, 可选
                # ComfyUI: 提供 prompt_id, watcher 自动检测完成
                "prompt_id": "abc-123-xyz",
                # Ollama: 设置 detect="model_unload", watcher 等模型从 /api/ps 消失
                "detect": "model_unload"
            }
        }
    返回: {status: "ok", task_id: "...", state: "...", auto_detect: true/false}
    """
    data = request.get_json(silent=True) or {}
    fw = (data.get("framework") or "").lower().strip()
    if fw not in ("ollama", "beellama", "comfyui", "embedding"):
        return jsonify({"error": "framework must be one of ollama/beellama/comfyui/embedding"}), 400
    model = (data.get("model") or "").strip()
    if not model:
        return jsonify({"error": "model is required"}), 400

    task_id = (data.get("task_id") or "").strip() or _task_uuid.uuid4().hex[:16]
    now = time.time()
    framework_ref = data.get("framework_ref") or {}

    # v1.5.0: 验证 framework_ref 合法性
    auto_detect = False
    if fw == "comfyui" and "prompt_id" in framework_ref:
        if not isinstance(framework_ref["prompt_id"], str) or len(framework_ref["prompt_id"]) < 4:
            return jsonify({"error": "framework_ref.prompt_id must be string (ComfyUI prompt_id)"}), 400
        auto_detect = True
    elif fw == "ollama" and framework_ref.get("detect") == "model_unload":
        auto_detect = True
    elif fw == "beellama" and framework_ref.get("detect") == "gpu_idle":
        # v1.6.0: beellama LLM 推理 (qwen3-14b 等) 用 GPU util 监测
        auto_detect = True
    elif fw == "embedding":
        if framework_ref:
            return jsonify({"error": "framework=embedding 不支持 framework_ref (-ngl 0 CPU 推理, 0.04s 完成, 轮询捕不到)"}), 400
    elif fw == "beellama" and framework_ref:
        return jsonify({"error": 'beellama framework_ref 仅支持 {"detect":"gpu_idle"}, got: ' + str(framework_ref)}), 400

    with _tasks_lock:
        if task_id in _tasks:
            return jsonify({"error": f"task_id {task_id} already exists", "task_id": task_id}), 409
        _tasks[task_id] = {
            "task_id": task_id,
            "framework": fw,
            "model": model,
            "state": "running",   # 简化: register 后默认 running, 调用方可传 "queued"
            "source": (data.get("source") or "unknown"),
            "registered_at": now,
            "started_at": now if (data.get("state") != "queued") else None,
            "finished_at": None,
            "estimated_duration_sec": data.get("estimated_duration_sec"),
            "metadata": data.get("metadata") or {},
            "framework_ref": framework_ref,  # v1.5.0 新增
            "auto_detect": auto_detect,        # v1.5.0 新增
        }
        if data.get("state") == "queued":
            _tasks[task_id]["state"] = "queued"

    audit_log("task_register", f"{fw}/{model} task_id={task_id[:8]} auto_detect={auto_detect}", "ok")
    return jsonify({"status": "ok", "task_id": task_id, "state": _tasks[task_id]["state"], "auto_detect": auto_detect})


@app.route("/api/task_done", methods=["POST"])
def api_task_done():
    """标记任务完成 (v1.4.0)
    Body: {"task_id": "...", "status": "success|failed", "result": {...}}
    返回: {status: "ok", task_id: "...", "state": "..."}
    """
    data = request.get_json(silent=True) or {}
    task_id = (data.get("task_id") or "").strip()
    if not task_id:
        return jsonify({"error": "task_id is required"}), 400
    final_status = data.get("status", "success")
    if final_status not in ("success", "failed"):
        return jsonify({"error": "status must be success or failed"}), 400

    with _tasks_lock:
        t = _tasks.get(task_id)
        if not t:
            return jsonify({"error": f"task_id {task_id} not found"}), 404
        if t["state"] in ("done", "failed"):
            return jsonify({"error": f"task already {t['state']}", "task_id": task_id}), 409
        t["state"] = "done" if final_status == "success" else "failed"
        t["finished_at"] = time.time()
        t["result"] = data.get("result") or {}

    audit_log("task_done", f"{t['framework']}/{t['model']} task_id={task_id[:8]} {final_status}", "ok")
    return jsonify({"status": "ok", "task_id": task_id, "state": t["state"]})


@app.route("/api/tasks", methods=["GET"])
def api_tasks_list():
    """列出所有任务 (含历史) - 调试用"""
    with _tasks_lock:
        all_tasks = list(_tasks.values())
    return jsonify({"count": len(all_tasks), "tasks": all_tasks})


@app.route("/api/tasks/<task_id>", methods=["GET"])
def api_tasks_get(task_id):
    """查询单个任务状态"""
    with _tasks_lock:
        t = _tasks.get(task_id)
    if not t:
        return jsonify({"error": f"task_id {task_id} not found"}), 404
    return jsonify(t)


def _cleanup_old_tasks():
    """清理超过 _TASK_HISTORY_MAX 的旧历史任务, 保留活跃"""
    with _tasks_lock:
        finished = [(tid, t) for tid, t in _tasks.items() if t["state"] in ("done", "failed")]
        if len(finished) > _TASK_HISTORY_MAX:
            finished.sort(key=lambda x: x[1]["finished_at"] or 0)
            for tid, _ in finished[:len(finished) - _TASK_HISTORY_MAX]:
                del _tasks[tid]


# ── v1.5.0: 任务自动检测 watcher ───────────────────────────────────────
# 目的: 不靠 timeout, 直接监测框架原生信号
#   Ollama:   /api/ps 拿 models[], 任务模型消失 → done
#   ComfyUI:  /history/{prompt_id}, 出现 → done (查 status_str)
#   beellama/embedding: llama.cpp 无任务 API, 不支持自动检测, 必须手动 task_done
#
# task_register 时可传 framework_ref:
#   {"prompt_id": "abc-123"}              # ComfyUI 自动检测
#   {"detect": "model_unload"}             # Ollama: 等模型从 /api/ps 消失
#
# 重复 register 同一 framework_ref → 幂等
# v1.5.0 完全 append-only: 不修改任何现有函数/路由

_watcher_started = False
_watcher_lock = threading.Lock()


def _ensure_task_watcher():
    """启动后台 watcher 线程 (每 2s 轮询活跃任务)"""
    global _watcher_started
    with _watcher_lock:
        if _watcher_started:
            return
        _watcher_started = True
    t = threading.Thread(target=_task_watcher_loop, name="task-watcher", daemon=True)
    t.start()
    log.info("[v1.5.0] task watcher started (interval=2s)")


def _task_watcher_loop():
    """后台循环: 每 2s 轮询所有活跃任务的 framework 原生信号"""
    import urllib.request as _urlreq
    import urllib.error as _urlerr
    import json as _json

    while True:
        try:
            # 收集当前活跃任务快照
            with _tasks_lock:
                active = [(tid, dict(t)) for tid, t in _tasks.items()
                          if t["state"] in ("running", "queued")]

            for tid, task in active:
                fref = task.get("framework_ref") or {}
                fw = task["framework"]
                try:
                    if fw == "comfyui" and "prompt_id" in fref:
                        _check_comfyui_history(tid, task, fref["prompt_id"])
                    elif fw == "ollama" and fref.get("detect") == "model_unload":
                        _check_ollama_unload(tid, task)
                    elif fw == "beellama" and fref.get("detect") == "gpu_idle":
                        _check_beellama_gpu_idle(tid, task)
                except Exception as e:
                    log.debug(f"[watcher] {tid} check error: {e}")

            # 清理历史任务
            _cleanup_old_tasks()
        except Exception as e:
            log.error(f"[watcher] loop error: {e}")

        time.sleep(2)


def _check_comfyui_history(task_id, task, prompt_id):
    """ComfyUI: 查 /history/{prompt_id}, 出现则 task_done"""
    import urllib.request as _urlreq
    import json as _json

    try:
        url = f"http://127.0.0.1:8188/history/{prompt_id}"
        req = _urlreq.Request(url, method="GET")
        with _urlreq.urlopen(req, timeout=3) as resp:
            data = _json.loads(resp.read())
    except Exception:
        return  # ComfyUI 不在跑或网络问题, 不动任务

    if prompt_id not in data:
        return  # 还没完成

    # ComfyUI 完成了 → task_done
    entry = data[prompt_id]
    status = entry.get("status", {})
    status_str = status.get("status_str", "unknown")
    final_status = "success" if status_str == "success" else "failed"

    # 提取输出节点 (给 result)
    outputs = entry.get("outputs", {})
    output_files = []
    for node_id, out in outputs.items():
        for img in out.get("images", []):
            output_files.append({
                "filename": img.get("filename"),
                "type": "image",
                "subfolder": img.get("subfolder", ""),
            })
        for vid in out.get("gifs", []):
            output_files.append({
                "filename": vid.get("filename"),
                "type": "video",
                "subfolder": vid.get("subfolder", ""),
            })

    result = {
        "comfyui_status": status_str,
        "comfyui_completed": status.get("completed", False),
        "outputs": output_files,
        "auto_detected": True,
    }
    if final_status == "failed":
        # 提取错误信息
        errs = [m for m in status.get("messages", []) if m[0] == "execution_error"]
        if errs:
            result["error"] = errs[0][1].get("exception_message", "")[:500]

    _auto_task_done(task_id, final_status, result)


def _check_ollama_unload(task_id, task):
    """Ollama: /api/ps 查模型是否还在, 消失则 task_done"""
    import urllib.request as _urlreq
    import json as _json

    model_name = task.get("model", "")

    try:
        req = _urlreq.Request("http://localhost:11434/api/ps", method="GET")
        with _urlreq.urlopen(req, timeout=3) as resp:
            data = _json.loads(resp.read())
    except Exception:
        return  # ollama 不在, 不动任务 (任务方自行处理)

    models = data.get("models", [])
    # 匹配模型名 (支持短名匹配, 如 qwen3:14b-ctx64k → qwen3:14b)
    loaded_names = [m.get("name", "") for m in models]
    matched = any(model_name == n or model_name in n or n in model_name for n in loaded_names)

    if matched:
        return  # 模型还在, 任务进行中

    # 模型消失 → ollama 自动卸载了, 任务完成
    _auto_task_done(task_id, "success", {
        "ollama_unloaded": True,
        "remaining_models": loaded_names,
        "auto_detected": True,
    })


def _check_beellama_gpu_idle(task_id, task):
    """v1.6.0: beellama GPU util 自动检测
    策略: 总 GPU util 持续 < 15% 超过 6s → 任务 done
    适用: beellama LLM 推理 (qwen3-14b 等, 单次几秒到几十秒, GPU 推理)
    不适用: embedding (-ngl 0 CPU 推理, 0.04s 完成, 轮询周期 2s 捕不到)
            → embedding 维持手动 task_done

    v1.6.0-patch1: 改为操作 _tasks[tid] 原对象 (之前传 dict copy 改不动原对象)
    v1.6.0-patch2: 改用 _vram_state["gpu_util_pct"] 缓存, 不直接 subprocess 调 nvidia-smi
                    (避免和 _vram_monitor_loop 5s 一次的 nvidia-smi 死锁)
    """
    # v1.6.0-patch2: 直接读 vram_monitor 缓存 (5s 一次, 已经够用)
    # vram_state age 太旧 (>10s) → vram_monitor 死了, 不动任务 (保守)
    log.debug(f"[v1.6.0 watcher] {task_id[:8]} enter check")
    age = time.time() - _vram_state.get("updated_at", 0)
    if age > 10 or _vram_state.get("updated_at", 0) == 0:
        log.debug(f"[v1.6.0 watcher] {task_id[:8]} vram_state too old age={age:.1f}s")
        return  # vram_monitor 不可信, 不动任务
    gpu_util = _vram_state.get("gpu_util_pct", 0)
    log.debug(f"[v1.6.0 watcher] {task_id[:8]} gpu_util={gpu_util}%")

    threshold = 15
    idle_needed = 3  # 连续 3 次 (< 6s) 才判定 done, 避免抖动

    # v1.6.0-patch4: 不在 _tasks_lock 内做多轮等待, 改用 try-acquire 立刻返回
    # 之前每次 watcher tick 都持锁更新 idle_count, 导致 _tasks_lock 长时间被 watcher 持有
    # api_tasks_list / api_tasks_get / api_task_register 等也用 _tasks_lock, 全 hang
    #
    # 解决: 只在 idle_count 达到阈值时才持锁调用 _auto_task_done
    #       中间状态更新用 try-acquire (拿不到锁就跳过本次更新)
    with _tasks_lock:
        real_task = _tasks.get(task_id)
        if not real_task or real_task["state"] not in ("running", "queued"):
            return

        # 原子更新 idle_count 和 peak (持锁时间 < 1ms)
        if gpu_util < threshold:
            real_task["_beellama_idle_count"] = real_task.get("_beellama_idle_count", 0) + 1
        else:
            real_task["_beellama_idle_count"] = 0

        peak = real_task.get("_beellama_peak_util", 0)
        if gpu_util > peak:
            real_task["_beellama_peak_util"] = gpu_util

        # 只在判定完成时再调 _auto_task_done (它内部会再次持锁, 但很快)
        if real_task["_beellama_idle_count"] >= idle_needed:
            peak_util = real_task.get("_beellama_peak_util", 0)
            if peak_util < threshold:
                _auto_task_done(task_id, "failed", {
                    "auto_detected": True,
                    "method": "gpu_idle",
                    "reason": f"GPU util 始终 <{threshold}%, 任务可能没真正运行",
                    "peak_gpu_util": peak_util,
                })
            else:
                _auto_task_done(task_id, "success", {
                    "auto_detected": True,
                    "method": "gpu_idle",
                    "peak_gpu_util": peak_util,
                    "idle_duration_sec": real_task["_beellama_idle_count"] * 2,
                })


def _auto_task_done(task_id, status, result):
    """框架信号检测到的 task_done, 不走 audit_log 避免重复"""
    with _tasks_lock:
        t = _tasks.get(task_id)
        if not t or t["state"] not in ("running", "queued"):
            return  # 已处理过
        t["state"] = "done" if status == "success" else "failed"
        t["finished_at"] = time.time()
        t["result"] = result
        t["auto_detected"] = True
    audit_log("task_auto_done", f"{t['framework']}/{t['model']} task_id={task_id[:8]} {status}", "ok")
    log.info(f"[v1.5.0 watcher] auto task_done: {task_id} {status} ({t['framework']}/{t['model']})")


# ── 主程序 ───────────────────────────────────────────────────────
if __name__ == '__main__':
    import atexit
    atexit.register(shutdown)
    initialize()
    log.info(f"Framework Manager starting on port {PORT}")
    # v1.2.0: 启动推理队列 worker（append-only：仅此一行新增）
    _ensure_qrun_worker()
    # v1.3.0: 启动 VRAM 监测线程
    _ensure_vram_monitor()
    # v1.5.0: 启动任务自动检测 watcher (ComfyUI history / Ollama /api/ps)
    _ensure_task_watcher()
    app.run(host='0.0.0.0', port=PORT, threaded=True)