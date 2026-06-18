#!/data/data/com.termux/files/usr/bin/bash
# Start Chrome with CDP and allow all origins

# Use the correct chromium path
CHROME_BIN="/data/data/com.termux/files/usr/bin/chromium-browser"

echo "Using chromium: $CHROME_BIN"

# Kill existing
pkill -f chromium 2>/dev/null
vncserver -kill :1 2>/dev/null
sleep 2

# Start VNC
vncserver :1 -geometry 1280x720 -depth 24 -localhost 2>/dev/null
echo "VNC started on :1"

# Wait for VNC
sleep 3

# Start Chrome with proper CDP flags
export DISPLAY=:1

$CHROME_BIN \
  --remote-debugging-port=9222 \
  --remote-debugging-address=127.0.0.1 \
  --remote-allow-origins="*" \
  --user-data-dir=/data/data/com.termux/files/usr/tmp/chrome-profile \
  --no-sandbox \
  --no-first-run \
  --disable-extensions \
  --disable-gpu \
  --disable-software-rasterizer \
  --disable-dev-shm-usage \
  --window-size=1280,720 \
  about:blank &

CHROME_PID=$!
echo "Chrome started with PID: $CHROME_PID"
echo "CDP available at: http://127.0.0.1:9222"

# Wait for Chrome to initialize
echo "Waiting for Chrome to initialize..."
sleep 5

# Get WebSocket URL
WS_URL=$(curl -s http://127.0.0.1:9222/json/version 2>/dev/null | grep -o 'ws://[^"]*')
if [ -n "$WS_URL" ]; then
    echo "✅ WebSocket URL: $WS_URL"
else
    echo "⏳ Waiting for CDP to be ready..."
    for i in {1..15}; do
        sleep 1
        WS_URL=$(curl -s http://127.0.0.1:9222/json/version 2>/dev/null | grep -o 'ws://[^"]*')
        if [ -n "$WS_URL" ]; then
            echo "✅ WebSocket URL: $WS_URL"
            break
        fi
    done
fi

echo ""
echo "✅ Chrome CDP is ready for research!"
echo "You can now run research scripts"
