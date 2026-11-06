#!/usr/bin/env bash
# Roda DENTRO da VM, desligado do guestcontrol (para não medir a si mesmo):
# espera $1 s, mede $2 s com a VM parada e grava o relatório em $3.
# CPU por processo (de /proc), interrupções por segundo (por tipo) e trocas de contexto.
ESPERA="${1:-15}"; JANELA="${2:-30}"; SAIDA="${3:-/tmp/medida.txt}"
rm -f "$SAIDA" "$SAIDA.ok"
foto() { # $1 = prefixo
  for p in /proc/[0-9]*; do
    # campo 2 pode ter espaços; pega utime/stime contando do fim do "(comm)"
    l="$(cat "$p/stat" 2>/dev/null)" || continue; r="${l##*) }"; read -r -a f <<<"$r"
    echo "${p#/proc/} $(( f[11] + f[12] )) $(tr -d ' ' < "$p/comm" 2>/dev/null) $(tr '\0' ' ' < "$p/cmdline" 2>/dev/null | cut -c1-60)"
  done > "/tmp/$1.proc"
  awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8+$9, $5+$6}' /proc/stat > "/tmp/$1.cpu"
  awk '/^ctxt/{print $2}' /proc/stat > "/tmp/$1.ctxt"
  awk 'NR>1{s=0; for(i=2;i<=NF;i++){ if($i ~ /^[0-9]+$/) s+=$i; else break }; n=$1; sub(":","",n); d=""; for(j=i;j<=NF;j++) d=d" "$j; print n, s, d}' /proc/interrupts > "/tmp/$1.irq"
}
sleep "$ESPERA"
foto m1; sleep "$JANELA"; foto m2
HZ=$(getconf CLK_TCK); NCPU=$(nproc)
{
  read -r t1 i1 < /tmp/m1.cpu; read -r t2 i2 < /tmp/m2.cpu
  echo "CPU ocupada (média dos $NCPU núcleos): $(awk -v a=$((t2-t1)) -v b=$((i2-i1)) 'BEGIN{printf "%.1f%%", (a-b)*100/a}')"
  echo "trocas de contexto/s: $(( ($(cat /tmp/m2.ctxt) - $(cat /tmp/m1.ctxt)) / JANELA ))"
  echo "--- processos (% de 1 núcleo)"
  awk -v hz="$HZ" -v j="$JANELA" 'NR==FNR{a[$1]=$2; next} ($1 in a){d=$2-a[$1]; if(d>0){pid=$1; $2=""; printf "%6.1f%%  %s\n", d*100/hz/j, $0}}' /tmp/m1.proc /tmp/m2.proc | sort -rn | head -n 15
  echo "--- interrupções/s"
  awk -v j="$JANELA" 'NR==FNR{a[$1]=$2; next} ($1 in a){d=$2-a[$1]; if(d>0){n=$1; $1=""; $2=""; printf "%7.0f  %s %s\n", d/j, n, $0}}' /tmp/m1.irq /tmp/m2.irq | sort -rn | head -n 12
} > "$SAIDA" 2>&1
touch "$SAIDA.ok"
