#!/bin/sh
# Build Ultraleap's leapc-python-bindings into hub/.venv (macOS).
# The upstream repo targets LeapC 5 (Gemini). Current Ultraleap Hand Tracking ships
# LeapC 6 (libLeapC.6.dylib), so the three references are patched before building.
# Needs: Ultraleap Hand Tracking installed in /Applications, Xcode command line tools.
set -e
HUB="$(cd "$(dirname "$0")" && pwd)"
SDK="${LEAPSDK_INSTALL_LOCATION:-/Applications/Ultraleap Hand Tracking.app/Contents/LeapSDK}"
WORK="$(mktemp -d)"
git clone -q --depth 1 https://github.com/ultraleap/leapc-python-bindings "$WORK/leapc-python-bindings"
cd "$WORK/leapc-python-bindings"
if [ -e "$SDK/lib/libLeapC.6.dylib" ]; then
  sed -i '' 's/libLeapC\.5\.dylib/libLeapC.6.dylib/' leapc-cffi/setup.py leapc-python-api/src/leap/__init__.py
  sed -i '' 's/"LeapC\.5"/"LeapC.6"/' leapc-cffi/src/scripts/cffi_build.py
fi
"$HUB/.venv/bin/pip" install -q build cffi
"$HUB/.venv/bin/python" -m build leapc-cffi
"$HUB/.venv/bin/pip" install --force-reinstall --no-deps leapc-cffi/dist/leapc_cffi-*.tar.gz
"$HUB/.venv/bin/pip" install --force-reinstall --no-deps ./leapc-python-api
"$HUB/.venv/bin/python" -c "import leap; print('leap bindings OK')"
rm -rf "$WORK"
