#!/bin/bash
# =============================================================================
# deploy.sh — One-time EC2 Setup Script
# Run this ONCE manually on your EC2 Ubuntu instance to set everything up.
# After this, Jenkins handles all future deployments.
#
# Usage:
#   ssh -i your-key.pem ubuntu@34.233.64.193
#   chmod +x deploy.sh
#   ./deploy.sh
# =============================================================================

set -e

DEPLOY_PATH="/home/ubuntu/deepgram_agent"
REPO_URL="https://github.com/johnallsonn/full-live-voice-bot.git"
BRANCH="main"

echo "=========================================="
echo "  deepgram_agent — EC2 First-Time Setup"
echo "=========================================="

# --- 1. System Updates ---
echo "--- [1/7] Updating system packages ---"
sudo apt-get update -y
sudo apt-get install -y git curl build-essential python3-pip python3-venv

# --- 2. Install Node.js 20.x ---
echo "--- [2/7] Installing Node.js 20 ---"
if ! command -v node &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi
echo "Node.js version: $(node -v)"

# --- 3. Install pnpm ---
echo "--- [3/7] Installing pnpm ---"
if ! command -v pnpm &> /dev/null; then
    curl -fsSL https://get.pnpm.io/install.sh | sh -
    export PNPM_HOME="$HOME/.local/share/pnpm"
    export PATH="$PNPM_HOME:$PATH"
    echo 'export PNPM_HOME="$HOME/.local/share/pnpm"' >> ~/.bashrc
    echo 'export PATH="$PNPM_HOME:$PATH"' >> ~/.bashrc
fi
echo "pnpm version: $(pnpm -v)"

# --- 4. Clone the repository ---
echo "--- [4/7] Cloning repository ---"
if [ -d "$DEPLOY_PATH/.git" ]; then
    echo "Repo already exists, pulling latest..."
    cd "$DEPLOY_PATH" && git pull origin $BRANCH
else
    git clone -b $BRANCH $REPO_URL $DEPLOY_PATH
fi

# --- 5. Copy .env file ---
echo "--- [5/7] Environment Setup ---"
if [ ! -f "$DEPLOY_PATH/.env" ]; then
    echo ""
    echo "⚠️  IMPORTANT: You need to create the .env file manually!"
    echo "   Run this command (fill in your real keys):"
    echo ""
    echo "   cat > $DEPLOY_PATH/.env << 'EOF'"
    echo "   GEMINI_API_KEY=your_gemini_api_key"
    echo "   OPENAI_API_KEY=your_openai_api_key"
    echo "   DEEPGRAM_API_KEY=your_deepgram_api_key"
    echo "   LIVEKIT_URL=wss://your-livekit-url.livekit.cloud"
    echo "   LIVEKIT_API_KEY=your_livekit_api_key"
    echo "   LIVEKIT_API_SECRET=your_livekit_api_secret"
    echo "   ASSEMBLYAI_API_KEY=your_assemblyai_api_key"
    echo "   EOF"
    echo ""
else
    echo ".env file already exists ✓"
fi

# --- 6. Create systemd service for Python Agent ---
echo "--- [6/7] Creating systemd service: deepgram-agent ---"
sudo tee /etc/systemd/system/deepgram-agent.service > /dev/null << EOF
[Unit]
Description=Deepgram LiveKit Voice Agent
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=${DEPLOY_PATH}
EnvironmentFile=${DEPLOY_PATH}/.env
ExecStart=/usr/bin/python3 agent.py start
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# --- 7. Create systemd service for Next.js Frontend ---
echo "--- [7/7] Creating systemd service: deepgram-frontend ---"

# Get pnpm path
PNPM_PATH=$(which pnpm || echo "$HOME/.local/share/pnpm/pnpm")

sudo tee /etc/systemd/system/deepgram-frontend.service > /dev/null << EOF
[Unit]
Description=Deepgram Voice Bot Next.js Frontend
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=${DEPLOY_PATH}/agent-starter-react-main
Environment=NODE_ENV=production
Environment=PORT=3000
ExecStart=${PNPM_PATH} start
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Reload and enable
sudo systemctl daemon-reload
sudo systemctl enable deepgram-agent
sudo systemctl enable deepgram-frontend

echo ""
echo "=========================================="
echo "  ✅ EC2 Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Create your .env file at: $DEPLOY_PATH/.env"
echo "  2. Install Python deps:  cd $DEPLOY_PATH && pip3 install -r requirements.txt"
echo "  3. Build frontend:       cd $DEPLOY_PATH/agent-starter-react-main && pnpm install && pnpm build"
echo "  4. Start services:       sudo systemctl start deepgram-agent deepgram-frontend"
echo "  5. Check status:         sudo systemctl status deepgram-agent deepgram-frontend"
echo "  6. View logs:            journalctl -u deepgram-agent -f"
echo ""
echo "  Frontend will be at:  http://34.233.64.193:3000"
echo ""
