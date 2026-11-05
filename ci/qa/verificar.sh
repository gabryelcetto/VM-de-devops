#!/usr/bin/env bash
# Checagens rápidas de qualidade (rodam em ~10 s, antes de qualquer build):
# análise estática do Python e dos scripts, coerência da tela com o servidor e testes de unidade.
# Uso: bash ci/qa/verificar.sh   (precisa de: pip install pytest coverage ruff shellcheck-py)
set -euo pipefail
cd "$(dirname "$0")/../.."
echo "== ruff (Python)"
ruff check --select E9,F,B,PLE --ignore B008,B904 files/painel/painel.py files/monitoramento/preparar-kuma.py ci/qa/*.py tests/
echo "== shellcheck (scripts)"
shellcheck -S warning scripts/*.sh ci/*.sh ci/lab/*.sh ci/qa/*.sh ci/vm-tests/*.sh files/*.sh files/painel/*.sh .devcontainer/*.sh
echo "== tela x servidor"
python3 ci/qa/checar-frontend.py
echo "== testes de unidade (com cobertura de ramos)"
COVERAGE_FILE="${COVERAGE_FILE:-.coverage}" python3 -m coverage run -m pytest -q tests
COVERAGE_FILE="${COVERAGE_FILE:-.coverage}" python3 -m coverage report | tail -n 1
