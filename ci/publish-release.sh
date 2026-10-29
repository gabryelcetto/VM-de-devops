#!/usr/bin/env bash
# Publica ova/DevOps-Lab-UVV.ova como Release pública.
# Uso: ci/publish-release.sh <commit-sha>   (precisa de GH_TOKEN e REPO)
set -uo pipefail
SHA="$1"
LOG=release.log
exec > >(tee -a "$LOG") 2>&1
trap 'rc=$?; if [ $rc -ne 0 ]; then echo "::error title=release (linha $LINENO, código $rc)::$(tail -n 25 "$LOG" | sed "s/%/%25/g" | awk "{printf \"%s%%0A\", \$0}")"; fi' EXIT
set -x

ls -l ova/ compat/ || true
test -s ova/DevOps-Lab-UVV.ova
FILES=(ova/DevOps-Lab-UVV.ova ova/DevOps-Lab-UVV.ova.sha256)
if [ -s compat/DevOps-Lab-UVV.ova ]; then
  mv compat/DevOps-Lab-UVV.ova compat/DevOps-Lab-UVV-compat-vbox6.ova
  (cd compat && sha256sum DevOps-Lab-UVV-compat-vbox6.ova > DevOps-Lab-UVV-compat-vbox6.ova.sha256)
  FILES+=(compat/DevOps-Lab-UVV-compat-vbox6.ova compat/DevOps-Lab-UVV-compat-vbox6.ova.sha256)
fi
NOTES="VM Ubuntu 24.04 + XFCE com VS Code, Docker, Docker Compose, Git, Ansible, Terraform, Python e Jenkins. Testada automaticamente no VirtualBox 7.2.

- DevOps-Lab-UVV.ova: use este (VirtualBox 7.x).
- DevOps-Lab-UVV-compat-vbox6.ova: só se o VirtualBox for antigo (6.1) e o arquivo principal não importar.

Importar em: VirtualBox > Arquivo > Importar Appliance. Usuario: aluno / Senha: devops"

# Reaproveita uma Release vazia (de tentativa anterior) ou cria uma nova
TAG="$(gh release list -R "$REPO" --limit 20 --json tagName,isDraft --jq '.[].tagName' | head -n 1)"
if [ -n "$TAG" ] && [ "$(gh release view "$TAG" -R "$REPO" --json assets --jq '.assets | length')" = "0" ]; then
  echo "Reaproveitando a Release vazia $TAG"
else
  TAG="v$(date -u +%Y.%m.%d-%H%M)"
  gh release create "$TAG" -R "$REPO" --target "$SHA" --latest \
    --title "DevOps-Lab-UVV ($TAG)" --notes "$NOTES" || exit 3
fi

for try in 1 2 3; do
  if gh release upload "$TAG" -R "$REPO" --clobber "${FILES[@]}"; then
    break
  fi
  echo "upload falhou (tentativa $try)"; sleep 30
  [ "$try" = 3 ] && exit 4
done

gh release edit "$TAG" -R "$REPO" --latest --notes "$NOTES" || true
gh release view "$TAG" -R "$REPO" --json assets --jq '.assets[] | "\(.name) \(.size)"'
set +x
echo "::notice title=release::https://github.com/$REPO/releases/download/$TAG/DevOps-Lab-UVV.ova"
