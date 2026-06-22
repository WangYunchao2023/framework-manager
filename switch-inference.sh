#!/bin/bash
# switch-inference.sh — Ollama ↔ beellama 推理引擎切换
# beellama = Anbeeld fork (llama.cpp 9459) — DFlash 推测解码 + TurboQuant
#
# 版本：1.0.3
#
# 更新日志:
# - v1.0.3: ollama 端 num_ctx 改为 per-model Modelfile 配置
#   移除 systemd override.conf 的 OLLAMA_CONTEXT_LENGTH 全局 32K
#   5 个常驻模型各有独立 num_ctx (对齐 beellama 端配置):
#     bge-m3:8K, qwen3:14b-64K, gemma4:26b-64K, qwen3.6-q3:128K, qwen3-vl:128K
#   Modelfile: /data/ollama/models/modelfiles/*.Modelfile
#   新 tag: bge-m3:ctx8k / qwen3:14b-ctx64k / gemma4:26b-ctx64k
#          / qwen3.6-q3:ctx128k / qwen3-vl:ctx128k
#   override.conf 仍保留: OLLAMA_KEEP_ALIVE=10m, OLLAMA_NUM_PARALLEL=1
# - v1.0.2: 与 framework-manager.py v1.0.2 同步发布
#   ollama 端参数 (ctx/parallel/keep_alive) 由 systemd override.conf 控制
#   beellama 端参数 (ctx/parallel) 由 beellama-wrapper.sh 控制
# - v1.0.0: 初始版本
#
# 用法:
#   ./switch-inference.sh status                             # 查看当前引擎
#   ./switch-inference.sh ollama                             # 切换到 Ollama
#   ./switch-inference.sh beellama [model] [df] [tq]        # 切换到 beellama
#   ./switch-inference.sh list                               # 可用模型列表
#
# 参数:
#   model  — 模型名 (默认: qwen3.6-q3)
#   df     — DFlash: 0=关, 1=开 (默认: 0)
#   tq     — TurboQuant KV 压缩: 2|3|4 bit (默认: 空=关)
#
# ⚠️ 已知问题: DFlash 在 RTX 2080 Ti (CC 7.5) + MoE 模型上崩溃
#    "failed to create shared DFlash drafter context" — DFlash 单独也崩
#    即使不开启 TurboQuant 也一样; 属于 MoE 或 CC 7.5 兼容性限制
#    建议: 用 TurboQuant (turbo3) 替代 DFlash, ~28 t/s 稳定运行

set -e

OLLAMA_PORT=11434
BEELLAMA_PORT=8080
BEELLAMA_BIN="/home/wangyc/beellama.cpp/build/bin/llama-server"
OLLAMA_BIN="/home/wangyc/.local/bin/ollama"
BEELLAMA_SERVICE="beellama.service"
MODEL_FILE="/tmp/beella_model"

MODELS=(
  "qwen3.6-q3|Qwen3.6-35B Q3_K_M|/home/wangyc/models/qwen3.6-35b/Qwen_Qwen3.6-35B-A3B-Q3_K_M.gguf|16 GB|~17 GB"
  "qwen3.6-uncensored|Qwen3.6-35B Uncensored HauhauCS Q3_K_P|/home/wangyc/models/qwen3.6-35b-uncensored/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-Q3_K_P.gguf|17.7 GB|~19 GB"
  "qwen3-14b|Qwen3-14B Q4_K_M|/home/wangyc/models/qwen3-14b/qwen3-14b-q4.gguf|9.3 GB|~10 GB"
  "gemma-4-26b|Gemma4 26B A4B|/data/ollama/models/blobs/$(ls /data/ollama/models/blobs/sha256-6159deaf76075* 2>/dev/null | head -1 | xargs basename)|16 GB|~17 GB"
  "qwen3-vl|Qwen3-VL 8B|/home/wangyc/models/qwen3-vl/qwen3-vl-8b.gguf|5.9 GB|~8 GB"
)

# beellama 可切换的模型
BEELLAMA_MODELS=("qwen3.6-q3" "qwen3.6-uncensored" "qwen3-vl" "gemma-4-26b" "qwen3-14b")

# v1.0.3: ollama 端 per-model tag (num_ctx 已固化在 Modelfile)
# 切换 ollama 端模型时优先用这些 tag (如: ollama run qwen3.6-q3:ctx128k)
OLLAMA_TAGS=(
  "bge-m3:ctx8k"
  "qwen3:14b-ctx64k"
  "gemma4:26b-ctx64k"
  "qwen3.6-q3:ctx128k"
  "qwen3-vl:ctx128k"
)

