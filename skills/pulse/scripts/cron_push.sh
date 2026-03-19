#!/bin/bash
# Pulse Cron Push — 每日简报定时推送
# 写入触发文件，由 HEARTBEAT 检测并执行 Pulse
#
# Cron 配置：
#   30 8  * * * /bin/bash ~/.openclaw/workspace-debug-master/aurora-skills/skills/pulse/scripts/cron_push.sh
#   30 18 * * * /bin/bash ~/.openclaw/workspace-debug-master/aurora-skills/skills/pulse/scripts/cron_push.sh

TRIGGER_FILE="$HOME/.openclaw/workspace-debug-master/.pulse_trigger"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo "$TIMESTAMP" > "$TRIGGER_FILE"
echo "[$TIMESTAMP] Pulse trigger written" >> "$HOME/.openclaw/workspace-debug-master/memory/pulse-cron.log"
