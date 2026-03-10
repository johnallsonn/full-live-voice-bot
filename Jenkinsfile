pipeline {
    agent any

    environment {
        SSH_CREDENTIAL_ID = 'ResearchQuest-chatbot'  // Jenkins Credential ID for EC2 SSH
        EC2_USER          = 'ubuntu'
        EC2_IP            = '34.233.64.193'
        DEPLOY_PATH       = '/home/ubuntu/deepgram_agent'
        REPO_URL          = 'https://github.com/johnallsonn/full-live-voice-bot.git'
        BRANCH            = 'main'
    }

    stages {

        stage('Checkout') {
            steps {
                echo '=== Checking out source code ==='
                checkout scm
            }
        }

        stage('Deploy to EC2') {
            steps {
                echo '=== Deploying to EC2 ==='
                sshagent(credentials: [SSH_CREDENTIAL_ID]) {
                    sh """
                        ssh -o StrictHostKeyChecking=no ${EC2_USER}@${EC2_IP} '
                            set -e

                            echo "--- Pulling latest code ---"
                            if [ -d "${DEPLOY_PATH}/.git" ]; then
                                cd ${DEPLOY_PATH}
                                git fetch origin
                                git reset --hard origin/${BRANCH}
                            else
                                mkdir -p ${DEPLOY_PATH}
                                git clone -b ${BRANCH} ${REPO_URL} ${DEPLOY_PATH}
                                cd ${DEPLOY_PATH}
                            fi

                            echo "--- Copying .env if not present ---"
                            if [ ! -f "${DEPLOY_PATH}/.env" ]; then
                                echo "WARNING: .env file not found at ${DEPLOY_PATH}/.env"
                                echo "Please manually copy your .env file to the server."
                            fi

                            echo "--- Installing Python dependencies ---"
                            cd ${DEPLOY_PATH}
                            python3 -m pip install --upgrade pip --quiet
                            python3 -m pip install -r requirements.txt --quiet

                            echo "--- Building Next.js Frontend ---"
                            cd ${DEPLOY_PATH}/agent-starter-react-main
                            pnpm install --frozen-lockfile
                            pnpm build

                            echo "--- Restarting Python Agent Service ---"
                            sudo systemctl daemon-reload
                            sudo systemctl restart deepgram-agent
                            sudo systemctl enable deepgram-agent

                            echo "--- Restarting Frontend Service ---"
                            sudo systemctl restart deepgram-frontend
                            sudo systemctl enable deepgram-frontend

                            echo "--- Checking service statuses ---"
                            sudo systemctl status deepgram-agent --no-pager
                            sudo systemctl status deepgram-frontend --no-pager

                            echo "=== Deployment Complete ==="
                        '
                    """
                }
            }
        }
    }

    post {
        success {
            echo '✅ Deployment SUCCESSFUL! App is live at http://${EC2_IP}:3000'
        }
        failure {
            echo '❌ Deployment FAILED! Check console output above for errors.'
        }
    }
}
