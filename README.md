Key Adjustments Summary

Before deploying, ensure these environment variables are set:

Required Environment Variables:

```bash
# Binance API (Required for production)
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret

# Telegram (Optional but recommended)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# Groq AI (Optional for AI analysis)
GROQ_API_KEY=your_groq_api_key

# Firebase (Optional for persistence)
FIREBASE_CREDENTIALS_JSON='{"type":"service_account",...}'
FIREBASE_DATABASE_URL=your_firebase_db_url
```

Optional Configuration Adjustments:

```bash
# Strategy Settings
DEFAULT_RRR=2.0              # Default Risk/Reward Ratio
MIN_RRR=1.0                  # Minimum RRR
MAX_RRR=4.0                  # Maximum RRR
TARGET_RRR=2.5               # Target RRR for quality signals
MIN_QUALITY_SCORE=60         # Minimum quality score (0-100)
CONFIDENCE_THRESHOLD=0.60    # Minimum confidence threshold

# Signal Lifecycle
SYMBOL_COOLDOWN_MINUTES=30   # Cooldown between signals per symbol
SIGNAL_EXPIRY_HOURS=12       # Signal expiry time
BREAK_EVEN_THRESHOLD_MINUTES=240  # Time before break-even check

# AI Settings
AI_MIN_INTERVAL_SECONDS=120  # AI cooldown per symbol
AI_OVERRIDE_QUALITY_THRESHOLD=80  # Quality to override AI conflicts

# Timeframes
TIMEFRAME=15m                # Main timeframe
HTF_TIMEFRAME=1h            # Higher timeframe for trend
LTF_TIMEFRAME=5m            # Lower timeframe for entry
```

---

README.md

```markdown
# 🤖 AI-Powered Trading Bot - Hybrid Strategy

[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-3.1.0-green.svg)](https://github.com/yourusername/trading-bot)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Code Style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

> **Advanced AI-Powered Trading Bot with Hybrid Strategy**: Smart Money Concepts + TDI + Bollinger Bands + Liquidity Sweep + MSS + FVG + HTF Validation

---

## 🚀 Features

### Core Strategy
- **Hybrid Approach**: Combines multiple proven trading strategies
- **Smart Money Concepts**: Liquidity Sweep, Market Structure Shift (MSS), Fair Value Gap (FVG)
- **Technical Analysis**: TDI (Trade Dynamic Index), Super Bollinger Bands, Heikin Ashi
- **Multi-Timeframe Analysis**: HTF (1h) trend validation + LTF (5m) entry timing
- **Dynamic RRR**: Risk/Reward ratio adjusts based on signal quality

### AI Integration
- **Groq AI Integration**: Advanced signal validation and analysis
- **Conflict Detection**: Intelligent handling of conflicting signals
- **Smart Reasoning**: Complete AI reasoning displayed in signals
- **Dynamic RRR Suggestion**: AI recommends optimal RRR based on market conditions

### Trading Features
- **Multiple Symbols**: Support for 20+ cryptocurrency pairs
- **Demo/Live Modes**: Test in demo mode before going live
- **Telegram Notifications**: Real-time signal alerts with complete analysis
- **Firebase Persistence**: Signal storage and recovery across restarts
- **Health Monitoring**: Built-in health check and metrics endpoints

### Risk Management
- **Dynamic Position Sizing**: Adjusts based on signal quality
- **Stop Loss/Take Profit**: Calculated from market structure
- **Fee Optimization**: Accounts for trading fees in calculations
- **Max Active Signals**: Configurable limit to manage risk

---

## 📊 Strategy Overview

### Entry Conditions
1. **TDI Zones**:
   - Hard Buy: TDI ≤ 25
   - Soft Buy: TDI ≤ 35
   - No Trade: TDI 50-65
   - Soft Sell: TDI ≥ 60
   - Hard Sell: TDI ≥ 65

2. **BB Touch + Rejection**:
   - Price touches BB extremes
   - Reversal confirmation (smaller candles)
   - Volume confirmation

3. **Smart Money Confirmation**:
   - Market Structure Shift (MSS)
   - Liquidity Sweep detection
   - Fair Value Gap (FVG) detection

4. **Multi-Timeframe Alignment**:
   - HTF (1h) trend alignment
   - LTF (5m) entry confirmation

### Signal Quality Scoring
| Score Range | Quality | RRR Range | Action |
|-------------|---------|-----------|--------|
| 90-100 | Excellent | 3.0-4.0 | Strong Buy/Sell |
| 70-89 | Good | 2.0-3.0 | Confident Entry |
| 60-69 | Fair | 1.5-2.0 | Cautious Entry |
| <60 | Poor | <1.5 | Reject/Wait |

---

## 🔧 Installation

### Prerequisites
```bash
Python 3.9+
pip (Python package manager)
Git
```

Step 1: Clone Repository

```bash
git clone https://github.com/yourusername/trading-bot.git
cd trading-bot
```

Step 2: Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

Step 4: Configure Environment

```bash
cp .env.example .env
# Edit .env with your configuration
```

Step 5: Create Required Directories

```bash
mkdir -p logs data backups models
```

---

⚙️ Configuration

Environment Variables (.env)

```bash
# === Binance API Configuration ===
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
BINANCE_TESTNET=true

