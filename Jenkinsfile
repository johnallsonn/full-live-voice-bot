pipeline {
    agent any

    environment {
        DEPLOY_PATH = '/home/ubuntu/deepgram_agent'
        BRANCH      = 'main'
    }

    stages {

        // ---------------------------------------------------------------
        // Stage 1: Pull latest code on EC2 (Jenkins is running on EC2)
        // No SSH needed — Jenkins itself runs on this machine
        // ---------------------------------------------------------------
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

        // ---------------------------------------------------------------
        // Stage 2: Write .env file from Jenkins Secret Credentials
        //
        // OPENAI_API_KEY  → stored as "Secret file"  → use file() binding
        // All others      → stored as "Secret text"  → use string() binding
        // ---------------------------------------------------------------
        stage('Write .env') {
            steps {
                echo '=== Writing .env from Jenkins Credentials ==='
                withCredentials([
                    // OPENAI_API_KEY is a Secret FILE — use unique ID 'VOICEBOT_OPENAI_API_KEY'
                    // (different from the existing OPENAI_API_KEY credential for another project)
                    file(credentialsId: 'VOICEBOT_OPENAI_API_KEY',    variable: 'OPENAI_KEY_FILE'),
                    // All others are Secret TEXT
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
                        echo ".env written successfully"
                    """
                }
            }
        }

        // ---------------------------------------------------------------
        // Stage 3: Install Python dependencies
        // ---------------------------------------------------------------
        stage('Install Python Deps') {
            steps {
                echo '=== Installing Python dependencies ==='
                dir("${DEPLOY_PATH}") {
                    sh '''
                        python3 -m pip install --upgrade pip --quiet
                        python3 -m pip install -r requirements.txt --quiet
                        echo "Python deps installed ✓"
                    '''
                }
            }
        }

        // ---------------------------------------------------------------
        // Stage 4: Build Next.js Frontend
        // ---------------------------------------------------------------
        stage('Build Frontend') {
            steps {
                echo '=== Building Next.js frontend ==='
                dir("${DEPLOY_PATH}/agent-starter-react-main") {
                    sh '''
                        export PNPM_HOME="$HOME/.local/share/pnpm"
                        export PATH="$PNPM_HOME:$PATH"
                        pnpm install --frozen-lockfile
                        pnpm build
                        echo "Frontend built ✓"
                    '''
                }
            }
        }

        // ---------------------------------------------------------------
        // Stage 5: Restart Services via systemd
        // ---------------------------------------------------------------
        stage('Restart Services') {
            steps {
                echo '=== Restarting services ==='
                sh '''
                    sudo systemctl daemon-reload
                    sudo systemctl restart deepgram-agent
                    sudo systemctl restart deepgram-frontend
                    echo "Services restarted ✓"
                '''
                sh '''
                    sudo systemctl status deepgram-agent --no-pager || true
                    sudo systemctl status deepgram-frontend --no-pager || true
                '''
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
