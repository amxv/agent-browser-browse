#!/bin/bash
# Install the Mac ARM64 browse build matching the local Homebrew agent-browser.
# This script is run by the pre-existing xyz.ashray.agent-browser-updater LaunchAgent.
set -euo pipefail
umask 077
export PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin

REPO=amxv/agent-browser-browse
VERSION="${1:-}"
BASE="$HOME/.local/share/agent-browser-browse"
VERSIONS="$BASE/versions"
CURRENT="$BASE/current"
CONFIG="$BASE/empty-config.json"
WRAPPER="$HOME/.local/bin/agent-browser-browse"
STATE="$HOME/Library/Application Support/agent-browser-updater"
ASSET=agent-browser-browse-darwin-arm64.tar.gz

log() { printf '[browse-install] %s\n' "$*"; }
fail() { log "ERROR: $*" >&2; exit 1; }

[ "$(uname -s)" = Darwin ] || fail 'Only macOS is supported'
[ "$(uname -m)" = arm64 ] || fail 'Only Apple Silicon is supported'
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "Invalid version: $VERSION"

mkdir -p "$VERSIONS" "$STATE" "$(dirname "$WRAPPER")"

# This empty config makes the browse binary independent of the user's ordinary
# ~/.agent-browser/config.json. The Rust patch carries the actual defaults.
if [ ! -f "$CONFIG" ]; then
  printf '{}\n' > "$CONFIG"
fi

# Browsing sessions live in an isolated namespace; no cross-wiring with Homebrew.
# Refresh the wrapper if the shared launcher policy changes. No auth profiles.
wrapper_tmp="${WRAPPER}.tmp.$$"
  cat > "$wrapper_tmp" <<'EOF'
#!/bin/bash
set -euo pipefail
export AGENT_BROWSER_NAMESPACE="${AGENT_BROWSER_NAMESPACE:-abb}"
export AGENT_BROWSER_CONFIG="${AGENT_BROWSER_CONFIG:-$HOME/.local/share/agent-browser-browse/empty-config.json}"
exec "$HOME/.local/share/agent-browser-browse/current/agent-browser-browse-native" "$@"
EOF
chmod 755 "$wrapper_tmp"
if [ ! -f "$WRAPPER" ] || ! /usr/bin/cmp -s "$wrapper_tmp" "$WRAPPER"; then
  /bin/mv -f "$wrapper_tmp" "$WRAPPER"
else
  /bin/rm -f "$wrapper_tmp"
fi

if [ -e "$CURRENT/agent-browser-browse-native" ] && [ -f "$CURRENT/UPSTREAM_VERSION" ]; then
  old_version="$(cat "$CURRENT/UPSTREAM_VERSION")"
  if [ "$old_version" = "$VERSION" ]; then
    existing="$CURRENT/agent-browser-browse-native"
    if [ -x "$existing" ] && [ "$("$existing" --version)" = "agent-browser $VERSION" ]; then
      log "Already current: $VERSION"
      exit 0
    fi
    fail "Installed version $VERSION failed binary integrity check"
  fi
fi

# Keep the previous working version until after a new download is verified.
# Don't switch a daemon's binary mid-session; the daily updater retries hourly.
if [ -L "$CURRENT" ] && [ -x "$WRAPPER" ]; then
  if ! sessions="$("$WRAPPER" session list --json)"; then
    fail 'Cannot inspect existing browsing sessions; will retry'
  fi
  if ! printf '%s' "$sessions" | /usr/bin/python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["success"]; sys.exit(0 if not d["data"]["sessions"] else 1)'; then
    fail 'Browsing session is active (or status is invalid); retry when idle'
  fi
fi

stage="$(mktemp -d "$STATE/browse-stage.XXXXXX")"
trap 'rm -rf "$stage"' EXIT
base_url="https://github.com/$REPO/releases/download/v$VERSION"
log "Fetching patched v$VERSION from $REPO"
if ! /usr/bin/curl --fail --location --silent --show-error --retry 3 --connect-timeout 12 --max-time 180 \
  "$base_url/$ASSET" --output "$stage/$ASSET"; then
  fail "Patched release v$VERSION is not published yet or download failed; retry later"
fi
if ! /usr/bin/curl --fail --location --silent --show-error --retry 3 --connect-timeout 12 --max-time 45 \
  "$base_url/SHA256SUMS" --output "$stage/SHA256SUMS"; then
  fail 'Could not fetch release checksums; keeping installed binary'
fi
(cd "$stage" && /usr/bin/shasum -a 256 --check SHA256SUMS) || fail 'Release checksum mismatch'
mkdir -p "$stage/unpacked"
/usr/bin/tar -xzf "$stage/$ASSET" -C "$stage/unpacked" || fail 'Could not extract archive'
new_binary="$stage/unpacked/agent-browser-browse-native"
[ -f "$new_binary" ] || fail 'Asset is missing its native executable'
chmod 755 "$new_binary"
[ "$(cat "$stage/unpacked/UPSTREAM_VERSION")" = "$VERSION" ] || fail 'Release version manifest mismatch'
[ "$("$new_binary" --version)" = "agent-browser $VERSION" ] || fail 'Compiled binary version mismatch'
/usr/bin/lipo -archs "$new_binary" | /usr/bin/grep -qx arm64 || fail 'Downloaded binary is not ARM64'
/usr/bin/codesign --verify "$new_binary" >/dev/null 2>&1 || fail 'Binary signature failed verification'

version_dir="$VERSIONS/$VERSION"
if [ ! -d "$version_dir" ]; then
  /bin/mv "$stage/unpacked" "$version_dir"
fi
[ -x "$version_dir/agent-browser-browse-native" ] || fail 'Installed binary is missing'

# os.replace swaps a symlink without dereferencing the old symlink-to-directory.
newlink="$BASE/.current.$$"
/bin/ln -s "$version_dir" "$newlink"
/usr/bin/python3 - "$newlink" "$CURRENT" <<'PY'
import os,sys
os.replace(sys.argv[1],sys.argv[2])
PY

log "Installed patched browse CLI v$VERSION (previous version retained)"
