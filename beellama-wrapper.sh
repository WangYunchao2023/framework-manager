#!/bin/bash
# beellama-wrapper.sh — beellama.cpp 启动包装器
# Anbeeld fork (llama.cpp 9812) — DFlash 推测解码 + TurboQuant
#
# 从 /tmp/beella_model 读取配置，由 switch-inference.sh 写入
# 文件格式：<gguf_path> <dflash_enabled(0|1)> [turboquant_level(2|3|4)|'']
#
# 如果文件不存在，使用默认模型（qwen3.6-q3，无 DFlash，TurboQuant 3bit）
#
# 版本：1.0.2
#
# 更新日志:
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
  turbo_level=3
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
    # Qwen3-14B Q4_K_M: 9.3 GB GGUF, ~10 GB VRAM (40K 原生, YaRN → 131K)
    # v1.0.2: 131K + 4 并发 OOM; 改为 64K (YaRN 1.5x) + 2 并发, ~12 GB
    CTX_SIZE=65536
    PARALLEL=2
    KV_OVERRIDE=""
    ;;
  *gemma4*|*Gemma4*)
    # Gemma 4 26B A4B MoE: 16 GB GGUF, ~17 GB VRAM (256K 原生, MRCR 128K 弱)
    # v1.0.2: 131K + 4 并发 OOM; 改为 64K + 1 并发, ~18 GB
    CTX_SIZE=65536
    PARALLEL=1
    KV_OVERRIDE=""
    ;;
  *qwen3-vl*|*Qwen3-VL*|*vl*)
    # Qwen3-VL 8B: 5.8 GB GGUF, VRAM 宽裕 (262K 原生)
    # v1.0.2: 改为 128K + 2 并发, ~13 GB (多图并发友好)
    # 修复：添加缺失的 rope 元数据键 (Ollama 导出的 GGUF 缺少这些键)
    # --override-kv 语法：KEY=TYPE:VALUE (类型：int/float/bool/str), 逗号分隔多个
    CTX_SIZE=131072
    PARALLEL=2
    # dimension_count=128 (int), dimension_sections=1 (int), scaling.type=linear (str)
    # ✅ 修复：使用逗号分隔语法，避免重复参数警告
    KV_OVERRIDE="--override-kv qwen3vl.rope.dimension_count=int:128,qwen3vl.rope.dimension_sections=int:1,qwen3vl.rope.scaling.type=str:linear"
    ;;
  *sha256-83c54*|*sha256-6159*|*qwen3.6*|*Qwen3.6*|*Qwen3.6-27B*)
    # Qwen3.6 35B A3B MoE: 16.6 GB GGUF, ~17.5 GB VRAM (262K 原生, YaRN 1M+)
    # v1.0.2: 128K + 4 并发 OOM (21+ GB); 改为 128K + 1 并发, ~19 GB
    # 多模态：自动加载 mmproj（视觉编码器 CPU，不占显存）
    MM_PROJ="/home/wangyc/models/qwen3.6-35b/mmproj-BF16.gguf"
    CTX_SIZE=131072
    PARALLEL=1
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
    CTX_SIZE=32768
    PARALLEL=2
    KV_OVERRIDE=""
    ;;
esac

echo "📐 beellama: model=$(basename $gguf_path .gguf), ctx=$CTX_SIZE, parallel=$PARALLEL, dflash=$dflash_enabled, turbo=$turbo_level" >&2

# --- 构建 DFlash 参数 ---
dflash_args=""
if [ "$dflash_enabled" = "1" ] 2>/dev/null; then
  dflash_args="--spec-type dflash --spec-dflash-max-slots 1 --spec-dflash-cross-ctx 512"
fi

# --- 构建 TurboQuant 参数（KV cache 低位量化）---
turbo_args=""
if [ -n "$turbo_level" ] && [ "$turbo_level" -ge 2 ] && [ "$turbo_level" -le 4 ] 2>/dev/null; then
  # turbo2/3/4 = 2/3/4 bit KV cache
  turbo_args="--cache-type-k turbo${turbo_level} --cache-type-v turbo${turbo_level}"
fi

# 构建 mmproj 参数（多模态视觉投影，CPU 运行不占显存）
mmproj_args=""
if [ -n "$MM_PROJ" ] && [ -f "$MM_PROJ" ]; then
  mmproj_args="--mmproj $MM_PROJ --no-mmproj-offload"
  echo "🖼️ 多模态: 已加载 $MM_PROJ (CPU)" >&2
fi

# 启动 beellama (不用 exec 以便捕获退出码)
"$BEELLAMA_BIN" \
  -m "$gguf_path" \
  --host 0.0.0.0 \
  --port $DEFAULT_PORT \
  -ngl 99 \
  -c $CTX_SIZE \
  --parallel $PARALLEL \
  --no-kv-offload \
  --flash-attn on \
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