# === Telegram Notifications ===
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# === Groq AI Configuration ===
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_TEMPERATURE=0.3
GROQ_MAX_TOKENS=1200

# === Firebase Persistence ===
FIREBASE_CREDENTIALS_JSON={"type":"service_account","project_id":"..."}
FIREBASE_DATABASE_URL=https://your-project.firebaseio.com

# === Strategy Configuration ===
TIMEFRAME=15m
HTF_TIMEFRAME=1h
LTF_TIMEFRAME=5m
SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,AVAXUSDT

# === RRR Configuration ===
DEFAULT_RRR=2.0
MIN_RRR=1.0
MAX_RRR=4.0
TARGET_RRR=2.5

# === Signal Quality ===
MIN_QUALITY_SCORE=60
CONFIDENCE_THRESHOLD=0.60
SYMBOL_COOLDOWN_MINUTES=30
MAX_SIGNALS_PER_CYCLE=3

# === AI Settings ===
AI_MIN_INTERVAL_SECONDS=120
AI_OVERRIDE_QUALITY_THRESHOLD=80

# === Signal Lifecycle ===
SIGNAL_EXPIRY_HOURS=12
BREAK_EVEN_THRESHOLD_MINUTES=240
MIN_BARS_BEFORE_CHECK=2

# === Deployment ===
ENVIRONMENT=development
RUN_MODE=DEMO
DEBUG=false
PORT=8080
```

---

🚀 Running the Bot

Start Trading Bot

```bash
python main.py
```

Monitor Health

```bash
# Health Check
curl http://localhost:8080/health

# Metrics
curl http://localhost:8080/metrics
```

Docker Deployment

```bash
docker build -t trading-bot .
docker run -d --name trading-bot -p 8080:8080 --env-file .env trading-bot
```

---

📁 Project Structure

```
trading-bot/
├── main.py                    # Main entry point
├── settings.py                # Configuration management
├── data_fetcher.py           # Market data fetching
├── requirements.txt          # Python dependencies
├── Dockerfile                # Docker configuration
├── .env.example              # Environment variables template
├── README.md                 # This file
├── strategy/
│   └── consolidated_trend.py # Main strategy logic
├── utils/
│   ├── ai_analyzer.py       # AI integration
│   ├── signal_manager.py    # Signal lifecycle management
│   ├── telegram_bot.py      # Telegram notifications
│   ├── firebase_client.py   # Firebase persistence
│   └── indicators.py        # Technical indicators
├── logs/                    # Log files
├── data/                    # Data storage
├── backups/                 # Backup files
└── models/                  # AI models
```

---

📊 Signal Flow

```
1. Data Fetching
   └── Binance API → Market Data

2. Strategy Analysis
   ├── HTF Trend (1h)
   ├── LTF Confirmation (5m)
   ├── TDI Analysis
   ├── BB Touch Detection
   └── Smart Money Detection

3. Signal Generation
   ├── Quality Score Calculation
   ├── Dynamic RRR Suggestion
   └── Signal Strength (HARD/SOFT)

