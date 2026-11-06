#!/usr/bin/env bash
# Roda DENTRO da VM, como root e destacado (setsid -f): conta, por alguns segundos,
# quais timers do kernel disparam (o que acorda a VM parada) e quem os arma.
# Uso: rastrear-timers.sh <segundos> <saida>
SEG="${1:-10}"; SAIDA="${2:-/tmp/timers.txt}"
T=/sys/kernel/tracing; [ -d "$T/events/timer" ] || T=/sys/kernel/debug/tracing
mount | grep -q tracefs || mount -t tracefs nodev /sys/kernel/tracing 2>/dev/null
{
  echo 0 > "$T/tracing_on"; : > "$T/trace"; echo 4096 > "$T/buffer_size_kb"
  for e in hrtimer_expire_entry timer_expire_entry hrtimer_start; do echo 1 > "$T/events/timer/$e/enable"; done
  echo 1 > "$T/tracing_on"; sleep "$SEG"; echo 0 > "$T/tracing_on"
  for e in hrtimer_expire_entry timer_expire_entry hrtimer_start; do echo 0 > "$T/events/timer/$e/enable"; done
} 2>/dev/null
cp "$T/trace" /tmp/trace-bruto.txt 2>/dev/null
{
  echo "--- timers que dispararam (por segundo, função)"
  grep -E '(hrtimer|timer)_expire_entry:' /tmp/trace-bruto.txt | sed -nE 's/.*function=([^ ]+).*/\1/p' |
    sort | uniq -c | sort -rn | head -n 15 | awk -v s="$SEG" '{printf "%7.1f  %s\n", $1/s, $2}'
  echo "--- quem arma hrtimers (por segundo, processo e função)"
  grep 'hrtimer_start:' /tmp/trace-bruto.txt |
    sed -nE 's/^ *(.+)-[0-9]+ +\[[0-9]+\].*function=([^ ]+).*/\1 \2/p' |
    sort | uniq -c | sort -rn | head -n 15 | awk -v s="$SEG" '{c=$1; $1=""; printf "%7.1f %s\n", c/s, $0}'
  echo "--- disparos por CPU (por segundo)"
  grep -E 'hrtimer_expire_entry:' /tmp/trace-bruto.txt | sed -nE 's/.*\[([0-9]+)\].*/cpu\1/p' |
    sort | uniq -c | awk -v s="$SEG" '{printf "%7.1f  %s\n", $1/s, $2}'
} > "$SAIDA"
touch "$SAIDA.ok"
