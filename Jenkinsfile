pipeline {
    agent any

    environment {
        // AWS EC2 Deployment Details
        EC2_IP = '34.233.64.193'
        EC2_USER = 'ubuntu'
        EC2_HOST = "${EC2_USER}@${EC2_IP}"
        SSH_CREDENTIAL_ID = 'ResearchQuest-chatbot'
        DEPLOY_PATH = '/home/ubuntu/deepgram_agent'
        BRANCH = 'main'
        
        // Prevent Jenkins from killing background pm2 processes
        JENKINS_NODE_COOKIE = 'dontKillMe'
        
        // Path for local tools if needed
        PATH = "/usr/bin:/usr/local/bin:${env.PATH}"
    }

    stages {
        stage('Checkout') {
            steps {
                echo '=== Checking out code from SCM ==='
                checkout scm
            }
        }

        stage('Deploy to EC2') {
            steps {
                sshagent(credentials: ["${SSH_CREDENTIAL_ID}"]) {
                    echo "=== Deploying to ${EC2_HOST} ==="
                    
                    // 1. Ensure remote directory exists
                    sh "ssh -o StrictHostKeyChecking=no ${EC2_HOST} 'mkdir -p ${DEPLOY_PATH}'"
                    
                    // 2. Sync files using rsync
                    echo '=== Syncing files to EC2 ==='
                    sh "rsync -avz -e 'ssh -o StrictHostKeyChecking=no' --exclude 'venv' --exclude '.git' ./ ${EC2_HOST}:${DEPLOY_PATH}"
                    
                    // 3. Remote execution
                    sh """
                        ssh -o StrictHostKeyChecking=no ${EC2_HOST} << 'EOF'
                            cd ${DEPLOY_PATH}
                            
                            echo "--- System Cleaning ---"
                            sudo journalctl --vacuum-time=1d
                            rm -rf ~/.cache/pip
                            sudo apt-get clean
                            
                            echo "--- Writing .env from passed variables ---"
                            # We'll handle secrets in the next sub-stage for better security/visibility
EOF
                    """
                }
            }
        }

        stage('Remote Setup & Restart') {
            steps {
                withCredentials([
                    file(credentialsId: 'VOICEBOT_OPENAI_API_KEY',    variable: 'OPENAI_KEY_FILE'),
                    string(credentialsId: 'DEEPGRAM_API_KEY',     variable: 'DEEPGRAM_API_KEY'),
                    string(credentialsId: 'LIVEKIT_URL',          variable: 'LIVEKIT_URL'),
                    string(credentialsId: 'LIVEKIT_API_KEY',      variable: 'LIVEKIT_API_KEY'),
                    string(credentialsId: 'LIVEKIT_API_SECRET',   variable: 'LIVEKIT_API_SECRET'),
                    string(credentialsId: 'GEMINI_API_KEY',       variable: 'GEMINI_API_KEY'),
                    string(credentialsId: 'ASSEMBLYAI_API_KEY',   variable: 'ASSEMBLYAI_API_KEY')
                ]) {
                    sshagent(credentials: ["${SSH_CREDENTIAL_ID}"]) {
                        sh """
                            ssh -o StrictHostKeyChecking=no ${EC2_HOST} << 'EOF'
                                cd ${DEPLOY_PATH}
                                
                                # Export keys for .env generation
                                export DEEPGRAM_API_KEY='${DEEPGRAM_API_KEY}'
                                export LIVEKIT_URL='${LIVEKIT_URL}'
                                export LIVEKIT_API_KEY='${LIVEKIT_API_KEY}'
                                export LIVEKIT_API_SECRET='${LIVEKIT_API_SECRET}'
                                export GEMINI_API_KEY='${GEMINI_API_KEY}'
                                export ASSEMBLYAI_API_KEY='${ASSEMBLYAI_API_KEY}'
                                
                                # Read OpenAI key from secret file
                                OPENAI_API_KEY=\$(cat \$OPENAI_KEY_FILE | tr -d '[:space:]')
                                
                                cat > .env << EOE
GEMINI_API_KEY=\${GEMINI_API_KEY}
OPENAI_API_KEY=\${OPENAI_API_KEY}
DEEPGRAM_API_KEY=\${DEEPGRAM_API_KEY}
LIVEKIT_URL=\${LIVEKIT_URL}
LIVEKIT_API_KEY=\${LIVEKIT_API_KEY}
LIVEKIT_API_SECRET=\${LIVEKIT_API_SECRET}
ASSEMBLYAI_API_KEY=\${ASSEMBLYAI_API_KEY}
EOE
                                echo ".env generated"

                                echo "--- Installing Python Deps ---"
                                export PATH="\$HOME/.local/bin:\$PATH"
                                if ! python3 -m pip --version > /dev/null 2>&1; then
                                    curl -sS https://bootstrap.pypa.io/get-pip.py -o get-pip.py
                                    python3 get-pip.py --user --break-system-packages || python3 get-pip.py --user
                                fi
                                python3 -m pip install --user --break-system-packages -r requirements.txt || python3 -m pip install --user -r requirements.txt
                                
                                echo "--- Installing Node & Building Frontend ---"
                                cd agent-starter-react-main
                                if [ ! -d "\$HOME/.nvm" ]; then
                                    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
                                fi
                                export NVM_DIR="\$HOME/.nvm"
                                [ -s "\$NVM_DIR/nvm.sh" ] && . "\$NVM_DIR/nvm.sh"
                                nvm install 20 > /dev/null 2>&1
                                nvm use 20 > /dev/null 2>&1
                                npm install -g pnpm pm2
                                
                                export NODE_OPTIONS="--max-old-space-size=4096"
                                pnpm install --frozen-lockfile
                                pnpm build
                                
                                echo "--- Restarting Services (PM2) ---"
                                cd ${DEPLOY_PATH}
                                echo "python3 agent.py start" > start_agent.sh
                                chmod +x start_agent.sh
                                
                                pm2 delete deepgram-agent || true
                                pm2 delete deepgram-frontend || true
                                
                                pm2 start ./start_agent.sh --name deepgram-agent
                                cd agent-starter-react-main
                                pm2 start npm --name deepgram-frontend -- run start
                                
                                pm2 save
                                echo "Deployment Complete!"
EOF
                        """
                    }
                }
            }
        }
    }

    post {
        always {
            cleanWs()
        }
        success {
            echo "✅ Deployment SUCCESSFUL! App is live at http://${EC2_IP}:3001"
        }
        failure {
            echo '❌ Deployment FAILED — check the stage logs above.'
        }
    }
}
