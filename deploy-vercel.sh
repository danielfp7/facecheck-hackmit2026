#!/bin/zsh
# Publish the FaceCheck web pages to Vercel.
#
# Vercel hosts the pages only. The check runs on the FaceCheck server, which the pages call
# directly: a check uploads 8-80 MB of frames and Vercel caps a proxied body at 4.5 MB.
#
#   ./deploy-vercel.sh                 deploy a preview
#   ./deploy-vercel.sh --prod          deploy to the .vercel.app address
#
# The CLI is run through bun, since there is no node on this Mac.
set -euo pipefail
cd "$(dirname "$0")"
CLI="$HOME/.bun/install/global/node_modules/vercel/dist/index.js"
[ -s "$CLI" ] || { echo "Vercel CLI missing. Install it with:  bun add -g vercel"; exit 1; }
exec "$HOME/.bun/bin/bun" "$CLI" "$@"
