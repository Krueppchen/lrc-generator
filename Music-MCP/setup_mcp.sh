#!/bin/bash
# ============================================================
#  setup_mcp.sh — Music-MCP in Claude Cowork einrichten
#  Fügt den MCP-Server zur Claude-Konfiguration hinzu.
#  Aufruf: bash ~/Documents/Music-MCP/setup_mcp.sh
# ============================================================

set -euo pipefail

GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
info() { echo -e "${BLUE}→${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }
fail() { echo -e "${RED}✗ FEHLER:${NC} $1"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_PATH="$SCRIPT_DIR/mcp_server.py"
PYTHON=$(command -v python3 || fail "python3 nicht gefunden")

echo ""
echo -e "${BLUE}🎵 Music-MCP — Claude Cowork Setup${NC}"
echo "======================================"
echo ""

# ── 1. Server-Datei prüfen ────────────────────────────────────
[[ -f "$SERVER_PATH" ]] || fail "mcp_server.py nicht gefunden in $SCRIPT_DIR"
ok "Server gefunden: $SERVER_PATH"

# ── 2. Dependencies installieren ─────────────────────────────
info "Installiere Python-Abhängigkeiten..."
"$PYTHON" -m pip install "mcp[cli]" stable-ts mutagen --break-system-packages -q
ok "Dependencies installiert"

# ── 3. Claude Desktop Config (claude_desktop_config.json) ─────
CLAUDE_CONFIG_DIR="$HOME/Library/Application Support/Claude"
CLAUDE_CONFIG="$CLAUDE_CONFIG_DIR/claude_desktop_config.json"
mkdir -p "$CLAUDE_CONFIG_DIR"

MCP_ENTRY=$(cat <<EOF
{
  "command": "python3",
  "args": ["$SERVER_PATH"]
}
EOF
)

if [[ -f "$CLAUDE_CONFIG" ]]; then
    info "Bestehende Config gefunden — füge music-library hinzu..."
    # Python für sicheres JSON-Merge nutzen
    "$PYTHON" - <<PYEOF
import json, sys
with open("$CLAUDE_CONFIG", "r") as f:
    cfg = json.load(f)
cfg.setdefault("mcpServers", {})
cfg["mcpServers"]["music-library"] = {
    "command": "python3",
    "args": ["$SERVER_PATH"]
}
with open("$CLAUDE_CONFIG", "w") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
print("  Gespeichert.")
PYEOF
else
    info "Erstelle neue Claude-Config..."
    "$PYTHON" - <<PYEOF
import json
cfg = {
  "mcpServers": {
    "music-library": {
      "command": "python3",
      "args": ["$SERVER_PATH"]
    }
  }
}
with open("$CLAUDE_CONFIG", "w") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
print("  Erstellt.")
PYEOF
fi

ok "Claude-Config aktualisiert: $CLAUDE_CONFIG"

# ── 4. Claude Code Config (~/.claude/claude.json) ─────────────
CLAUDE_CODE_CONFIG="$HOME/.claude/claude.json"
if [[ -f "$CLAUDE_CODE_CONFIG" ]]; then
    info "Claude Code Config gefunden — füge auch dort ein..."
    "$PYTHON" - <<PYEOF
import json
with open("$CLAUDE_CODE_CONFIG", "r") as f:
    cfg = json.load(f)
cfg.setdefault("mcpServers", {})
cfg["mcpServers"]["music-library"] = {
    "command": "python3",
    "args": ["$SERVER_PATH"]
}
with open("$CLAUDE_CODE_CONFIG", "w") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
print("  Gespeichert.")
PYEOF
    ok "Claude Code Config aktualisiert"
fi

# ── 5. Config anzeigen ────────────────────────────────────────
echo ""
echo "Config-Inhalt:"
cat "$CLAUDE_CONFIG"
echo ""

# ── 6. Fertig ─────────────────────────────────────────────────
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ✅  SETUP ABGESCHLOSSEN!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "  Nächster Schritt:"
echo "  → Claude Cowork komplett beenden und neu starten"
echo "  → Dann sagen: 'Zeig mir den Status meiner Musikbibliothek'"
echo "  → Claude ruft dann get_library_status() auf"
echo ""
echo "  Log: ~/Library/Logs/MusicMCP.log"
echo ""
