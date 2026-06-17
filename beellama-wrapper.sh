#!/bin/bash
# beellama-wrapper.sh — beellama.cpp 启动包装器
# Anbeeld fork (llama.cpp 9812) — DFlash 推测解码 + TurboQuant
#
# 从 /tmp/beella_model 读取配置，由 switch-inference.sh 写入
# 文件格式：<gguf_path> <dflash_enabled(0|1)> [turboquant_level(2|3|4)|'']
#
# 如果文件不存在，使用默认模型（qwen3.6-q3，无 DFlash，TurboQuant 3bit）
#
# 版本：1.0.6
#
# 更新日志:
# - v1.0.6: 与 framework-manager.py v1.1.3 联动, 统一默认/推荐值
#   - qwen3-14b: PARALLEL 4 → 2 (与推荐值对齐, 2080Ti 22GB 保畺)
#   - 移除 *) 兑底 case (CTX=32K, PARALLEL=2) — 不再为未知模型提供 wrapper 默认值
#   - 未知模型现在 wrapper 报错退出, 提示用户去 WebUI 手动配置
# - v1.0.5: qwen3-vl 块去掉 KV_OVERRIDE 修复乱码 (GGUF 自带 dimension_sections=5, 错改成 1)
#   同时为 qwen3-vl 自动加载 mmproj (启用多模态)
#   背景: 切换到 unsloth 修复版 GGUF (sha256-541df240) 后，beellama 加载成功但输出乱码
#         根因: v1.0.2 时代为了修"key not found"强加的 override-kv 还在把 5 改成 1
# - v1.0.4: 全面解锁 ctx/并发 + KV 放回 VRAM (配合 turbo3 KV 量化)
#   原因: v1.0.2 用了 --no-kv-offload 把 KV 丢到 CPU 内存
#         22.5GB 卡虽紧，但 turbo3 (3-bit KV) 把 KV 缩到 1-2GB 后，GGUF+KV 可全部进 GPU
#   变化: 删 --no-kv-offload (KV 从 CPU 内存 → GPU VRAM)；并发/ctx 全面提升:
#     qwen3-14b:    64K+2  → 128K+4   (~13 GB, +吞吐)
#     gemma-4-26b:  64K+1  → 128K+1   (~17 GB, 256K 原生)
#     qwen3-vl-8b:  128K+2 → 128K+4   (~10 GB, 多图并发)
#     qwen3.6-35b:  128K+1 → 128K+2   (~20 GB, 临界)
#   turbo3 默认启用 (switch-inference.sh 默认 turbo3 + wrapper turbo_args 逻辑)
#   推理速度提升: KV 放 GPU 比 CPU 快 5-10x
#   质量影响: turbo3 3-bit KV 精度损失可忽略 (turbo4 ≈ turbo3 > turbo2)
#   回退路径: 改回 --no-kv-offload + 改 ctx/parallel 表即可 (1分钟回退)
# - v1.0.2: 按模型差异化设置 CTX_SIZE/PARALLEL
#   原因: 131K+parallel 4 在 22.5GB 物理 VRAM 下必 OOM (qwen3.6-35b 17GB 模型占大头)
#   qwen3-14b:    131K+4 → 64K+2   (~12 GB)
#   gemma-4-26b:  131K+4 → 64K+1   (~18 GB)
#   qwen3-vl-8b:  131K+4 → 128K+2  (~13 GB)
#   qwen3.6-35b:  131K+4 → 128K+1  (~19 GB)
# - v1.0.0: 初始版本, 全部用 131K+4 并发

BEELLAMA_BIN="/home/wangyc/beellama.cpp/build/bin/llama-server"
MODEL_FILE="/tmp/beella_model"
DEFAULT_GGUF="/home/wangyc/models/qwen3.6-35b/Qwen_Qwen3.6-35B-A3B-Q3_K_M.gguf"
DEFAULT_PORT=8080

# DFlash 已知问题：在 CC 7.5 (RTX 2080 Ti Turing) + MoE 模型上
# drafter context 创建失败 ("failed to create shared DFlash drafter context")
# 与 TurboQuant 无关; MoE (qwen35moe) 或 CC 7.5 兼容性限制
# 解决方案：默认不用 DFlash, 仅 TurboQuant
# 参考：journalctl --user -u beellama.service | grep "failed to create"

