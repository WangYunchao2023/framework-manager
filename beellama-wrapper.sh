#!/bin/bash
# beellama-wrapper.sh — beellama.cpp 启动包装器
# Anbeeld fork (llama.cpp 9812) — DFlash 推测解码 + TurboQuant
#
# 从 /tmp/beella_model 读取配置，由 switch-inference.sh 写入
# 文件格式：<gguf_path> <dflash_enabled(0|1)> [turboquant_level(2|3|4)|'']
#
# 如果文件不存在，使用默认模型（qwen3.6-q3，无 DFlash，TurboQuant 3bit）
#
# 版本：1.0.7
#
# 更新日志:
# - v1.0.7: 全面删除模型 case + 兜底 (与 framework-manager.py v1.1.4 联动)
#   - 删除 *qwen3-14b* / *gemma4* / *qwen3-vl* / *qwen3.6* 4 个 case
#   - 删除 *) 兑底 case
#   - ctx_size/parallel/ngpu_layers 三个值统一从 framework-manager.json 的
#     framework_params.beellama.models.<short_name> 读取
#   - 缺失任一字段 → 报错退出，提示去 WebUI 配置 (填 per-model 或恢复默认)
#   - mmproj 从同目录 mmproj-*.gguf 自动发现 (不再 case 判断)
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

# --- v1.0.7: 删除所有模型 case，统一从 per-model 配置读取 ---
# 所有 ctx/parallel/ngl 必须由 framework-manager WebUI 配置
# 路径: 「📦 模型专属参数」或「🎯 默认值」+ 「🔄 恢复默认」
gguf_basename=$(basename "$gguf_path")
FM_CONFIG="$HOME/.openclaw/config/framework-manager.json"
if [ ! -f "$FM_CONFIG" ]; then
  echo "❌ 配置文件不存在: $FM_CONFIG" >&2
  exit 1
fi

MODEL_NAME=$(basename "$gguf_path" .gguf)
# 提取 short_name (与 framework-manager.py _extract_short_model_name 逻辑一致):
#   Qwen_Qwen3.6-35B-A3B-Q3_K_M -> qwen3.6-q3
#   qwen3-14b-q4 -> qwen3-14b
#   qwen3-vl/Qwen3-VL-8B-Instruct-Q4_K_M -> qwen3-vl
#   gemma-4-26B-A4B-it-UD-Q4_K_M -> gemma-4-26b
MODEL_NAME_SHORT=$(python3 -c "
import re
name = '$MODEL_NAME'
m = re.match(r'Qwen_Qwen([0-9.]+)-([0-9]+B)-A([0-9]+B)', name)
if m: print(f'qwen{m.group(1)}-q{m.group(2)[0].lower()}'); exit()
if re.search(r'qwen3-?vl', name, re.IGNORECASE): print('qwen3-vl'); exit()
m = re.match(r'(qwen[0-9.]+(?:-[0-9]+b)?)-q[0-9]', name)
if m: print(m.group(1)); exit()
m = re.match(r'gemma-?([0-9]+)-?([0-9]+b)', name.lower())
if m: print(f'gemma-{m.group(1)}-{m.group(2)}'); exit()
print('')
" 2>/dev/null)

# 读取 per-model 参数 (兼容多种 key: basename 或 short_name)
read_pm() {
  local field="$1"
  python3 -c "
import json
c = json.load(open('$FM_CONFIG'))
m = c.get('framework_params',{}).get('beellama',{}).get('models',{})
for k in ('$MODEL_NAME', '$MODEL_NAME_SHORT'):
    v = m.get(k, {}).get('$field')
    if v: print(v); exit()
print('')
" 2>/dev/null
}

CTX_SIZE=$(read_pm ctx_size)
PARALLEL=$(read_pm parallel)
NGL=$(read_pm ngpu_layers)

# 验证: 三个必填
missing=""
[ -z "$CTX_SIZE" ] && missing="$missing ctx_size"
[ -z "$PARALLEL" ] && missing="$missing parallel"
[ -z "$NGL" ] && missing="$missing ngpu_layers"
if [ -n "$missing" ]; then
  echo "❌ 模型 $MODEL_NAME 缺少 per-model 配置:$missing" >&2
  echo "   请在 framework-manager WebUI (http://localhost:9528) 操作:" >&2
  echo "   • 「📦 模型专属参数」中填值并保存（手动指定）" >&2
  echo "   • 或「🎯 默认值」添加此模型后，「🔄 恢复默认」" >&2
  echo "   提示: 第一次添加新模型时，后二者更省事" >&2
  exit 1
fi
echo "📦 [$MODEL_NAME_SHORT] ctx=$CTX_SIZE, parallel=$PARALLEL, ngl=$NGL (来自 per-model)" >&2

# mmproj 自动发现: 同目录下的 mmproj-*.gguf
MM_PROJ=$(ls "$(dirname "$gguf_path")/mmproj-"*.gguf 2>/dev/null | head -1)

# 全局参数: turbo_level / flash_attn (从 FM_CONFIG 的 global 读)
fm_turbo=$(python3 -c "import json; c=json.load(open('$FM_CONFIG')); print(c.get('framework_params',{}).get('beellama',{}).get('global',{}).get('turbo_level',''))" 2>/dev/null)
fm_flash=$(python3 -c "import json; c=json.load(open('$FM_CONFIG')); print('on' if c.get('framework_params',{}).get('beellama',{}).get('global',{}).get('flash_attn',True) else 'off')" 2>/dev/null)
if [ -n "$fm_turbo" ]; then
  turbo_level="$fm_turbo"
  echo "📐 [全局] turbo_level=$turbo_level" >&2
fi
if [ -n "$fm_flash" ]; then
  FLASH_ATTN="$fm_flash"
  echo "📐 [全局] flash_attn=$FLASH_ATTN" >&2
fi

echo "📐 beellama: model=$MODEL_NAME, ctx=$CTX_SIZE, parallel=$PARALLEL, dflash=$dflash_enabled, turbo=$turbo_level" >&2

# --- 构建 DFlash 参数 ---
dflash_args=""
if [ "$dflash_enabled" = "1" ] 2>/dev/null; then
  dflash_args="--spec-type dflash --spec-dflash-max-slots 1 --spec-dflash-cross-ctx 512"
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