4. AI Validation
   ├── Conflict Detection
   ├── RRR Optimization
   └── Decision (APPROVE/REJECT/WAIT)

5. Signal Execution
   ├── SL/TP Calculation
   ├── Position Sizing
   └── Telegram Notification

6. Active Monitoring
   ├── SL/TP Monitoring
   ├── Break-Even Check
   └── Signal Expiry (12h)
```

---

📈 Performance Metrics

Prometheus Metrics

The bot exposes Prometheus metrics at /metrics endpoint:

· bot_status - Bot health status
· bot_signals_generated - Total signals generated
· bot_sniper_signals - Total executed signals
· bot_profitable_signals - Profitable signals count
· bot_losing_signals - Losing signals count
· bot_total_pnl - Total PnL
· bot_avg_rrr - Average Risk/Reward Ratio
· bot_ai_tokens_remaining - AI tokens remaining
· bot_ai_approve_count - AI approvals
· bot_ai_reject_count - AI rejections

---

🛠️ Troubleshooting

Common Issues

1. Connection Errors

```bash
# Check Binance API connectivity
curl https://api.binance.com/api/v3/ping

# Verify API keys
python -c "from settings import config; print(config.binance.api_key)"
```

2. AI Rate Limiting

```bash
# Check AI tokens
curl http://localhost:8080/health | jq '.ai_status.tokens_remaining'

# Clear AI cache
python -c "from utils.ai_analyzer import ai_analyzer; ai_analyzer.clear_cache()"
```

3. Missing Signals

· Verify symbol cooldown: Check SYMBOL_COOLDOWN_MINUTES
· Check confidence threshold: CONFIDENCE_THRESHOLD
· Verify quality score: MIN_QUALITY_SCORE
· Check LTF confirmation: REQUIRE_LTF_CONFIRMATION

4. Telegram Notifications Not Working

```bash
# Test connection
python -c "from utils.telegram_bot import telegram_bot; telegram_bot.send_message('Test')"
```

---

🔒 Security

Best Practices

1. Never commit .env file - Use .env.example as template
2. Use environment variables for all secrets
3. Run in demo mode first before going live
4. Monitor logs for suspicious activity
5. Regularly update dependencies
6. Use strong API keys with limited permissions

Production Setup

```bash
# Use production environment
ENVIRONMENT=production

# Disable demo mode
RUN_MODE=PRODUCTION

# Enable security features
DEBUG=false

# Use strong API keys
BINANCE_API_KEY=... (read-only keys recommended)
```

---

🤝 Contributing

Development Setup

```bash
# Clone development branch
git checkout develop

# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
pytest tests/

# Check code style
black .
flake8
```

Pull Request Process

1. Fork the repository
2. Create feature branch (git checkout -b feature/amazing-feature)
3. Commit changes (git commit -m 'Add amazing feature')
4. Push to branch (git push origin feature/amazing-feature)
5. Open Pull Request

---

📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

⚠️ Disclaimer

IMPORTANT: This bot is for educational purposes only. Cryptocurrency trading involves significant risk. Never trade with money you cannot afford to lose. The authors are not responsible for any financial losses incurred while using this software.

---

📞 Support

· Documentation: Wiki
· Issues: GitHub Issues
· Discord: Join Discord
· Twitter: @YourTwitter

---

🙏 Acknowledgments

· Binance API - Market data provider
· Groq AI - AI analysis
· Telegram - Notifications
· Firebase - Persistence

---

📊 Version History

v3.1.0 (Current)

· ✅ Fixed AI conflict detection and handling
· ✅ Added dynamic RRR based on quality score
· ✅ Improved HTF trend validation
· ✅ Added quality score filtering
· ✅ Fixed signal lifecycle management
· ✅ Enhanced Telegram notifications with AI reasoning

v3.0.0

· ✅ Hybrid strategy integration
· ✅ Smart Money concepts added
· ✅ Multi-timeframe analysis
· ✅ AI integration

v2.0.0

· ✅ TDI + BB strategy
· ✅ Telegram notifications
· ✅ Firebase persistence

---

🚀 Quick Start

```bash
# 1. Clone repository
git clone https://github.com/yourusername/trading-bot.git
cd trading-bot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your configuration

