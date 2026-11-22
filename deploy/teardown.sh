#!/usr/bin/env bash
# Deletes the resource group, purges the soft deleted Foundry resource and lists what is left.
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/config.sh

az account show --query "{subscription:name}" -o table
if [ "$(az group exists -n "$RG")" = "true" ]; then
  az group delete -n "$RG" --yes
fi
az cognitiveservices account purge -n "$ACCOUNT" -g "$RG" -l "$LOCATION" 2>/dev/null || true

echo "== Remaining check"
echo "Resource group exists: $(az group exists -n "$RG")"
echo "Soft deleted accounts with this name:"
az cognitiveservices account list-deleted --query "[?name=='$ACCOUNT'].name" -o tsv
echo "Role assignments on the old scope are removed together with the resource."