status() {
  local ollama_pid=$(pgrep -x ollama 2>/dev/null || echo "0")
  local beellama_pid=$(pgrep -f "beellama-wrapper" 2>/dev/null || echo "0")
  # 备选：如果 wrapper 退出但 llama-server 还在
  if [ "$beellama_pid" = "0" ]; then
    beellama_pid=$(pgrep -f "llama-server" 2>/dev/null | grep -v pgrep || echo "0")
  fi

  if [ "$ollama_pid" != "0" ]; then
    local ollama_tag=$(curl -s http://localhost:$OLLAMA_PORT/api/tags 2>/dev/null | python3 -c "
import sys,json
try:
    tags=json.load(sys.stdin).get('models',[])
    print(tags[0]['name'] if tags else 'none')
except: print('error')
" 2>/dev/null)
    echo "引擎: Ollama (port $OLLAMA_PORT)"
    echo "模型: $ollama_tag"
    echo "PID: $ollama_pid"
  elif [ "$beellama_pid" != "0" ]; then
    local cmdline=$(cat /proc/$beellama_pid/cmdline 2>/dev/null | tr '\0' ' ' || echo "")
    local model_path=$(echo "$cmdline" | grep -oP '(?<=-m\s)[^\s]+' || echo "unknown")
    local dflash_on=$(echo "$cmdline" | grep -o '\-\-spec-type dflash' || echo "")
    local tq_on=$(echo "$cmdline" | grep -oP 'turbo\d' || echo "")
    echo "引擎: beellama (port $BEELLAMA_PORT)"
    echo "GGUF: $(basename $model_path 2>/dev/null || echo 'unknown')"
    [ -n "$dflash_on" ] && echo "DFlash: ✅ 开启" || echo "DFlash: ❌ 关闭"
    [ -n "$tq_on" ] && echo "TurboQuant: ✅ ${tq_on}" || echo "TurboQuant: ❌ 关闭"
    echo "PID: $beellama_pid"
  else
    echo "引擎: 无"
  fi

  local gpu=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader 2>/dev/null | tr -d ' MiB' || echo "0")
  echo "VRAM: ${gpu} MiB / 22528 MiB"
}

list() {
  echo "可用模型:"
  printf "  %-15s %-25s %-8s %-8s\n" "名称" "描述" "大小" "VRAM"
  for m in "${MODELS[@]}"; do
    IFS='|' read -r key desc path size vram <<< "$m"
    printf "  %-15s %-25s %-8s %-8s\n" "$key" "$desc" "$size" "$vram"
  done
  echo ""
  echo "Ollama 端推荐 tag (v1.0.3 per-model num_ctx):"
  for t in "${OLLAMA_TAGS[@]}"; do
    echo "  $t"
  done
  echo ""
  echo "DFlash 建议:"
  echo "  ⚠️ RTX 2080 Ti (CC 7.5) + MoE 模型不支持 DFlash"
  echo "  ('failed to create shared DFlash drafter context')"
  echo "  请用 TurboQuant (turbo3) 替代 DFlash, Q3 ~28 t/s"
  echo ""
  echo "TurboQuant 建议:"
  echo "  2/3/4 = 2/3/4 bit KV cache 压缩, 省 VRAM"
  echo "  质量影响: turbo4 ≈ turbo3 > turbo2"
}

switch_to_ollama() {
  # 停 beellama（systemd service）
  if systemctl --user is-active "$BEELLAMA_SERVICE" >/dev/null 2>&1; then
    systemctl --user stop "$BEELLAMA_SERVICE"
    sleep 1
  fi
  # 清理残留进程
  pkill -f "beellama-wrapper" 2>/dev/null || true
  killall -9 llama-server 2>/dev/null || true
  sleep 1

  # 启 Ollama
  if ! pgrep -x ollama >/dev/null 2>&1; then
    echo "正在启动 Ollama..."
    systemctl --user start ollama.service
    local max_wait=30
    for i in $(seq 1 $max_wait); do
      curl -s http://localhost:$OLLAMA_PORT/api/tags >/dev/null 2>&1 && break
      sleep 1
    done
  fi
  echo "✅ 已切换到 Ollama (port $OLLAMA_PORT)"
}

