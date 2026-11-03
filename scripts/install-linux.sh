#!/bin/sh
# Install the version-matched browse build on Linux x86_64, without touching
# the official agent-browser installation or its daemon namespace.
set -eu
umask 077
version=${1:?Usage: install-linux.sh VERSION}
printf '%s\n' "$version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || { echo 'Invalid version' >&2; exit 1; }
[ "$(uname -s)" = Linux ] && [ "$(uname -m)" = x86_64 ] || { echo 'Linux x86_64 required' >&2; exit 1; }
asset=agent-browser-browse-linux-x86_64.tar.gz
base="${XDG_DATA_HOME:-$HOME/.local/share}/agent-browser-browse"
bin_dir="${XDG_BIN_HOME:-$HOME/.local/bin}"
case "$base:$bin_dir" in /*:/*) ;; *) echo 'Install paths must be absolute' >&2; exit 1;; esac
mkdir -p "$base/versions" "$bin_dir"
chmod 700 "$base" "$base/versions"
stage=$(mktemp -d "$base/.stage.XXXXXXXX")
trap 'rm -rf "$stage"' EXIT HUP INT TERM
url="https://github.com/amxv/agent-browser-browse/releases/download/v$version"
curl --proto '=https' --tlsv1.2 -fsSL --retry 2 "$url/$asset" -o "$stage/$asset"
curl --proto '=https' --tlsv1.2 -fsSL --retry 2 "$url/SHA256SUMS" -o "$stage/SHA256SUMS"
expected=$(awk -v file="$asset" '$2==file {n++; hash=$1} END {if(n==1) print hash}' "$stage/SHA256SUMS")
printf '%s\n' "$expected" | grep -Eq '^[[:xdigit:]]{64}$' || { echo 'Missing/ambiguous SHA256' >&2; exit 1; }
[ "$(sha256sum "$stage/$asset" | awk '{print $1}')" = "$expected" ] || { echo 'SHA256 mismatch' >&2; exit 1; }
tar -tzf "$stage/$asset" | while IFS= read -r member; do
  member=${member#./}
  case "$member" in ''|agent-browser-browse-native|LICENSE.upstream|UPSTREAM_VERSION|UPSTREAM_COMMIT|PATCH_SHA256) ;; *) echo "Unexpected archive member: $member" >&2; exit 1;; esac
done
tar -tvzf "$stage/$asset" | awk 'substr($0,1,1)!="-" && substr($0,1,1)!="d" {bad=1} END {exit bad}' || { echo 'Nonregular archive entry' >&2; exit 1; }
mkdir "$stage/unpacked"
tar -xzf "$stage/$asset" -C "$stage/unpacked"
binary="$stage/unpacked/agent-browser-browse-native"
chmod 755 "$binary"
[ "$(cat "$stage/unpacked/UPSTREAM_VERSION")" = "$version" ] || { echo 'Version mismatch' >&2; exit 1; }
[ "$("$binary" --version)" = "agent-browser $version" ] || { echo 'Binary not runnable' >&2; exit 1; }
target="$base/versions/$version"
if [ ! -e "$target" ]; then mv "$stage/unpacked" "$target"; fi
if [ ! -f "$base/empty-config.json" ]; then printf '{}\n' > "$base/empty-config.json"; fi
cat > "$stage/agent-browser-browse" <<'WRAPPER'
#!/bin/sh
set -eu
export AGENT_BROWSER_NAMESPACE="${AGENT_BROWSER_NAMESPACE:-abb}"
export AGENT_BROWSER_CONFIG="${AGENT_BROWSER_CONFIG:-${XDG_DATA_HOME:-$HOME/.local/share}/agent-browser-browse/empty-config.json}"
exec "${XDG_DATA_HOME:-$HOME/.local/share}/agent-browser-browse/current/agent-browser-browse-native" "$@"
WRAPPER
chmod 755 "$stage/agent-browser-browse"
wrapper="$bin_dir/agent-browser-browse"
if [ -x "$wrapper" ] && [ -L "$base/current" ]; then
  sessions=$("$wrapper" session list --json) || { echo 'Existing sessions could not be inspected' >&2; exit 1; }
  printf '%s' "$sessions" | python3 -c 'import json,sys; v=json.load(sys.stdin); assert v["success"] and not v["data"]["sessions"]' || { echo 'Browsing sessions active; retry when idle' >&2; exit 1; }
fi
ln -s "$target" "$stage/new-current"
python3 - "$stage/new-current" "$base/current" <<'PY'
import os,sys
os.replace(sys.argv[1], sys.argv[2])
PY
mv "$stage/agent-browser-browse" "$wrapper"
echo "Installed agent-browser-browse $version. Add $bin_dir to PATH if needed."
