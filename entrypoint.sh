#!/bin/bash
# ============================================================
# DCA Day Trading Bot - Entrypoint Script
# Version: 1.0.0
# ============================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║         DCA DAY TRADING BOT - ENTRYPOINT              ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════╝${NC}"

# Log function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" >&2
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

# ============ ENVIRONMENT VALIDATION ============

log "Validating environment variables..."

# Check required variables
REQUIRED_VARS=(
    "BINANCE_API_KEY"
    "BINANCE_API_SECRET"
)

MISSING_VARS=()
for VAR in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!VAR}" ]; then
        MISSING_VARS+=("$VAR")
    fi
done

if [ ${#MISSING_VARS[@]} -ne 0 ]; then
    error "Missing required environment variables:"
    for VAR in "${MISSING_VARS[@]}"; do
        error "  - $VAR"
    done
    error "Please set these variables in .env file or environment"

    # Continue in DEMO mode if missing
    if [ "${RUN_MODE:-DEMO}" = "DEMO" ]; then
        warn "Running in DEMO mode with limited functionality"
    else
        exit 1
    fi
fi

# Check testnet setting
if [ "${BINANCE_TESTNET:-true}" = "true" ]; then
    log "Running on Binance TESTNET"
else
    warn "Running on Binance MAINNET - BE CAREFUL!"
    if [ "${ENVIRONMENT:-development}" = "production" ]; then
        log "Production environment confirmed"
    else
        warn "Mainnet with non-production environment - risky!"
        if [ "${FORCE_MAINNET:-false}" != "true" ]; then
            error "Use BINANCE_TESTNET=true for development"
            exit 1
        fi
    fi
fi

# ============ DIRECTORY SETUP ============

log "Setting up directories..."

mkdir -p /app/logs /app/data /app/cache

if [ $? -eq 0 ]; then
    log "✓ Directories created successfully"
else
    error "Failed to create directories"
    exit 1
fi

# ============ MONGODB CHECK ============

if [ -n "${MONGODB_URI}" ]; then
    log "MongoDB URI detected - waiting for connection..."

    # Extract host and port from URI (simple extraction)
    MONGODB_HOST=$(echo "${MONGODB_URI}" | sed -n 's/.*@\(.*\):\([0-9]*\)\/.*/\1/p')
    MONGODB_PORT=$(echo "${MONGODB_URI}" | sed -n 's/.*@\(.*\):\([0-9]*\)\/.*/\2/p')

    if [ -z "${MONGODB_HOST}" ] || [ -z "${MONGODB_PORT}" ]; then
        warn "Could not parse MongoDB host/port, skipping connection check"
    else
        log "Waiting for MongoDB at ${MONGODB_HOST}:${MONGODB_PORT}..."

        MAX_RETRIES=30
        RETRY_COUNT=0
        while ! nc -z "${MONGODB_HOST}" "${MONGODB_PORT}" 2>/dev/null; do
            RETRY_COUNT=$((RETRY_COUNT + 1))
            if [ ${RETRY_COUNT} -ge ${MAX_RETRIES} ]; then
                error "MongoDB not available after ${MAX_RETRIES} attempts"
                warn "Continuing without MongoDB..."
                break
            fi
            echo -n "."
            sleep 2
        done

        if [ ${RETRY_COUNT} -lt ${MAX_RETRIES} ]; then
            log "✓ MongoDB connected successfully"
        fi
    fi
else
    log "No MongoDB URI provided - using in-memory storage"
fi

# ============ PYTHON DEPENDENCIES ============

log "Checking Python dependencies..."

if [ -f "requirements.txt" ]; then
    # Check if all packages are installed
    if ! python -c "import pandas, numpy, requests, pymongo, binance" 2>/dev/null; then
        warn "Some dependencies missing - installing..."
        pip install --no-cache-dir -r requirements.txt
    else
        log "✓ All dependencies installed"
    fi
fi

# ============ CONFIGURATION SUMMARY ============

log "Configuration Summary:"
echo "  ┌─────────────────────────────────────────────────────"
echo "  │ Strategy: Hybrid DCA + Super TDI"
echo "  │ DCA Levels: ${DCA_LEVELS:-3}"
echo "  │ Position Size: \$${POSITION_SIZE_USD:-50}"
echo "  │ Stop Loss: $(echo "${STOP_LOSS_PERCENT:-0.010} * 100" | bc | awk '{printf "%.1f", $0}')%"
echo "  │ Exit Time: ${EXIT_HOUR:-21}:${EXIT_MINUTE:-0} UTC"
echo "  │ Symbols: ${SYMBOLS:-BTCUSDT,ETHUSDT}"
echo "  │ Timeframe: ${TIMEFRAME:-15m}"
echo "  │ Environment: ${ENVIRONMENT:-development}"
echo "  │ Run Mode: ${RUN_MODE:-DEMO}"
echo "  └─────────────────────────────────────────────────────"

# ============ STARTUP ============

log "Starting DCA Day Trading Bot..."

# Create a PID file
echo $$ > /app/dca-bot.pid

# Handle signals
trap 'log "Received SIGTERM - shutting down..."; exit 0' TERM
trap 'log "Received SIGINT - shutting down..."; exit 0' INT

# Run the bot
exec python main.py
