#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# start-browser.sh  —  Robust Chromium CDP launcher for Termux
# ============================================================
# Requirements:
#   pkg install chromium x11-repo tigervnc curl procps
#
# Assumed paths (Termux defaults):
#   CHROME_BIN  /data/data/com.termux/files/usr/bin/chromium-browser
#   PREFIX      /data/data/com.termux/files/usr   (set by Termux automatically)
#   VNC display :1  →  lock file at $PREFIX/tmp/.X1-lock
#   CDP port    9222 (change CDP_PORT below if needed)
#
# Usage:
#   chmod +x start-browser.sh
#   ./start-browser.sh            # start normally
#   ./start-browser.sh --force    # kill any existing Chromium first
#   ./start-browser.sh --url      # print only the WS URL (for scripting)
#   ./start-browser.sh --kill     # kill everything (VNC + Chromium)
# ============================================================

set -euo pipefail

# ── Config ─────────────────────────────────────────────────
DISPLAY_NUM=":1"
CHROME_BIN="${CHROME_BIN:-/data/data/com.termux/files/usr/bin/chromium-browser}"
CDP_PORT="${CDP_PORT:-9222}"
CDP_URL="http://127.0.0.1:${CDP_PORT}/json/version"
VNC_GEOMETRY="${VNC_GEOMETRY:-1280x720}"
POLL_TIMEOUT="${POLL_TIMEOUT:-60}"   # seconds to wait for Chromium to be ready
# In Termux, /tmp is read-only — $PREFIX/tmp is the writable equivalent
TERMUX_TMP="${PREFIX:-/data/data/com.termux/files/usr}/tmp"
LOG_FILE="${LOG_FILE:-${TERMUX_TMP}/start-browser.log}"

# User data dir keeps profile isolated and avoids "profile locked" conflicts
CHROME_PROFILE="${CHROME_PROFILE:-${TERMUX_TMP}/chromium-cdp-profile}"

# ── Flags ──────────────────────────────────────────────────
FORCE=false
URL_ONLY=false
KILL_ALL=false
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=true ;;
    --url)   URL_ONLY=true ;;
    --kill)  KILL_ALL=true ;;
    --help)
      echo "Usage: $0 [--force] [--url] [--kill]"
      echo "  --force  kill existing Chromium before starting"
      echo "  --url    print only the WebSocket debugger URL"
      echo "  --kill   kill all VNC and Chromium processes"
      exit 0 ;;
  esac
done

# ── Init log file ──────────────────────────────────────────
mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
touch "$LOG_FILE" 2>/dev/null || LOG_FILE=/dev/null

# ── Helpers ────────────────────────────────────────────────
log()  { "$URL_ONLY" || echo "[*] $*"; echo "$(date '+%H:%M:%S') [info]  $*" >> "$LOG_FILE"; }
ok()   { "$URL_ONLY" || echo "[+] $*"; echo "$(date '+%H:%M:%S') [ok]    $*" >> "$LOG_FILE"; }
warn() { "$URL_ONLY" || echo "[-] $*" >&2; echo "$(date '+%H:%M:%S') [warn]  $*" >> "$LOG_FILE"; }
die()  { echo "[!] $*" >&2; echo "$(date '+%H:%M:%S') [error] $*" >> "$LOG_FILE"; exit 1; }

get_ws_url() {
  # Try multiple methods to get WebSocket URL
  local ws_url=""
  
  # Method 1: Direct curl to CDP endpoint
  ws_url=$(curl -s --max-time 3 "$CDP_URL" 2>/dev/null \
    | grep -o '"webSocketDebuggerUrl":"[^"]*"' \
    | cut -d'"' -f4)
  
  # Method 2: Parse from log file
  if [[ -z "$ws_url" ]]; then
    ws_url=$(grep -oP 'DevTools listening on ws://\S+' "$LOG_FILE" 2>/dev/null | head -1 | cut -d' ' -f4)
  fi
  
  # Method 3: Try to get from /json/version with python if available
  if [[ -z "$ws_url" ]] && command -v python3 >/dev/null 2>&1; then
    ws_url=$(curl -s --max-time 3 "$CDP_URL" 2>/dev/null \
      | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('webSocketDebuggerUrl', ''))" 2>/dev/null)
  fi
  
  echo "$ws_url"
}