# 4. Start trading
python main.py

# 5. Monitor health
curl http://localhost:8080/health
```

---

Made with ❤️ for the trading community

```

---

## Additional Files Needed

### `.env.example`
```bash
# === Binance API Configuration ===
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
BINANCE_TESTNET=true

# === Telegram Notifications ===
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# === Groq AI Configuration ===
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_TEMPERATURE=0.3
GROQ_MAX_TOKENS=1200

# === Firebase Persistence ===
FIREBASE_CREDENTIALS_JSON={"type":"service_account","project_id":"your-project","private_key":"-----BEGIN PRIVATE KEY-----\n...","client_email":"...@...iam.gserviceaccount.com"}
FIREBASE_DATABASE_URL=https://your-project.firebaseio.com
FIREBASE_COLLECTION=trading_signals

# === Strategy Configuration ===
TIMEFRAME=15m
HTF_TIMEFRAME=1h
LTF_TIMEFRAME=5m
SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,AVAXUSDT,DOGEUSDT,ADAUSDT,DOTUSDT,MATICUSDT,LINKUSDT,UNIUSDT

# === RRR Configuration ===
DEFAULT_RRR=2.0
MIN_RRR=1.0
MAX_RRR=4.0
TARGET_RRR=2.5

# === Signal Quality ===
MIN_QUALITY_SCORE=60
CONFIDENCE_THRESHOLD=0.60
SYMBOL_COOLDOWN_MINUTES=30
MAX_SIGNALS_PER_CYCLE=3
MAX_ACTIVE_SIGNALS=8

# === AI Settings ===
AI_MIN_INTERVAL_SECONDS=120
AI_CACHE_TTL=600
AI_OVERRIDE_QUALITY_THRESHOLD=80

# === Signal Lifecycle ===
SIGNAL_EXPIRY_HOURS=12
BREAK_EVEN_THRESHOLD_MINUTES=240
MIN_BARS_BEFORE_CHECK=2

# === Trading Settings ===
RISK_PER_TRADE_PERCENT=0.5
MAX_POSITION_SIZE_PERCENT=10.0
USE_FUTURES=true
MAX_LEVERAGE=20
DEFAULT_LEVERAGE=5

# === Deployment ===
ENVIRONMENT=development
RUN_MODE=DEMO
DEBUG=false
PORT=8080
ENABLE_HEALTH_SERVER=true

# === Logging ===
LOG_LEVEL=INFO
LOG_FILE=logs/trading_bot.log
METRICS_ENABLED=true
METRICS_PORT=9090
```

requirements.txt

```bash
# Core Dependencies
python-binance==1.0.19
pandas==2.0.3
numpy==1.24.3
python-dotenv==1.0.0

# AI Integration
groq==0.4.2
httpx==0.25.1

# Telegram
python-telegram-bot==20.6

# Firebase
firebase-admin==6.4.0

# HTTP & Networking
requests==2.31.0
urllib3==2.0.7

# Utilities
python-dateutil==2.8.2
pytz==2023.3

# Logging & Monitoring
prometheus-client==0.17.1

# Database (Optional)
sqlalchemy==2.0.22
psycopg2-binary==2.9.9

# Development (Optional)
pytest==7.4.3
black==23.11.0
flake8==6.1.0
mypy==1.7.0
```

Dockerfile

```dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories
RUN mkdir -p logs data backups models

# Expose ports
EXPOSE 8080 9090

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')"

# Run the bot
CMD ["python", "main.py"]
```

.gitignore

```bash
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Environment
.env
.env.local
.env.*.local

# Logs
logs/
*.log

# Data
data/
*.db
*.sqlite

# Backups
backups/
*.bak

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Docker
*.pid

# Testing
.pytest_cache/
.coverage
htmlcov/

# Jupyter
.ipynb_checkpoints/
*.ipynb

# Firebase
*.json
!firebase-credentials-example.json

# Groq
groq_*.json
```

These files provide everything needed for a complete GitHub repository with proper documentation, configuration, and deployment setup.