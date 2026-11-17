#!/usr/bin/env bash
# Usage: bash performance/k6/run.sh <script-name> <env-profile>
# Example: CATALOG=sample VUS=1 BURSTS=1 bash performance/k6/run.sh page-load-retail dev
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "Usage: bash performance/k6/run.sh <script-name> <env-profile>" >&2
  echo "Scripts: $(ls "$(dirname "$0")/scripts" | sed 's/\.js$//' | tr '\n' ' ')" >&2
  exit 1
fi

SCRIPT="$1"
PROFILE="$2"
HERE="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$HERE/../shared/env/.env.$PROFILE"

command -v k6 >/dev/null 2>&1 || { echo "k6 is not installed. See README, 'One-time setup'." >&2; exit 1; }
[ -f "$HERE/scripts/$SCRIPT.js" ] || { echo "No such script: scripts/$SCRIPT.js" >&2; exit 1; }
[ -f "$ENV_FILE" ] || { echo "Missing $ENV_FILE. Create it: cp performance/shared/env/.env.example performance/shared/env/.env.$PROFILE" >&2; exit 1; }

# Values in the env file override the command line for the keys they set.
set -a
# shellcheck disable=SC1090
source <(tr -d '\r' < "$ENV_FILE")
set +a

# Scripts run from scripts/ so REPORTS_DIR defaults to ../reports.
cd "$HERE/scripts"
mkdir -p "${REPORTS_DIR:-../reports}"
exec k6 run "$SCRIPT.js"
