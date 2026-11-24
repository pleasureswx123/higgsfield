#!/usr/bin/env bash
set -euo pipefail
ACTIONLINT_VERSION=1.7.12
archive="actionlint_${ACTIONLINT_VERSION}_linux_amd64.tar.gz"
curl --fail --location --retry 3 "https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}/${archive}" --output "${RUNNER_TEMP}/${archive}"
echo "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8  ${RUNNER_TEMP}/${archive}" | sha256sum --check
tar -xzf "${RUNNER_TEMP}/${archive}" -C "$RUNNER_TEMP" actionlint
"$RUNNER_TEMP/actionlint" -color