if [ -f "$MODEL_FILE" ]; then
  read -r gguf_path dflash_enabled turbo_level < "$MODEL_FILE"
  # ⚡ NONE 标记：仅激活服务占位，不加载任何模型
  if [ "$gguf_path" = "NONE" ]; then
    echo "🔌 beellama 已激活（无模型），等待 framework-manager 指定模型后重启" >&2
    sleep infinity
  fi
else
  gguf_path="$DEFAULT_GGUF"
  dflash_enabled=0
  turbo_level=1
fi

# 自动降级：如果 DFlash 导致过崩溃，强制关掉
if [ "$dflash_enabled" = "1" ] && [ -f "/tmp/beella_dflash_failed" ]; then
  echo "⚠️ DFlash 之前崩溃过，自动降级：禁用 DFlash" >&2
  dflash_enabled=0
fi

if [ ! -f "$gguf_path" ]; then
  echo "❌ GGUF 文件不存在：$gguf_path" >&2
  exit 1
fi

# --- 按模型自动设置参数 ---
# GGUF 文件名决定 num_ctx 和并发数
gguf_basename=$(basename "$gguf_path")
case "$gguf_basename" in
  *qwen3-14b*|*Qwen3-14B*|*qwen3:14*)
    # Qwen3-14B Q4_K_M: 9.3 GB GGUF (40K 原生, YaRN → 131K)
    # v1.0.2: 64K + 2 并发 (KV 在 CPU)
    # v1.0.4: 128K + 4 并发, turbo3 → 9.3 GB + 4 × 1GB KV ≈ 13 GB VRAM
    # v1.0.6: 并发 4 → 2 (与推荐值对齐, 保守 128K+2 ≈ 11 GB VRAM, 为上下文/吞吐留余量)
    CTX_SIZE=131072
    PARALLEL=2
    KV_OVERRIDE=""
    ;;
  *gemma4*|*Gemma4*)
    # Gemma 4 26B A4B MoE: 16 GB GGUF (256K 原生, MRCR 128K 弱)
    # v1.0.2: 64K + 1 并发 (KV 在 CPU)
    # v1.0.4: 128K + 1 并发, turbo3 → 16 GB + 1 GB KV ≈ 17 GB VRAM
    CTX_SIZE=131072
    PARALLEL=1
    KV_OVERRIDE=""
    ;;
  *qwen3-vl*|*Qwen3-VL*|*vl*)
    # Qwen3-VL 8B: 5.0 GB GGUF, VRAM 宽裕 (262K 原生)
    # v1.0.2: 128K + 2 并发 (KV 在 CPU)
    # v1.0.4: 128K + 4 并发, turbo3 → 5.0 GB + 4 × 1GB KV ≈ 10 GB VRAM
    # 多模态：自动加载 mmproj (unsloth 版 BF16 视觉编码器，CPU，不占显存)
    MM_PROJ=""
    CTX_SIZE=131072
    PARALLEL=4
    # v1.0.5: 删除 KV_OVERRIDE 修复乱码
    # 历史: v1.0.2 用 --override-kv 强补缺失的 rope key（旧 ed12a4 GGUF 缺 dimension_sections）
    # 后果: 新版 GGUF (unsloth 541df240) 自带 dimension_sections=5，override 把它错改成 1
    #       → tokenizer 错位，输出乱码 ("GG????")
    # 修复: 不再 override，让 llama-server 直接用 GGUF 自带的元数据
    # 旧 ed12a4 已被替换为 541df240（含完整 rope 元数据）
    KV_OVERRIDE=""
    ;;
  *sha256-83c54*|*sha256-6159*|*qwen3.6*|*Qwen3.6*|*Qwen3.6-27B*)
    turbo_level=""  # v1.0.5: turbo3 让 qwen3.6-35B (Q3_K_M MoE) token 采样失稳, 输出 ////
    # Qwen3.6 35B A3B MoE: 16.6 GB GGUF (262K 原生, YaRN 1M+)
    # v1.0.2: 128K + 1 并发 (KV 在 CPU), ~19 GB
    # v1.0.4: 128K + 2 并发, turbo3 → 16.6 GB + 2 × 1.9 GB KV ≈ 20.4 GB VRAM (临界)
    # 多模态：自动加载 mmproj（视觉编码器 CPU，不占显存）
    MM_PROJ="/home/wangyc/models/qwen3.6-35b/mmproj-BF16.gguf"
    CTX_SIZE=131072
    PARALLEL=1  # v1.0.9: 2080Ti 22GB 保命，改 parallel=1 (排队执行，显存~20GB 安全)
    KV_OVERRIDE=""
    # ✅ 修复：如果符号链接损坏，自动下载 mmproj
    if [ ! -f "$MM_PROJ" ]; then
      echo "⏳ mmproj 文件不存在或链接损坏，尝试下载..." >&2
      mkdir -p /home/wangyc/models/qwen3.6-35b
      huggingface-cli download unsloth/Qwen3.6-35B-A3B-GGUF \
        --include '*mmproj*' \
        --local-dir /home/wangyc/models/qwen3.6-35b \
        --quiet 2>/dev/null
      # 如果下载成功，更新 MM_PROJ 指向新下载的文件
      found_mmproj=$(ls /home/wangyc/models/qwen3.6-35b/mmproj-*.gguf 2>/dev/null | head -1)
      if [ -n "$found_mmproj" ]; then
        MM_PROJ="$found_mmproj"
        echo "✅ mmproj 已下载: $MM_PROJ" >&2
      else
        echo "⚠️ mmproj 下载失败，视觉功能不可用" >&2
      fi
    fi
    ;;
  *)
    # v1.0.6: 移除未知模型兑底默认值 (32K+2)
    # 原因: 避免 wrapper “自作主张”提供可能不合适的 ctx/parallel
    # 后果: 未知模型加载失败, 用户需去 framework-manager WebUI 的“模型专属参数”手动配置
    echo "❌ 未知模型，无法提供默认参数: $gguf_basename" >&2
    echo "   请在 framework-manager WebUI (http://localhost:9528) 的“模型专属参数”卡中手动配置 ctx/parallel/ngl" >&2
    echo "   或在 wrapper 中为该模型添加 case" >&2
    exit 1
    ;;
