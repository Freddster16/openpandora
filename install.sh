#!/bin/sh
set -eu

repo="${OPENPANDORA_REPO:-Freddster16/openpandora}"
install_dir="${OPENPANDORA_INSTALL_DIR:-$HOME/.local/bin}"
app_dir="${OPENPANDORA_APP_DIR:-$HOME/.local/share/openpandora}"
download_url="${OPENPANDORA_URL:-https://github.com/$repo/releases/latest/download/openpandora.pyz}"
app_file="$app_dir/openpandora.pyz"
target="$install_dir/openpandora"
temp_file="$app_file.tmp"

check_python() {
  "$1" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
}

find_python() {
  if [ -n "${OPENPANDORA_PYTHON:-}" ]; then
    if check_python "$OPENPANDORA_PYTHON"; then
      command -v "$OPENPANDORA_PYTHON"
      return 0
    fi
    return 1
  fi

  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      python_path="$(command -v "$candidate")"
      if check_python "$python_path"; then
        echo "$python_path"
        return 0
      fi
    fi
  done

  return 1
}

python_cmd="$(find_python)" || {
  echo "OpenPandora needs Python 3.11 or newer." >&2
  echo "Set OPENPANDORA_PYTHON to a compatible Python if needed." >&2
  exit 1
}

mkdir -p "$install_dir" "$app_dir"

if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$download_url" -o "$temp_file"
elif command -v wget >/dev/null 2>&1; then
  wget -q "$download_url" -O "$temp_file"
else
  echo "OpenPandora needs curl or wget to download the latest release." >&2
  exit 1
fi

mv "$temp_file" "$app_file"

cat > "$target" <<EOF
#!/bin/sh
exec "$python_cmd" "$app_file" "\$@"
EOF
chmod +x "$target"

echo "OpenPandora installed to $target"
if [ "${OPENPANDORA_SKIP_SETUP:-}" != "1" ] && [ -t 0 ]; then
  echo "Starting first-time setup. Set OPENPANDORA_SKIP_SETUP=1 to skip this."
  if ! "$target" setup --global; then
    echo "Setup did not finish. You can run it later with: openpandora setup"
  fi
fi
case ":$PATH:" in
  *":$install_dir:"*) ;;
  *)
    echo "Add this to your PATH if openpandora is not found:"
    echo "  export PATH=\"$install_dir:\$PATH\""
    ;;
esac
