#!/bin/bash
# Blocks agent reads of .env files and shell commands that name them.
# .env.example stays allowed. Exit 2 blocks the action.
input=$(cat)
pattern='(^|[\s/"'\''=])\.env((\.(?!example)[A-Za-z0-9_-]+)|)(?![A-Za-z0-9_.-])'
if printf '%s' "$input" | grep -qP "$pattern"; then
  echo "Blocked: .env holds secrets. Use .env.example or ask the user to check a variable name." >&2
  exit 2
fi
echo '{ "permission": "allow" }'
exit 0
