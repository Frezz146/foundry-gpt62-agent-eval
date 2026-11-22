# Shared names for deploy.sh and teardown.sh
LOCATION="swedencentral"
RG="alex-sc-rg-gpt62eval-dev"
ACCOUNT="alex-sc-ais-gpt62eval-dev"
CAPACITY=500   # thousands of tokens per minute per deployment
TAGS="project=blog-post-6 owner=alex env=dev"
# model:version, deployment name equals model name
MODELS="gpt-6.2-astra:2026-11-17 gpt-6-astra:2026-09-03 gpt-6.2-sol:2026-11-17 gpt-6.1-sol:2026-09-29"
