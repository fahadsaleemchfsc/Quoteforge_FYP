#!/usr/bin/env bash
# Deploy Salesforce custom metadata, substituting secret placeholders with
# values from quoteforge_v3/backend/.env at deploy time. The committed XML
# only ever contains placeholders (e.g. ${QF_SANDBOX_TENANT_PASSWORD}); the
# real values live in .env, which is gitignored.
#
# Usage:
#   scripts/deploy_metadata.sh <target-org-alias>
#
# Required env vars (loaded from quoteforge_v3/backend/.env):
#   QF_SANDBOX_TENANT_PASSWORD
#   QF_PROD_TENANT_PASSWORD
#
# Required CLI:
#   sf (Salesforce CLI)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/quoteforge_v3/backend/.env"
SF_PROJECT_DIR="${REPO_ROOT}/quoteforge_v3/salesforce_package"
CUSTOM_METADATA_REL_DIR="force-app/main/default/customMetadata"

# tenant-config XML files that use placeholder substitution.
SANDBOX_REL="${CUSTOM_METADATA_REL_DIR}/QuoteForge_Tenant_Config.Sandbox_Tenant.md-meta.xml"
PROD_REL="${CUSTOM_METADATA_REL_DIR}/QuoteForge_Tenant_Config.Prod_Tenant.md-meta.xml"

TARGET_ORG="${1:-}"
if [[ -z "${TARGET_ORG}" ]]; then
    echo "Usage: $0 <target-org-alias>" >&2
    exit 2
fi

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "ERROR: env file not found at ${ENV_FILE}" >&2
    exit 1
fi

# Load env vars from .env (KEY=VALUE lines, ignore comments and blanks).
set -a
# shellcheck disable=SC1090
source <(grep -E '^[A-Z_][A-Z0-9_]*=' "${ENV_FILE}")
set +a

for var in QF_SANDBOX_TENANT_PASSWORD QF_PROD_TENANT_PASSWORD; do
    if [[ -z "${!var:-}" ]]; then
        echo "ERROR: ${var} is not set in ${ENV_FILE}" >&2
        exit 1
    fi
done

for rel in "${SANDBOX_REL}" "${PROD_REL}"; do
    if [[ ! -f "${SF_PROJECT_DIR}/${rel}" ]]; then
        echo "ERROR: metadata file missing at ${SF_PROJECT_DIR}/${rel}" >&2
        exit 1
    fi
done

STAGING_DIR="$(mktemp -d -t qf-deploy-XXXXXX)"
trap 'rm -rf "${STAGING_DIR}"' EXIT

# Mirror the SF project structure under the staging dir, then substitute.
cp -R "${SF_PROJECT_DIR}/." "${STAGING_DIR}/"

# Substitute placeholders. Use Python for portable, safe replacement (avoids
# sed quoting issues when the password contains regex metachars).
STAGING_DIR="${STAGING_DIR}" \
SANDBOX_REL="${SANDBOX_REL}" \
PROD_REL="${PROD_REL}" \
QF_SANDBOX_TENANT_PASSWORD="${QF_SANDBOX_TENANT_PASSWORD}" \
QF_PROD_TENANT_PASSWORD="${QF_PROD_TENANT_PASSWORD}" \
python3 - <<'PY'
import os
from pathlib import Path

staging = Path(os.environ["STAGING_DIR"])
substitutions = [
    (staging / os.environ["SANDBOX_REL"], "${QF_SANDBOX_TENANT_PASSWORD}", os.environ["QF_SANDBOX_TENANT_PASSWORD"]),
    (staging / os.environ["PROD_REL"],    "${QF_PROD_TENANT_PASSWORD}",    os.environ["QF_PROD_TENANT_PASSWORD"]),
]
for path, needle, value in substitutions:
    text = path.read_text(encoding="utf-8")
    if needle not in text:
        raise SystemExit(
            f"placeholder {needle!r} not found in {path} — has the metadata "
            "been hardcoded with a real value? Aborting."
        )
    path.write_text(text.replace(needle, value), encoding="utf-8")
PY

echo "Substituted placeholders in staged metadata. Deploying to ${TARGET_ORG}..."

cd "${STAGING_DIR}"
sf project deploy start \
    --target-org "${TARGET_ORG}" \
    --source-dir "${CUSTOM_METADATA_REL_DIR}"

echo "Deploy complete."
