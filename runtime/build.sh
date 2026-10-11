#!/bin/sh
# input: this runtime folder + a python-build-standalone CPython 3.12 (uv python install 3.12); output: dist/流星蝴蝶剑.app and dist/MeteorMac-arm64.zip; pos: release build.
# The app carries the emulator, Mac adapters and Python only. Game files come from the player; SERIAL=<file> presets the CD key, otherwise it is asked on first launch.
set -e
cd "$(dirname "$0")"
PY=${PY:-$(uv python find 3.12)};PYHOME=$(cd "$(dirname "$PY")/.." && pwd)
DIST=${DIST:-dist};APP="$DIST/流星蝴蝶剑.app";C=$APP/Contents;R=$C/Resources
W="-Wall -Wno-deprecated-declarations -arch arm64 -mmacosx-version-min=12.0"
clang -O2 -dynamiclib $W -framework OpenGL -o libd3dgl.dylib d3dgl.c fast.c
clang -O2 -dynamiclib $W -framework AudioToolbox -framework CoreAudio -framework CoreFoundation -o libaudio.dylib audio.c
clang -O2 -dynamiclib $W -fobjc-arc -framework AppKit -framework OpenGL -o libmeteorhost.dylib host.m
clang -O2 -dynamiclib $W -o libpixels.dylib pixels.c
rm -rf "$APP";mkdir -p "$C/MacOS" "$R/runtime"
cp -R "$PYHOME" "$R/python"
rm -rf "$R/python/lib/python3.12/test" "$R/python/lib/python3.12/idlelib" "$R/python/lib/python3.12/tkinter" "$R/python/lib/"tcl* "$R/python/lib/"tk* "$R/python/lib/"itcl* "$R/python/lib/"thread* "$R/python/include" "$R/python/share"
"$R/python/bin/python3.12" -m pip install -q --no-compile --disable-pip-version-check unicorn==2.1.4 pefile==2024.8.26 pillow capstone==5.0.9
"$R/python/bin/python3.12" -m pip uninstall -q -y pip
rm -rf "$R/python/lib/pkgconfig" "$R/python/bin/"pip* "$R/python/bin/"idle* "$R/python/bin/pydoc"*
# Drop the build machine's paths baked into the interpreter's sysconfig.
grep -rl "$PYHOME" "$R/python" 2>/dev/null | while read -r f;do case "$f" in *.py|*.json|*.txt|*/python3.12-config|*.mk) sed -i '' "s#$PYHOME#/opt/meteor-python#g" "$f";;esac;done
install_name_tool -id @rpath/libpython3.12.dylib "$R/python/lib/libpython3.12.dylib"
clang -O2 $W -I"$R/python/include/python3.12" -I"$PYHOME/include/python3.12" -o "$C/MacOS/MeteorMac" launcher.c -L"$R/python/lib" -lpython3.12 -Wl,-rpath,@executable_path/../Resources/python/lib
for f in runner.py paths.py heap.py win32.py window.py host.py input.py com.py ddraw.py d3d.py gdi.py opengl.py opengl_noop.py dsound.py dshow.py winsock.py registry.py file_search.py \
 libd3dgl.dylib libaudio.dylib libmeteorhost.dylib libpixels.dylib;do cp "$f" "$R/runtime/";done
# App icon: generated, then packed into the sizes macOS asks for.
I=$(mktemp -d)/AppIcon.iconset;mkdir -p "$I";"$R/python/bin/python3.12" make_icon.py "$I/icon_512x512@2x.png"
for n in 16 32 128 256 512;do sips -z $n $n "$I/icon_512x512@2x.png" --out "$I/icon_${n}x${n}.png" >/dev/null;sips -z $((n*2)) $((n*2)) "$I/icon_512x512@2x.png" --out "$I/icon_${n}x${n}@2x.png" >/dev/null;done
iconutil -c icns "$I" -o "$R/AppIcon.icns"
[ -n "$SERIAL" ] && cp "$SERIAL" "$R/runtime/serial.txt"
cat > "$C/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>MeteorMac</string>
<key>CFBundleIdentifier</key><string>io.github.meteor-mac</string>
<key>CFBundleName</key><string>流星蝴蝶剑</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>CFBundleDisplayName</key><string>流星蝴蝶剑</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>${VERSION:-0.1.0}</string>
<key>LSMinimumSystemVersion</key><string>12.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
find "$R/python" -name __pycache__ -prune -exec rm -rf {} +
if grep -rlI "$HOME" "$APP" >/dev/null;then echo "local path left in bundle:";grep -rlI "$HOME" "$APP";exit 1;fi
codesign --force --deep -s - "$APP"
(cd "$DIST" && rm -f MeteorMac-arm64.zip && ditto -c -k --keepParent 流星蝴蝶剑.app MeteorMac-arm64.zip)
du -sh "$APP" "$DIST/MeteorMac-arm64.zip"
