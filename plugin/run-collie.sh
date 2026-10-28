#!/bin/sh
# Herdr runs plugin actions from its server, whose PATH often lacks herdr itself and uv's tool bin directory.
if [ -n "${HERDR_BIN_PATH:-}" ]; then PATH="$(dirname "$HERDR_BIN_PATH"):$PATH"; export PATH; fi
for c in "$(command -v collie 2>/dev/null)" "${UV_TOOL_BIN_DIR:-}/collie" "${XDG_BIN_HOME:-}/collie" "$HOME/.local/bin/collie"; do
  [ -n "$c" ] && [ -x "$c" ] && exec "$c" "$@"
done
echo "collie: not found; run 'uv tool install .' in $HERDR_PLUGIN_ROOT" >&2
exit 127
