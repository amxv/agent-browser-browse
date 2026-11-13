#!/bin/bash
# Install the Mac ARM64 browse build; used by the existing daily LaunchAgent.
set -euo pipefail
umask 077
export PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
VERSION="${1:-}"
BASE="$HOME/.local/share/agent-browser-browse"
BIN_DIR="$HOME/.local/bin"
ASSET=agent-browser-browse-darwin-arm64.tar.gz
[ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ] || { echo 'Apple Silicon macOS required' >&2; exit 1; }

log() { printf '[browse-install] %s\n' "$*"; }
fail() { log "ERROR: $*" >&2; exit 1; }

[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "Invalid version: $VERSION"
case "$BASE" in /*) ;; *) fail 'Install paths must be absolute';; esac
case "$BIN_DIR" in /*) ;; *) fail 'Install paths must be absolute';; esac
VERSIONS="$BASE/versions"
CURRENT="$BASE/current"
CONFIG="$BASE/empty-config.json"
WRAPPER="$BIN_DIR/agent-browser-browse"
[ ! -L "$BASE" ] && [ ! -L "$VERSIONS" ] || fail 'Install directories must not be symlinks'
mkdir -p "$VERSIONS" "$BIN_DIR"
lock="$BASE/.install-lock"
mkdir "$lock" 2>/dev/null || fail 'Another installer is running; retry when idle'
stage=""
wrapper_tmp=""
cleanup() {
  [ -z "$stage" ] || rm -rf "$stage"
  [ -z "$wrapper_tmp" ] || rm -f "$wrapper_tmp"
  rmdir "$lock" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
stage="$(mktemp -d "$BASE/.stage.XXXXXXXX")"

# Refuse to replace custom launchers, config links, or unrelated current links.
[ ! -L "$WRAPPER" ] || fail 'The browsing command is a custom symlink'
[ ! -L "$CONFIG" ] || fail 'The browse config is a symlink; leaving it untouched'
[ ! -e "$CONFIG" ] || [ -f "$CONFIG" ] || fail 'The browse config is not a file'
cat > "$stage/wrapper" <<'WRAPPER'
#!/bin/bash
set -euo pipefail
export AGENT_BROWSER_NAMESPACE="${AGENT_BROWSER_NAMESPACE:-abb}"
export AGENT_BROWSER_CONFIG="${AGENT_BROWSER_CONFIG:-$HOME/.local/share/agent-browser-browse/empty-config.json}"
exec "$HOME/.local/share/agent-browser-browse/current/agent-browser-browse-native" "$@"
WRAPPER
if [ -e "$WRAPPER" ]; then
  [ -f "$WRAPPER" ] && cmp -s "$stage/wrapper" "$WRAPPER" || fail 'The browsing command is customized; leaving it untouched'
fi
if [ -L "$CURRENT" ]; then
  python3 -I - "$CURRENT" "$VERSIONS" <<'PY' || fail 'Current installation points outside the managed versions'
import pathlib, re, sys
current, versions = map(pathlib.Path, sys.argv[1:])
target = current.resolve(strict=True)
assert target.parent == versions.resolve(strict=True)
assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", target.name)
assert target.is_dir() and not (versions / target.name).is_symlink()
PY
elif [ -e "$CURRENT" ]; then
  fail 'Current installation is not a managed symlink'
fi

check_sessions() {
  if [ -L "$CURRENT" ]; then
    existing="$CURRENT/agent-browser-browse-native"
    [ -x "$existing" ] || fail 'Existing binary cannot inspect browsing sessions'
    python3 -I - "$existing" "$CONFIG" <<'PY' || fail 'Browsing sessions are active or status is invalid; retry when idle'
import json, os, subprocess, sys
env = {key: value for key, value in os.environ.items() if not key.startswith("AGENT_BROWSER_")}
env.update(AGENT_BROWSER_NAMESPACE="abb", AGENT_BROWSER_CONFIG=sys.argv[2])
result = subprocess.run([sys.argv[1], "session", "list", "--json"], env=env, text=True, capture_output=True, timeout=30, check=True)
data = json.loads(result.stdout)
assert data.get("success") is True and isinstance(data["data"]["sessions"], list) and not data["data"]["sessions"]
PY
  fi
}
check_sessions

base_url="https://github.com/amxv/agent-browser-browse/releases/download/v$VERSION"
log "Fetching patched v$VERSION"
curl --proto '=https' --tlsv1.2 --fail --location --silent --show-error --retry 3 --connect-timeout 12 --max-time 180 \
  "$base_url/$ASSET" --output "$stage/$ASSET" || fail 'Release download failed; keeping installed binary'
curl --proto '=https' --tlsv1.2 --fail --location --silent --show-error --retry 3 --connect-timeout 12 --max-time 45 \
  "$base_url/SHA256SUMS" --output "$stage/SHA256SUMS" || fail 'Checksum download failed; keeping installed binary'

# A multi-platform manifest is valid. Require exactly one checksum for this asset.
# Extract only the five regular files that this project packages, never links.
python3 -I - "$stage" "$ASSET" "$VERSION" <<'PY' || fail 'Release checksum, archive, or provenance validation failed'
import hashlib, pathlib, re, sys, tarfile
stage = pathlib.Path(sys.argv[1])
asset, version = sys.argv[2:]
rows = [line.split() for line in (stage / "SHA256SUMS").read_text().splitlines()]
rows = [row for row in rows if len(row) >= 2 and row[1] == asset]
assert len(rows) == 1 and len(rows[0]) == 2 and re.fullmatch(r"[a-fA-F0-9]{64}", rows[0][0]), "missing/duplicate checksum"
assert hashlib.sha256((stage / asset).read_bytes()).hexdigest() == rows[0][0].lower(), "checksum mismatch"
names = {"agent-browser-browse-native", "LICENSE.upstream", "UPSTREAM_VERSION", "UPSTREAM_COMMIT", "PATCH_SHA256"}
unpacked = stage / "unpacked"
unpacked.mkdir()
seen = set()
with tarfile.open(stage / asset, "r:gz") as archive:
    for member in archive:
        name = member.name.removeprefix("./")
        if name in ("", ".") and member.isdir():
            continue
        assert name in names and name not in seen and member.isfile(), "unexpected/duplicate/nonregular archive member"
        assert 0 <= member.size <= (512 * 1024 * 1024 if name == "agent-browser-browse-native" else 1024 * 1024), "oversized archive member"
        seen.add(name)
        stream = archive.extractfile(member)
        assert stream is not None
        with (unpacked / name).open("xb") as output:
            while chunk := stream.read(1024 * 1024):
                output.write(chunk)
assert seen == names, "missing archive member"
assert (unpacked / "UPSTREAM_VERSION").read_text().strip() == version, "version mismatch"
assert re.fullmatch(r"[a-fA-F0-9]{40}", (unpacked / "UPSTREAM_COMMIT").read_text().strip()), "invalid source commit"
assert re.fullmatch(r"[a-fA-F0-9]{64}", (unpacked / "PATCH_SHA256").read_text().strip()), "invalid patch hash"
PY
new_binary="$stage/unpacked/agent-browser-browse-native"
[ "$(lipo -archs "$new_binary")" = arm64 ] || fail 'Downloaded binary is not ARM64'
codesign --verify "$new_binary" >/dev/null 2>&1 || fail 'Binary signature failed verification'
chmod 755 "$new_binary"
[ "$("$new_binary" --version)" = "agent-browser $VERSION" ] || fail 'Compiled binary version mismatch'

# Never activate an old, unverified directory just because its version matches.
version_dir="$VERSIONS/$VERSION"
if [ -e "$version_dir" ] || [ -L "$version_dir" ]; then
  [ -d "$version_dir" ] && [ ! -L "$version_dir" ] || fail 'Existing version is not a managed directory'
  python3 -I - "$stage/unpacked" "$version_dir" <<'PY' || fail 'Existing version differs from the verified release; leaving it untouched'
import pathlib, sys
new, old = map(pathlib.Path, sys.argv[1:])
assert {p.name for p in new.iterdir()} == {p.name for p in old.iterdir()}
for source in new.iterdir():
    target = old / source.name
    assert target.is_file() and not target.is_symlink() and source.read_bytes() == target.read_bytes()
assert (old / "agent-browser-browse-native").stat().st_mode & 0o111
PY
else
  # Staging under BASE keeps this rename on the same filesystem.
  mv "$stage/unpacked" "$version_dir"
fi
check_sessions

# The wrapper is constant across versions. Preserve any existing regular config.
if [ ! -e "$CONFIG" ]; then
  (set -o noclobber; printf '{}\n' > "$CONFIG") || fail 'Could not create browse config'
fi
if [ ! -e "$WRAPPER" ]; then
  wrapper_tmp="$(mktemp "$BIN_DIR/.agent-browser-browse.XXXXXXXX")"
  cat "$stage/wrapper" > "$wrapper_tmp"
  chmod 755 "$wrapper_tmp"
  # Hard-linking is atomic and refuses an unrelated file created concurrently.
  ln "$wrapper_tmp" "$WRAPPER" || fail 'Browsing command appeared during installation'
  rm "$wrapper_tmp"
  wrapper_tmp=""
fi
ln -s "$version_dir" "$stage/current"
python3 -I - "$stage/current" "$CURRENT" <<'PY' || fail 'Could not activate verified release'
import os, sys
os.replace(sys.argv[1], sys.argv[2])
PY
log "Installed patched browse CLI v$VERSION (previous version retained)"
