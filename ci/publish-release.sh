#!/usr/bin/env bash
# Publica ova/DevOps-Lab.ova como Release pública.
# Uso: ci/publish-release.sh <commit-sha>   (precisa de GH_TOKEN e REPO)
set -uo pipefail
SHA="$1"
LOG=release.log
exec > >(tee -a "$LOG") 2>&1
# shellcheck disable=SC2154  # rc é criado dentro do próprio trap
trap 'rc=$?; if [ $rc -ne 0 ]; then echo "::error title=release (linha $LINENO, código $rc)::$(tail -n 25 "$LOG" | sed "s/%/%25/g" | awk "{printf \"%s%%0A\", \$0}")"; fi' EXIT
set -x

ls -l ova/ compat/ || true
test -s ova/DevOps-Lab.ova
FILES=(ova/DevOps-Lab.ova ova/DevOps-Lab.ova.sha256)
if [ -s compat/DevOps-Lab.ova ]; then
  mv compat/DevOps-Lab.ova compat/DevOps-Lab-compat-vbox6.ova
  (cd compat && sha256sum DevOps-Lab-compat-vbox6.ova > DevOps-Lab-compat-vbox6.ova.sha256)
  FILES+=(compat/DevOps-Lab-compat-vbox6.ova compat/DevOps-Lab-compat-vbox6.ova.sha256)
fi
# ---------------------------------------------------------------- notas automáticas
# O que mudou (commits desde a última Release), resultado do teste e versões das ferramentas
PREV="$(gh api "repos/$REPO/releases/latest" --jq .tag_name 2>/dev/null || true)"
MUDOU=""
if [ -n "$PREV" ]; then
  MUDOU="$(gh api "repos/$REPO/compare/$PREV...$SHA" --jq '.commits[].commit.message | split("\n")[0]' 2>/dev/null \
    | grep -vE '^(Merge |Resultados do teste)' | sed 's/^/- /' | tail -n 30 || true)"
fi
[ -n "$MUDOU" ] || MUDOU="- Atualização de rotina (pacotes e ferramentas na versão mais nova)"

TESTE=""; VERSOES=""
if git fetch -q --depth 1 origin test-results 2>/dev/null; then
  RES="$(git show FETCH_HEAD:RESUMO.txt 2>/dev/null || true)"
  VL="$(git show FETCH_HEAD:verificar-lab.txt 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' || true)"
  if [ -n "$RES" ]; then
    OKS="$(grep -c '^\[OK\]' <<<"$RES" || true)"
    BOOT="$(grep -oE '= [0-9.]+s' <<<"$(grep '^Boot:' <<<"$RES")" | head -n1 | tr -d '= ' || true)"
    MEM="$(awk '/^Memória:/ {print $4; exit}' <<<"$RES")"
    MEMT="$(awk '/^Memória:/ {print $3; exit}' <<<"$RES")"
    TESTE="- $OKS checagens automáticas no VirtualBox: $(grep '^RESULTADO' <<<"$RES" | sed 's/^RESULTADO: //' | tr 'A-Z' 'a-z')
- Linux pronto em ${BOOT:-?} após ligar
- Memória em uso com o Jenkins ligado: ${MEM:-?} MB de ${MEMT:-?} MB"
  fi
  if [ -n "$VL" ]; then
    VERSOES="$(python3 - "$VL" <<'PY'
import re, sys
quero = ["Ubuntu", "VS Code", "Docker", "Docker Compose", "Git", "Terraform", "Python", "Jenkins", "Firefox"]
achou = {}
for linha in sys.argv[1].splitlines():
    m = re.match(r"\[OK\]\s+(.{16})(.*)", linha)
    if not m:
        continue
    nome, valor = m.group(1).strip(), m.group(2)
    v = re.findall(r"\d+(?:\.\d+)+", valor)
    if nome in quero and v:
        achou[nome] = v[-1] if nome == "Jenkins" else v[0]
print("\n".join(f"- {n}: {achou[n]}" for n in quero if n in achou))
PY
)"
  fi
fi

NOTES="VM Ubuntu 24.04 + XFCE com VS Code, Docker, Docker Compose, Git, Terraform, Python, Jenkins, Grafana, Prometheus, Uptime Kuma e Painel DevOps. Testada automaticamente no VirtualBox 7.2.

## Como instalar
1. Baixe **DevOps-Lab.ova** (abaixo).
2. VirtualBox > Arquivo > Importar Appliance.
3. Usuário: **aluno** / Senha: **devops**

Se já tem uma versão anterior, remova a antiga antes (botão direito > Remover > Excluir todos os arquivos).
Só use **DevOps-Lab-compat-vbox6.ova** se o seu VirtualBox for o antigo 6.1 e o arquivo principal não importar.

## O que mudou
$MUDOU"
[ -n "$TESTE" ] && NOTES="$NOTES

## Resultado do teste
$TESTE"
[ -n "$VERSOES" ] && NOTES="$NOTES

## Versões das ferramentas
$VERSOES"
NOTES="$NOTES

## Conferir o download (opcional)
O arquivo .sha256 traz a soma de verificação. No Windows (PowerShell): \`Get-FileHash DevOps-Lab.ova\`"
echo "$NOTES"

# Reaproveita uma Release vazia (de tentativa anterior) ou cria uma nova
TAG="$(gh release list -R "$REPO" --limit 20 --json tagName,isDraft --jq '.[].tagName' | head -n 1)"
if [ -n "$TAG" ] && [ "$(gh release view "$TAG" -R "$REPO" --json assets --jq '.assets | length')" = "0" ]; then
  echo "Reaproveitando a Release vazia $TAG"
else
  TAG="v$(date -u +%Y.%m.%d-%H%M)"
  gh release create "$TAG" -R "$REPO" --target "$SHA" --latest \
    --title "DevOps-Lab ($TAG)" --notes "$NOTES" || exit 3
fi

for try in 1 2 3; do
  if gh release upload "$TAG" -R "$REPO" --clobber "${FILES[@]}"; then
    break
  fi
  echo "upload falhou (tentativa $try)"; sleep 30
  [ "$try" = 3 ] && exit 4
done

gh release edit "$TAG" -R "$REPO" --latest --notes "$NOTES" || true

# Mantém só as 3 Releases mais novas (a atual + 2 anteriores), só depois que a nova já está publicada
MANTER=3
n=0
for t in $(gh api "repos/$REPO/releases?per_page=100" --jq 'sort_by(.created_at) | reverse | .[].tag_name'); do
  n=$((n + 1))
  [ "$t" = "$TAG" ] && continue
  if [ "$n" -gt "$MANTER" ]; then
    echo "Removendo Release antiga $t"
    gh release delete "$t" -R "$REPO" --cleanup-tag -y || true
  fi
done
gh release view "$TAG" -R "$REPO" --json assets --jq '.assets[] | "\(.name) \(.size)"'
set +x
echo "::notice title=release::https://github.com/$REPO/releases/download/$TAG/DevOps-Lab.ova"
