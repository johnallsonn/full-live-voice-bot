pipeline {
    agent any

    environment {
        DEPLOY_PATH = '/var/lib/jenkins/deepgram_agent'
        BRANCH      = 'main'
        // Prevent Jenkins from killing background pm2 processes
        JENKINS_NODE_COOKIE = 'dontKillMe'
    }

    stages {

        stage('Pull Code') {
            steps {
                echo '=== Pulling latest code from GitHub ==='
                dir("${DEPLOY_PATH}") {
                    sh '''
                        if [ -d ".git" ]; then
                            git fetch origin
                            git reset --hard origin/${BRANCH}
                        else
                            git clone -b ${BRANCH} $(git remote get-url origin 2>/dev/null || echo "https://github.com/johnallsonn/full-live-voice-bot.git") ${DEPLOY_PATH}
                        fi
                    '''
                }
            }
        }

        stage('Write .env') {
            steps {
                echo '=== Writing .env from Jenkins Credentials ==='
                withCredentials([
                    file(credentialsId: 'VOICEBOT_OPENAI_API_KEY',    variable: 'OPENAI_KEY_FILE'),
                    string(credentialsId: 'DEEPGRAM_API_KEY',     variable: 'DEEPGRAM_API_KEY'),
                    string(credentialsId: 'LIVEKIT_URL',          variable: 'LIVEKIT_URL'),
                    string(credentialsId: 'LIVEKIT_API_KEY',      variable: 'LIVEKIT_API_KEY'),
                    string(credentialsId: 'LIVEKIT_API_SECRET',   variable: 'LIVEKIT_API_SECRET'),
                    string(credentialsId: 'GEMINI_API_KEY',       variable: 'GEMINI_API_KEY'),
                    string(credentialsId: 'ASSEMBLYAI_API_KEY',   variable: 'ASSEMBLYAI_API_KEY')
                ]) {
                    sh """
                        # Read the OPENAI key from the Secret file Jenkins mounted
                        OPENAI_API_KEY=\$(cat \$OPENAI_KEY_FILE | tr -d '[:space:]')

                        cat > ${DEPLOY_PATH}/.env << EOF
GEMINI_API_KEY=${GEMINI_API_KEY}
OPENAI_API_KEY=\${OPENAI_API_KEY}
DEEPGRAM_API_KEY=${DEEPGRAM_API_KEY}
LIVEKIT_URL=${LIVEKIT_URL}
LIVEKIT_API_KEY=${LIVEKIT_API_KEY}
LIVEKIT_API_SECRET=${LIVEKIT_API_SECRET}
ASSEMBLYAI_API_KEY=${ASSEMBLYAI_API_KEY}
EOF
                        echo ".env written successfully \u2713"
                    """
                }
            }
        }

        stage('Install System & Python Deps') {
            steps {
                echo '=== Installing Pip and Python dependencies (100% Rootless) ==='
                dir("${DEPLOY_PATH}") {
                    sh '''
                        export PATH="$HOME/.local/bin:$PATH"
                        
                        # 1. Install pip locally if missing (bypasses sudo requirement entirely)
                        if ! python3 -m pip --version > /dev/null 2>&1; then
                            echo "Downloading get-pip.py..."
                            curl -sS https://bootstrap.pypa.io/get-pip.py -o get-pip.py
                            python3 get-pip.py --user --break-system-packages || python3 get-pip.py --user
                        fi
                        
                        # 2. Install requirements
                        echo "Installing Python requirements..."
                        python3 -m pip install --user --break-system-packages -r requirements.txt || python3 -m pip install --user -r requirements.txt
                        echo "Python deps installed \u2713"
                    '''
                }
            }
        }

        stage('Install Node & Build Frontend') {
            steps {
                echo '=== Installing Node, pnpm and Building Frontend (100% Rootless) ==='
                dir("${DEPLOY_PATH}/agent-starter-react-main") {
                    sh '''
                        # 1. Install NVM & Node 20 if missing
                        if [ ! -d "$HOME/.nvm" ]; then
                            echo "Installing NVM and Node 20 locally..."
                            curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
                        fi
                        export NVM_DIR="$HOME/.nvm"
                        [ -s "$NVM_DIR/nvm.sh" ] && \\. "$NVM_DIR/nvm.sh"
                        
                        nvm install 20
                        nvm use 20
                        
                        # 2. Install pnpm and pm2 locally
                        npm install -g pnpm pm2
                        
                        # 4. Build Next.js (with increased memory limit to prevent JS heap OOM)
                        export NODE_OPTIONS="--max-old-space-size=4096"
                        pnpm install --frozen-lockfile
                        pnpm build
                        echo "Frontend built \u2713"
                    '''
                }
            }
        }

        stage('Restart Services (PM2)') {
            steps {
                echo '=== Restarting services using PM2 (No sudo needed) ==='
                dir("${DEPLOY_PATH}") {
                    sh '''
                        export PATH="$HOME/.local/bin:$PATH"
                        export NVM_DIR="$HOME/.nvm"
                        [ -s "$NVM_DIR/nvm.sh" ] && \\. "$NVM_DIR/nvm.sh"
                        nvm use 20
                        
                        # Create a simple launcher for Python
                        echo "python3 agent.py start" > start_agent.sh
                        chmod +x start_agent.sh
                        
                        # Delete existing pm2 instances if they exist
                        pm2 delete deepgram-agent || true
                        pm2 delete deepgram-frontend || true
                        
                        # Start Agent
                        pm2 start ./start_agent.sh --name deepgram-agent
                        
                        # Start Frontend
                        cd agent-starter-react-main
                        pm2 start npm --name deepgram-frontend -- run start
                        
                        pm2 save
                        pm2 status
                        echo "Services restarted with PM2 \u2713"
                    '''
                }
            }
        }
    }

    post {
        success {
            echo '✅ Deployment SUCCESSFUL! App is live at http://34.233.64.193:3000'
        }
        failure {
            echo '❌ Deployment FAILED — check the stage logs above.'
        }
    }
}
