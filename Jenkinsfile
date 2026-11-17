
pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Install & Test') {
            steps {
                bat 'python --version'
                bat 'python -m pip install -r requirements.txt'
                bat 'python -m unittest discover -s tests -v'
            }
        }

        stage('Docker Build') {
            steps {
                bat 'docker build -t smart-canteen:%BUILD_NUMBER% -t smart-canteen:latest .'
            }
        }
    }

    post {
        success {
            echo 'Smart Canteen CI Pipeline completed successfully!'
        }
        failure {
            echo 'Pipeline failed - check the stage logs.'
        }
    }
}
