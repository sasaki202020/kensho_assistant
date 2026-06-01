#!/usr/bin/env bash
set -euo pipefail

echo "== WSL Hermes setup =="
export PATH="$HOME/.local/bin:$PATH"

need_cmds=()
for cmd in bash curl git; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    need_cmds+=("$cmd")
  fi
done

if ((${#need_cmds[@]} > 0)); then
  echo "不足しています: ${need_cmds[*]}"
  echo "WSL(Ubuntu) で次を実行してください:"
  echo "sudo apt update && sudo apt install -y curl git bash"
  exit 1
fi

if ! command -v hermes >/dev/null 2>&1; then
  echo "Hermes が見つかりません。uv tool で hermes-agent をインストールします。"
  if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
  fi
  uv tool install hermes-agent
fi

if [ -f "$HOME/.bashrc" ]; then
  # shellcheck disable=SC1090
  source "$HOME/.bashrc" || true
fi

if ! command -v hermes >/dev/null 2>&1; then
  echo "hermes コマンドを確認できませんでした。"
  echo "必要なら次を手動で実行してください:"
  echo "curl -LsSf https://astral.sh/uv/install.sh | sh"
  echo "export PATH=\"\$HOME/.local/bin:\$PATH\""
  echo "uv tool install hermes-agent"
  exit 1
fi

hermes --version || true

echo "次に WSL で実行:"
echo "hermes model"
echo "hermes auth add xai-oauth"
echo "hermes tools"
echo "hermes tools では X Search / x_search を ON にしてください。"
