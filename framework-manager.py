#!/usr/bin/env python3
"""framework-manager.py — 框架管理器 (Ollama/Beellama/ComfyUI)
REST API + WebUI, 端口 9528
支持：Ollama ↔ beellama ↔ comfyui 切换，模型热切换
CLI 模式：python3 framework-manager.py status|ollama|beellama|comfyui [model]

版本：1.1.3

更新日志:
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

import os, sys, json, time, subprocess, signal, threading, logging
from pathlib import Path
from datetime import datetime

import flask
from flask import Flask, request, jsonify, render_template_string

# ── 配置 ──────────────────────────────────────────────────────────
PORT = 9528
SWITCH_SCRIPT = os.path.expanduser("~/.openclaw/scripts/switch-inference.sh")
OLLAMA_SERVICE = "ollama.service"
BEELLAMA_SERVICE = "beellama.service"
COMFYUI_SERVICE = "comfyui.service"
OLLAMA_PORT = 11434
BEELLAMA_PORT = 8080
COMFYUI_PORT = 8188
LOG_FILE = os.path.expanduser("~/.openclaw/scripts/framework-manager-audit.log")
CONFIG_DIR = os.path.expanduser("~/.openclaw/config")
CONFIG_FILE = os.path.join(CONFIG_DIR, "framework-manager.json")

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

def get_ollama_models():
    """
    获取 Ollama 模型列表。
    Ollama 服务运行中 -> ollama list 实时拉取。
    Ollama 未运行 -> 从本地 manifest 目录回退，展示已下载的模型。
    """
    try:
        out = subprocess.check_output(["ollama", "list"], text=True, stderr=subprocess.DEVNULL)
        lines = out.strip().split("\n")[1:]
        models = []
        for line in lines:
            if line.strip():
                name = line.split()[0]
                # 排除 bge-m3 等非 LLM 模型
                if name.lower().startswith('bge-m3'):
                    continue
                models.append(name)
        return models
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
                    if name.lower().startswith('bge'):
                        continue
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
        return sorted(manifests)
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
    """扫描 ComfyUI 模型，支持子目录和多种模型类型"""
    model_dirs = [
        Path.home() / "ComfyUI" / "models" / "checkpoints",
        Path.home() / "ComfyUI" / "models" / "diffusers",  # Diffusers 格式
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
                gguf_filename = os.path.basename(gguf_path)
                if 'qwen3-14b' in gguf_filename.lower():
                    model_name = 'qwen3-14b'
                elif 'qwen3.6' in gguf_filename.lower() or 'qwen3.6-35b' in gguf_filename:
                    model_name = 'qwen3.6-q3'
                elif 'gemma-4-26b' in gguf_filename.lower() or 'gemma4' in gguf_filename.lower():
                    model_name = 'gemma4'
                elif 'qwen3-vl' in gguf_filename.lower():
                    model_name = 'qwen3-vl'
                else:
                    raw_name = os.path.splitext(gguf_filename)[0]
                    if len(raw_name) > 25:
                        raw_name = raw_name[:25] + '...'
                    model_name = raw_name

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

        # 1. 先卸载当前模型
        unload_ollama_models()

        _loading_state.update({"message": f"正在使用 Ollama 加载 {model_name}...", "progress": 40})

        # 2. 通过 /api/generate 加载模型到显存
        ollama_model_name = model_name
        if ':' not in model_name:
            ollama_model_name = model_name + ':latest'

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

        # 从完整路径提取短模型名
        short_model_name = model_name.split('/')[0] if '/' in model_name else model_name
        if short_model_name.endswith('.gguf'):
            short_model_name = short_model_name[:-5]
        if 'gemma' in short_model_name.lower():
            short_model_name = 'gemma4'
        if 'qwen3.6' in short_model_name.lower() or 'qwen3.6-35b' in short_model_name.lower():
            short_model_name = 'qwen3.6-q3'
        if 'qwen3-vl' in short_model_name.lower():
            short_model_name = 'qwen3-vl'

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
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

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

    ok, msg = load_model_for_framework(model)
    if ok:
        return jsonify({"status": "ok", "message": msg})
    return jsonify({"error": msg}), 400


def _extract_short_model_name(model_path):
    """从完整路径提取短别名 (用于 framework_params.beellama.models 的 key)
    qwen3.6-35b/Qwen_Qwen3.6-35B-A3B-Q3_K_M.gguf -> qwen3.6-q3
    qwen3-14b/qwen3-14b-q4.gguf -> qwen3-14b
    gemma-4-26B-A4B-it-UD-Q4_K_M -> gemma-4-26b
    """
    import re
    # 取 basename (去掉 .gguf)
    basename = model_path.split("/")[-1].replace(".gguf", "")
    # Qwen_Qwen3.6-35B-A3B-Q3_K_M -> qwen3.6-q3
    m = re.match(r"Qwen_Qwen([0-9.]+)-([0-9]+B)-A([0-9]+B)", basename)
    if m:
        return f"qwen{m.group(1)}-q{m.group(2)[0].lower()}"
    # qwen3-vl-8b -> qwen3-vl
    m = re.match(r"(qwen[0-9.]+-vl)-", basename)
    if m:
        return m.group(1)
    # qwen3-14b-q4 -> qwen3-14b
    m = re.match(r"(qwen[0-9.]+(?:-[0-9]+b)?)-q[0-9]", basename)
    if m:
        return m.group(1)
    # gemma-4-26B-... -> gemma-4-26b
    m = re.match(r"gemma-?([0-9]+)-?([0-9]+b)", basename.lower())
    if m:
        return f"gemma-{m.group(1)}-{m.group(2)}"
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
    ok, msg = load_model_for_framework(model_name)
    if ok:
        current_model = model_name
        audit_log("自动重载", f"model={model_name}", "ok")
        return jsonify({
            "status": "ok",
            "model": model_name,
            "params": config["framework_params"]["beellama"]["models"][model_name],
            "message": f"已应用新参数并加载 {model_name}"
        })
    else:
        return jsonify({
            "status": "partial",
            "error": f"beellama 已启动但模型加载失败: {msg}",
            "params": config["framework_params"]["beellama"]["models"][model_name]
        }), 500

@app.route("/api/models_by_framework")
def api_models_by_framework():
    """获取指定框架的模型列表（独立于当前框架）"""
    fw = request.args.get("framework", "beellama")
    if fw not in ["ollama", "beellama", "comfyui"]:
        return jsonify({"error": "无效的框架"}), 400
    models = get_framework_models(fw, force_refresh=True)
    return jsonify({"framework": fw, "models": models})

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
<title>框架管理器</title>
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
💡 留空表示使用 wrapper 硬编码默认
</p>
</div>
<div class="card">
<h2>🎯 模型 & 参数</h2>
<div class="form-row">
<div class="form-group"><label>模型</label><select id="model-select" style="min-width:200px"><option value="">— 加载模型到当前框架 —</option></select></div>
<button class="btn primary" onclick="loadModel()" id="btn-load-model">📥 加载模型</button>
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
<h2>📋 队列情况</h2>
<div style="font-size:1.1rem;font-family:monospace" id="queue-length">0 任务</div>
<div style="font-size:0.75rem;color:var(--text-dim);margin-top:4px;font-family:monospace" id="queue-details">无排队任务</div>
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
    // ⚙️ 同步 JS 全局 currentModel，供 loadModelParams() 使用
    if (data.model && data.model !== '—' && data.model !== '\u2014') {
      currentModel = data.model;
    } else {
      currentModel = null;
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
    document.getElementById('queue-length').textContent = (data.queue.total || 0) + ' 任务';
    // 更新队列详情
    const queueDetails = document.getElementById('queue-details');
    if (queueDetails && data.queue) {
      const byFw = data.queue.by_framework || {};
      const parts = [];
      for (const [fw, cnt] of Object.entries(byFw)) {
        parts.push(fw + ': ' + cnt);
      }
      queueDetails.textContent = parts.length > 0 ? parts.join(' | ') : '无排队任务';
    }
    // 状态轮询不写日志，避免刷屏
    updateModelSelect(data.available_models);
  } catch (e) {
    log('刷新失败：' + e.message, 'error');
  }
}
function updateModelSelect(models) {
  var sel = document.getElementById('model-select');
  var prevValue = sel.value;  // 保存用户当前选中的值
  sel.innerHTML = '<option value="">— 加载模型到当前框架 —</option>';
  models.forEach(function(m) {
    var opt = document.createElement('option');
    opt.value = m;
    opt.textContent = m;
    sel.appendChild(opt);
  });
  // 恢复之前选中的值（如果新列表里还有的话）
  if (prevValue) {
    sel.value = prevValue;
  }
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
    var fw = this.value;
    fetchJSON('/api/models_by_framework?framework=' + encodeURIComponent(fw))
      .then(function(r) {
        updateDefaultModelSelect(r.models || [], document.getElementById('default-model-select').value);
      })
      .catch(function(e) {
        log('获取框架模型列表失败：' + e.message, 'error');
      });
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
    document.getElementById('default-model-select').value = config.default_model || '';
    document.getElementById('idle-timeout-input').value = config.idle_timeout || 300;
    
    // 根据默认框架获取模型列表
    var modelsResp = await fetchJSON('/api/models_by_framework?framework=' + encodeURIComponent(defaultFw));
    updateDefaultModelSelect(modelsResp.models || [], config.default_model || '');
    
    log('默认设置已加载：框架=' + defaultFw + ' 模型=' + (config.default_model||'无') + ' 超时=' + (config.idle_timeout||300) + 's');
  } catch (e) {
    log('加载设置失败：' + e.message, 'error');
  }
}

function updateDefaultModelSelect(models, selectedModel) {
  var sel = document.getElementById('default-model-select');
  sel.innerHTML = '<option value="">(无)</option>';
  (models || []).forEach(function(m) {
    var opt = document.createElement('option');
    opt.value = m;
    // 对于 beellama 模型，显示短名称
    var displayName = m;
    if (m.includes('/')) {
      displayName = m.split('/')[0];
      if (displayName.includes('gemma')) displayName = 'gemma4';
      if (displayName.includes('qwen3.6')) displayName = 'qwen3.6-q3';
      if (displayName.includes('qwen3-vl')) displayName = 'qwen3-vl';
    }
    opt.textContent = displayName;
    if (m === selectedModel) opt.selected = true;
    sel.appendChild(opt);
  });
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
  if (!confirm('确定要清空 "' + currentModel + '" 的自定义参数并恢复默认值吗？\n\n恢复后：\n- 上下文：使用硬编码默认值 (通常 128K)\n- 并发数：使用硬编码默认值\n- GPU 层数：99\n\n将自动重启 beellama 并重载模型。')) return;
  
  const btn = document.getElementById('btn-reset-model-params');
  const overlay = document.getElementById('model-params-overlay');
  btn.disabled = true;
  btn.textContent = '⏳ 重置并重启中...';
  saveInProgress = true;
  if (overlay) overlay.style.display = 'flex';
  
  try {
    // 一个端点完成: 清空配置 → 停止 → 启动 → 重载
    const resp = await fetchJSON('/api/save_and_apply_model_params', 'POST', {
      model: currentModel,
      ctx_size: null,
      parallel: null,
      ngpu_layers: null
    });
    if (resp.status === 'ok') {
      document.getElementById('model-ctx-size').value = '';
      document.getElementById('model-parallel').value = '';
      document.getElementById('model-ngpu-layers').value = '';
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

</script>
</body>
</html>'''

# ── 主程序 ───────────────────────────────────────────────────────
if __name__ == '__main__':
    import atexit
    atexit.register(shutdown)
    initialize()
    log.info(f"Framework Manager starting on port {PORT}")
    app.run(host='0.0.0.0', port=PORT, threaded=True)