esac

echo "📐 beellama: model=$(basename $gguf_path .gguf), ctx=$CTX_SIZE, parallel=$PARALLEL, dflash=$dflash_enabled, turbo=$turbo_level" >&2

# --- 构建 DFlash 参数 ---
dflash_args=""
if [ "$dflash_enabled" = "1" ] 2>/dev/null; then
  dflash_args="--spec-type dflash --spec-dflash-max-slots 1 --spec-dflash-cross-ctx 512"
fi

# --- 构建 TurboQuant / per-model 参数（v1.0.8） ---
# 从 framework-manager 读取全局和 per-model 配置
turbo_args=""
FM_CONFIG="$HOME/.openclaw/config/framework-manager.json"
MODEL_NAME=$(basename "$gguf_path" .gguf)
# 提取核心短名 (用于查找配置): 
#   Qwen_Qwen3.6-35B-A3B-Q3_K_M -> qwen3.6-q3
#   qwen3-14b-q4 -> qwen3-14b
#   gemma-4-26B-A4B-it-UD-Q4_K_M -> gemma-4-26b
MODEL_NAME_SHORT=$(python3 -c "
import re
name = '$MODEL_NAME'
m = re.match(r'Qwen_Qwen([0-9.]+)-([0-9]+B)-A([0-9]+B)', name)
if m: print(f'qwen{m.group(1)}-q{m.group(2)[0].lower()}'); exit()
m = re.match(r'(qwen[0-9.]+-vl)-', name)
if m: print(m.group(1)); exit()
m = re.match(r'(qwen[0-9.]+(?:-[0-9]+b)?)-q[0-9]', name)
if m: print(m.group(1)); exit()
m = re.match(r'gemma-?([0-9]+)-?([0-9]+b)', name.lower())
if m: print(f'gemma-{m.group(1)}-{m.group(2)}'); exit()
print('')
" 2>/dev/null)

if [ -f "$FM_CONFIG" ]; then
  # 读取全局参数
  fm_turbo=$(python3 -c "import json; c=json.load(open('$FM_CONFIG')); print(c.get('framework_params',{}).get('beellama',{}).get('global',{}).get('turbo_level',''))" 2>/dev/null)
  fm_flash=$(python3 -c "import json; c=json.load(open('$FM_CONFIG')); print('on' if c.get('framework_params',{}).get('beellama',{}).get('global',{}).get('flash_attn',True) else 'off')" 2>/dev/null)
  
  # 读取 per-model 参数 (兼容多种 key: basename, 完整短名, 或带 -q3/-q4 后缀)
  # 先尝试 MODEL_NAME 和 MODEL_NAME_SHORT, 都找不到则用 Python 模糊匹配
  fm_ctx=$(python3 -c "import json; c=json.load(open('$FM_CONFIG')); m=c.get('framework_params',{}).get('beellama',{}).get('models',{}); v=m.get('$MODEL_NAME',{}).get('ctx_size') or m.get('$MODEL_NAME_SHORT',{}).get('ctx_size'); print(v if v else '')" 2>/dev/null)
  fm_parallel=$(python3 -c "import json; c=json.load(open('$FM_CONFIG')); m=c.get('framework_params',{}).get('beellama',{}).get('models',{}); v=m.get('$MODEL_NAME',{}).get('parallel') or m.get('$MODEL_NAME_SHORT',{}).get('parallel'); print(v if v else '')" 2>/dev/null)
  fm_ngl=$(python3 -c "import json; c=json.load(open('$FM_CONFIG')); m=c.get('framework_params',{}).get('beellama',{}).get('models',{}); v=m.get('$MODEL_NAME',{}).get('ngpu_layers') or m.get('$MODEL_NAME_SHORT',{}).get('ngpu_layers'); print(v if v else '')" 2>/dev/null)
  
  # 应用全局参数（如果 per-model 未设置）
  if [ -n "$fm_turbo" ]; then
    turbo_level="$fm_turbo"
    echo "📐 [全局] turbo_level=$turbo_level" >&2
  fi
  if [ -n "$fm_flash" ]; then
    FLASH_ATTN="$fm_flash"
    echo "📐 [全局] flash_attn=$FLASH_ATDN" >&2
  fi
  
  # 应用 per-model 参数（覆盖默认值）
  if [ -n "$fm_ctx" ]; then
    CTX_SIZE="$fm_ctx"
    echo "📦 [$MODEL_NAME] ctx_size=$CTX_SIZE" >&2
  fi
  if [ -n "$fm_parallel" ]; then
    PARALLEL="$fm_parallel"
    echo "📦 [$MODEL_NAME] parallel=$PARALLEL" >&2
  fi
  if [ -n "$fm_ngl" ]; then
    NGL="$fm_ngl"
    echo "📦 [$MODEL_NAME] ngpu_layers=$NGL" >&2
  fi
fi

# 构建 KV 参数量化参数
turbo_args=""
if [ -n "$turbo_level" ] && [ "$turbo_level" = "q8_0" ]; then
  turbo_args="--cache-type-k q8_0 --cache-type-v q8_0"
elif [ -n "$turbo_level" ] && [ "$turbo_level" -ge 2 ] && [ "$turbo_level" -le 4 ] 2>/dev/null; then
  turbo_args="--cache-type-k turbo${turbo_level} --cache-type-v turbo${turbo_level}"
fi

# 构建 mmproj 参数（多模态视觉投影，CPU 运行不占显存）
mmproj_args=""
if [ -n "$MM_PROJ" ] && [ -f "$MM_PROJ" ]; then
  mmproj_args="--mmproj $MM_PROJ --no-mmproj-offload"
  echo "🖼️ 多模态: 已加载 $MM_PROJ (CPU)" >&2
fi

# 启动 beellama (使用动态参数)
NG_LAYERS=${NGL:-99}
FLASH_MODE=${FLASH_ATTN:-on}

echo "🚀 启动参数：ctx=$CTX_SIZE, parallel=$PARALLEL, ngl=$NG_LAYERS, flash=$FLASH_MODE, turbo=$turbo_level" >&2

"$BEELLAMA_BIN" \
  -m "$gguf_path" \
  --host 0.0.0.0 \
  --port $DEFAULT_PORT \
  -ngl $NG_LAYERS \
  -c $CTX_SIZE \
  --parallel $PARALLEL \
  --flash-attn $FLASH_MODE \
  --reasoning off \
  --reasoning-format none \
  $dflash_args \
  $turbo_args \
  $mmproj_args \
  ${KV_OVERRIDE:+$KV_OVERRIDE}

EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ] && [ "$dflash_enabled" = "1" ]; then
  # DFlash 崩溃：写入标记，下次自动降级
  echo "❗ beellama 退出码 $EXIT_CODE, 疑似 DFlash 崩溃" >&2
  date > /tmp/beella_dflash_failed
fi
exit $EXIT_CODE