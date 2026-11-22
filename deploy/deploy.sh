#!/usr/bin/env bash
# Creates one Foundry (AIServices) resource with four Global Standard deployments.
# Pay per token, no base fee. Writes FOUNDRY_OPENAI_BASE_URL to .env.
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/config.sh

az account show --query "{subscription:name, tenantDefault:isDefault}" -o table

az group create -n "$RG" -l "$LOCATION" --tags $TAGS -o none
az cognitiveservices account create -n "$ACCOUNT" -g "$RG" -l "$LOCATION" \
  --kind AIServices --sku S0 --custom-domain "$ACCOUNT" --tags $TAGS --yes -o none

for entry in $MODELS; do
  model="${entry%%:*}"; version="${entry##*:}"
  echo "Deploying $model ($version)"
  az cognitiveservices account deployment create -n "$ACCOUNT" -g "$RG" \
    --deployment-name "$model" --model-name "$model" --model-version "$version" \
    --model-format OpenAI --sku-name GlobalStandard --sku-capacity "$CAPACITY" -o none
done

scope=$(az cognitiveservices account show -n "$ACCOUNT" -g "$RG" --query id -o tsv)
me=$(az ad signed-in-user show --query id -o tsv)
az role assignment create --assignee-object-id "$me" --assignee-principal-type User \
  --role "Cognitive Services OpenAI User" --scope "$scope" -o none

echo "FOUNDRY_OPENAI_BASE_URL=https://$ACCOUNT.openai.azure.com/openai/v1/" > .env
az cognitiveservices account deployment list -n "$ACCOUNT" -g "$RG" \
  --query "[].{name:name, version:properties.model.version, sku:sku.name, state:properties.provisioningState}" -o table
echo "Role assignments can take a few minutes to apply."