cdp_alive() {
  # Check if CDP is responding
  if curl -sf --max-time 2 "$CDP_URL" >/dev/null 2>&1; then
    return 0
  fi
  
  # Alternative: Check if Chromium process has the port in its cmdline
  if pgrep -f "chromium.*--remote-debugging-port=${CDP_PORT}" >/dev/null 2>&1; then
    # Process exists, check if it's listening
    if command -v netstat >/dev/null 2>&1; then
      netstat -tln 2>/dev/null | grep -q ":${CDP_PORT}" && return 0
    fi
    # Check via /proc
    if grep -q "chromium.*${CDP_PORT}" /proc/*/cmdline 2>/dev/null; then
      return 0
    fi
  fi
  
  return 1
}

port_in_use() {
  # Check if port is already in use
  if command -v netstat >/dev/null 2>&1; then
    netstat -tln 2>/dev/null | grep -q ":${CDP_PORT} " && return 0
  fi
  
  if command -v ss >/dev/null 2>&1; then
    ss -tln 2>/dev/null | grep -q ":${CDP_PORT} " && return 0
  fi
  
  # Check via /proc
  local hex_port
  hex_port=$(printf '%04X' "$CDP_PORT")
  grep -qE ":[0-9A-F]*${hex_port} " /proc/net/tcp6 /proc/net/tcp 2>/dev/null && return 0
  
  return 1
}

# ── Kill everything (VNC + Chromium) ───────────────────────
if "$KILL_ALL"; then
  log "Killing all Chromium and VNC processes..."
  
  # Kill Chromium
  pkill -f "chromium" 2>/dev/null && ok "Killed Chromium processes" || warn "No Chromium processes found"
  
  # Kill VNC
  vncserver -kill "$DISPLAY_NUM" 2>/dev/null && ok "Killed VNC session $DISPLAY_NUM" || warn "No VNC session on $DISPLAY_NUM"
  
  # Clean up lock files
  rm -f "${TERMUX_TMP}/.X${DISPLAY_NUM#:}-lock" 2>/dev/null || true
  rm -f "${TERMUX_TMP}/.X11-unix/X${DISPLAY_NUM#:}" 2>/dev/null || true
  
  ok "Cleanup complete"
  exit 0
fi

# ── 1. Dependency check ─────────────────────────────────────
log "Checking dependencies..."
missing=()
for dep in curl vncserver pkill; do
  command -v "$dep" >/dev/null 2>&1 || missing+=("$dep")
done

# Check for chromium (try multiple paths)
if [[ ! -x "$CHROME_BIN" ]]; then
  # Try alternative paths
  if [[ -x "/data/data/com.termux/files/usr/bin/chromium" ]]; then
    CHROME_BIN="/data/data/com.termux/files/usr/bin/chromium"
    ok "Found chromium at $CHROME_BIN"
  elif [[ -x "/data/data/com.termux/files/usr/bin/chromium-browser" ]]; then
    CHROME_BIN="/data/data/com.termux/files/usr/bin/chromium-browser"
    ok "Found chromium at $CHROME_BIN"
  else
    missing+=("chromium")
  fi
fi

if [[ ${#missing[@]} -gt 0 ]]; then
  die "Missing dependencies: ${missing[*]}
  Install with: pkg install chromium x11-repo tigervnc curl procps"
fi
ok "All dependencies present"

# ── 2. Check if CDP already up (skip if force) ─────────────
if ! "$FORCE" && cdp_alive; then
  ok "Chromium already running on port $CDP_PORT"
  WS=$(get_ws_url)
  if [[ -n "$WS" ]]; then
    "$URL_ONLY" && echo "$WS" || echo "[+] WS URL: $WS"
    exit 0
  else
    warn "CDP alive but could not get WebSocket URL"
  fi
fi

# ── 3. Force mode: kill existing processes ─────────────────
if "$FORCE"; then
  log "Force mode: killing existing processes..."
  
  # Kill Chromium
  pkill -f "chromium.*--remote-debugging-port" 2>/dev/null || true
  pkill -f "chromium" 2>/dev/null || true
  
  # Kill VNC session
  vncserver -kill "$DISPLAY_NUM" 2>/dev/null || true
  
  # Wait for port to free
  for i in $(seq 1 10); do
    port_in_use || break
    sleep 1
  done
  
  # Clean up lock files
  rm -f "${TERMUX_TMP}/.X${DISPLAY_NUM#:}-lock" 2>/dev/null || true
  rm -f "${TERMUX_TMP}/.X11-unix/X${DISPLAY_NUM#:}" 2>/dev/null || true
  
  port_in_use && warn "Port $CDP_PORT still in use after 10s"
  sleep 2
fi

# ── 4. Start VNC if not running ────────────────────────────
log "Checking VNC on ${DISPLAY_NUM}..."
VNC_RUNNING=false

# Check if VNC is already running
if vncserver -list 2>/dev/null | grep -qF "$DISPLAY_NUM"; then
  ok "VNC session already running on $DISPLAY_NUM"
  VNC_RUNNING=true
fi

if ! "$VNC_RUNNING"; then
  log "Starting VNC on $DISPLAY_NUM..."
  
  # Create VNC password if it doesn't exist
  VNC_PASSWD="${HOME}/.vnc/passwd"
  if [[ ! -f "$VNC_PASSWD" ]]; then
    mkdir -p "${HOME}/.vnc"
    # Set a simple password (using 'termux')
    printf "termux\ntermux\nn\n" | vncpasswd 2>/dev/null || \
      echo "termux" | vncpasswd -f > "$VNC_PASSWD" 2>/dev/null || \
      warn "Could not set VNC password, trying without authentication"
    chmod 600 "$VNC_PASSWD" 2>/dev/null || true
  fi
  
  # Try to start VNC with multiple configurations
  if ! vncserver "$DISPLAY_NUM" -geometry "$VNC_GEOMETRY" -depth 24 -localhost 2>>"$LOG_FILE"; then
    warn "First VNC attempt failed, trying without -localhost..."
    if ! vncserver "$DISPLAY_NUM" -geometry "$VNC_GEOMETRY" -depth 16 2>>"$LOG_FILE"; then
      die "vncserver failed to start. Check: $LOG_FILE"
    fi
  fi
  
  ok "VNC started on $DISPLAY_NUM ($VNC_GEOMETRY)"
  
  # Wait for VNC to fully initialize
  sleep 3
fi

export DISPLAY="$DISPLAY_NUM"

# ── 5. Kill any stale Chromium (if not already killed) ─────
if pkill -0 -f "chromium" 2>/dev/null; then
  if "$FORCE"; then
    log "Stopping stale Chromium processes..."
    pkill -f "chromium" 2>/dev/null || true
    sleep 2
  else
    warn "Existing Chromium process found. Use --force to kill it."
  fi
fi

# ── 6. Ensure profile dir exists ───────────────────────────
mkdir -p "$CHROME_PROFILE"

# ── 7. Clear old log for fresh start ───────────────────────
if [[ -f "$LOG_FILE" ]]; then
  echo "--- New session started at $(date) ---" >> "$LOG_FILE"
fi

# ── 8. Launch Chromium ─────────────────────────────────────
log "Launching Chromium (CDP port $CDP_PORT, DISPLAY=$DISPLAY)..."

# Build chromium command
CHROME_CMD=(
  "$CHROME_BIN"
  "--remote-debugging-port=${CDP_PORT}"
  "--remote-debugging-address=127.0.0.1"
  "--user-data-dir=${CHROME_PROFILE}"
  "--display=${DISPLAY}"
  "--no-sandbox"
  "--no-first-run"
  "--no-default-browser-check"
  "--disable-extensions"
  "--disable-default-apps"
  "--disable-translate"
  "--disable-background-networking"
  "--disable-sync"
  "--disable-gpu"
  "--disable-software-rasterizer"
  "--disable-dev-shm-usage"
  "--disable-features=VizDisplayCompositor"
  "--metrics-recording-only"
  "--safebrowsing-disable-auto-update"
  "--window-size=${VNC_GEOMETRY%x*},${VNC_GEOMETRY#*x}"
  "--window-position=0,0"
  "about:blank"
)

# Launch chromium
nohup "${CHROME_CMD[@]}" >> "$LOG_FILE" 2>&1 &
CHROME_PID=$!
ok "Chromium launched (PID $CHROME_PID)"

# ── 9. Poll until CDP is ready (improved) ──────────────────
log "Waiting for CDP to be ready (up to ${POLL_TIMEOUT}s)..."

for i in $(seq 1 "$POLL_TIMEOUT"); do
  # Check if process is still alive
  if ! kill -0 "$CHROME_PID" 2>/dev/null; then
    # Process died, check if it's a crash or normal exit
    if grep -q "DevTools listening" "$LOG_FILE" 2>/dev/null; then
      # It logged success before dying, might be ok
      WS=$(get_ws_url)
      if [[ -n "$WS" ]]; then
        warn "Chromium process died but CDP was active"
        "$URL_ONLY" && echo "$WS" || echo "[+] WS URL: $WS"
        exit 0
      fi
    fi
    die "Chromium process died (PID $CHROME_PID). Check: $LOG_FILE"
  fi
  
  # Method 1: Check log for DevTools listening message (fastest)
  WS=$(grep -oP 'DevTools listening on ws://\S+' "$LOG_FILE" 2>/dev/null | head -1 | cut -d' ' -f4)
  if [[ -n "$WS" ]]; then
    ok "Chromium ready after ${i}s (detected from log)"
    "$URL_ONLY" && echo "$WS" || echo "[+] WS URL: $WS"
    exit 0
  fi
  
  # Method 2: Try direct CDP connection
  if cdp_alive; then
    WS=$(get_ws_url)
    if [[ -n "$WS" ]]; then
      ok "Chromium ready after ${i}s (CDP endpoint responding)"
      "$URL_ONLY" && echo "$WS" || echo "[+] WS URL: $WS"
      exit 0
    fi
  fi
  
  # Show progress every 10 seconds
  if (( i % 10 == 0 )); then
    log "Still waiting... (${i}s elapsed)"
  fi
  
  sleep 1
done

# ── 10. Timeout - show diagnostic info ──────────────────────
echo ""
warn "Chromium did not respond on port $CDP_PORT within ${POLL_TIMEOUT}s"
echo ""
echo "Diagnostic information:"
echo "  - PID: $CHROME_PID"
echo "  - Log file: $LOG_FILE"
echo ""
echo "Checking process status:"
if kill -0 "$CHROME_PID" 2>/dev/null; then
  echo "  ✓ Process $CHROME_PID is still running"
else
  echo "  ✗ Process $CHROME_PID is dead"
fi
echo ""
echo "Last 20 lines of log:"
tail -20 "$LOG_FILE"
echo ""
echo "Manual debug steps:"
echo "  1. Check if VNC is running: vncserver -list"
echo "  2. Test display: DISPLAY=:1 xdpyinfo"
echo "  3. Try connecting to CDP: curl $CDP_URL"
echo "  4. Check chromium directly: ps aux | grep chromium"
echo "  5. Run with --force to restart everything: ./start-browser.sh --force"
echo ""

die "Chromium failed to start CDP endpoint"