switch_to_beellama() {
  local model_key="${1:-qwen3.6-q3}"
  local dflash_enabled="${2:-0}"
  local turbo_level="${3:-3}"

  # 检查是否为 beellama 不支持的模型
  local is_beellama_model=false
  for bm in "${BEELLAMA_MODELS[@]}"; do
    if [ "$model_key" = "$bm" ]; then
      is_beellama_model=true
      break
    fi
  done
  if [ "$is_beellama_model" != "true" ]; then
    echo "❌ $model_key 不支持 beellama"
    echo "   Beellama 可用模型: ${BEELLAMA_MODELS[*]}"
    echo "   Ollama native: ollama run qwen3.6-q3:ctx128k（请用 switch-inference.sh ollama）"
    exit 1
  fi

  # tq=0 或 "off" 视为关闭
  if [ "$turbo_level" = "0" ] || [ "$turbo_level" = "off" ] 2>/dev/null; then
    turbo_level=""
  fi

  # 解析模型路径
  local gguf_path=""
  local model_desc=""
  for m in "${MODELS[@]}"; do
    IFS='|' read -r key desc path size vram <<< "$m"
    if [ "$key" = "$model_key" ]; then
      gguf_path="$path"
      model_desc="$desc"
      break
    fi
  done

  if [ -z "$gguf_path" ]; then
    echo "❌ 未知模型: $model_key"
    echo "   Beellama 可用: ${BEELLAMA_MODELS[*]}"
    echo "   Ollama native: ollama run 模型名"
    exit 1
  fi

  if [ ! -f "$gguf_path" ]; then
    echo "❌ GGUF 文件不存在: $gguf_path"
    exit 1
  fi

  # 校验参数
  if [ "$dflash_enabled" != "0" ] && [ "$dflash_enabled" != "1" ]; then
    echo "⚠️ DFlash 参数: 0=关, 1=开, 已设为 0"
    dflash_enabled=0
  fi

  if [ -n "$turbo_level" ] && { [ "$turbo_level" -lt 2 ] || [ "$turbo_level" -gt 4 ]; } 2>/dev/null; then
    echo "⚠️ TurboQuant 级别 2-4, 已设为空（关）"
    turbo_level=""
  fi

  # 停 Ollama
  if systemctl --user is-active ollama.service >/dev/null 2>&1; then
    systemctl --user stop ollama.service
  fi
  pkill -x ollama 2>/dev/null || true
  sleep 1

  # 写入模型配置到 flag 文件
  mkdir -p "$(dirname "$MODEL_FILE")"
  echo "$gguf_path $dflash_enabled $turbo_level" > "$MODEL_FILE"

  # 停已有 beellama 进程并启动
  systemctl --user stop "$BEELLAMA_SERVICE" 2>/dev/null || true
  pkill -f "beellama-wrapper" 2>/dev/null || true
  killall -9 llama-server 2>/dev/null || true
  sleep 1

  systemctl --user start "$BEELLAMA_SERVICE"

  echo "正在加载 $model_desc..."
  [ "$dflash_enabled" = "1" ] && echo "  DFlash: ✅ 开启" || echo "  DFlash: ❌ 关闭"
  [ -n "$turbo_level" ] && echo "  TurboQuant: ✅ turbo${turbo_level}" || echo "  TurboQuant: ❌ 关闭"

  # 等待 health 端点就绪（含模型加载时间）
  local max_wait=150
  local waited=0
  echo -n "  等待就绪"
  while [ $waited -lt $max_wait ]; do
    code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$BEELLAMA_PORT/health 2>/dev/null || echo "000")
    if [ "$code" = "200" ]; then
      echo ""
      # 验证推理
      local infer_ok=$(curl -s http://localhost:$BEELLAMA_PORT/v1/chat/completions \
        -H "Content-Type: application/json" \
        -d '{"model":"test","messages":[{"role":"user","content":"1"}],"max_tokens":3}' \
        2>/dev/null | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    print('ok' if 'choices' in d else 'no:'+str(list(d.keys())))
except Exception as e:
    print('err:'+str(e))
" 2>/dev/null)
      echo "推理测试: $infer_ok"
      if echo "$infer_ok" | grep -q "^ok"; then
        echo "✅ beellama 就绪 — $model_desc (port $BEELLAMA_PORT)"
      else
        echo "⚠️ health 通过但推理异常，日志:"
        echo "   journalctl --user -u beellama.service -n 20 --no-pager"
      fi
      return 0
    fi
    echo -n "."
    sleep 2
    waited=$((waited + 2))
  done

  echo ""
  echo "⚠️ beellama 启动超时（${max_wait}s），请检查:"
  echo "   journalctl --user -u beellama.service -n 50 --no-pager"
  echo "   cat $MODEL_FILE"
  exit 1
}

case "${1:-status}" in
  status)   status ;;
  list)     list ;;
  ollama)   switch_to_ollama ;;
  beellama) switch_to_beellama "$2" "$3" "$4" ;;
  beella)   switch_to_beellama "$2" "$3" "$4" ;;  # 简写
  *)
    echo "用法: switch-inference.sh [status|list|ollama|beellama [model] [df] [tq]]"
    echo ""
    echo "   model:  ${BEELLAMA_MODELS[*]} (默认: qwen3.6-q3)"
    echo "   df:     0=关 DFlash (默认), 1=开 DFlash"
    echo "   tq:     2|3|4 = TurboQuant KV bit, 空=关"
    ;;
esac
