#!/usr/bin/env bash
# Deploy skills → ~/.claude/skills/ with placeholder substitution.
# One-way: repo is the source of truth, this overwrites the deployed copies.
#
# Usage:
#   bin/install.sh                # dry-run
#   bin/install.sh --apply        # write

set -euo pipefail
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ADQA_AGENT_DIR="$REPO_ROOT"

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

echo "ADQA_AGENT_DIR=$ADQA_AGENT_DIR"
echo

substitute() {
  sed -e "s|__ADQA_AGENT_DIR__|${ADQA_AGENT_DIR}|g"
}

deploy_file() {
  local src="$1" dest="$2"
  if [[ $APPLY -eq 1 ]]; then
    mkdir -p "$(dirname "$dest")"
    substitute < "$src" > "$dest"
    echo "wrote $dest"
  else
    echo "[dry-run] would write $dest  (from $src)"
  fi
}

for skill in askagent brew; do
  for src in "$REPO_ROOT/skills/$skill"/*.md; do
    name="$(basename "$src")"
    deploy_file "$src" "${HOME}/.claude/skills/${skill}/${name}"
  done
done

if [[ $APPLY -eq 0 ]]; then
  echo
  echo "dry-run only. Re-run with --apply to write."
fi
