#!/usr/bin/env bash
# Thin wrapper — sets this repo's identity, delegates to traast SDLC root script
export REPO="Traast/traast-api"
exec "$(dirname "$0")/../../scripts/run-agent.sh" "$@"
