// Declarative pipeline: GitHub -> test -> Docker build/push -> Kubernetes deploy.
// Jenkins prerequisites: Docker + kubectl + python3 on the agent, and credentials:
//   'dockerhub-creds' (Username/Password)  and  'kubeconfig' (Secret file).
pipeline {
  agent any
  options { timestamps(); disableConcurrentBuilds() }
  environment {
    IMAGE = "YOUR_DOCKERHUB_USER/smart-canteen"   // <-- change this
    TAG   = "${env.BUILD_NUMBER}"
  }
  stages {
    stage('Checkout') { steps { checkout scm } }

    stage('Install & Test') {
      steps {
        sh '''
          python3 -m venv .venv
          . .venv/bin/activate
          pip install -q -r requirements.txt
          python -m unittest discover -s tests -v
        '''
      }
    }

    stage('Docker Build') {
      steps { sh 'docker build -t $IMAGE:$TAG -t $IMAGE:latest .' }
    }

    stage('Docker Push') {
      steps {
        withCredentials([usernamePassword(credentialsId: 'dockerhub-creds', usernameVariable: 'U', passwordVariable: 'P')]) {
          sh '''
            echo "$P" | docker login -u "$U" --password-stdin
            docker push $IMAGE:$TAG
            docker push $IMAGE:latest
          '''
        }
      }
    }

    stage('Deploy to Kubernetes') {
      when { branch 'main' }
      steps {
        withCredentials([file(credentialsId: 'kubeconfig', variable: 'KUBECONFIG')]) {
          sh '''
            kubectl apply -f k8s/
            kubectl set image deployment/smart-canteen canteen=$IMAGE:$TAG
            kubectl rollout status deployment/smart-canteen --timeout=120s
          '''
        }
      }
    }
  }
  post {
    always  { sh 'docker logout || true' }
    success { echo "Deployed $IMAGE:$TAG" }
    failure { echo 'Pipeline failed - check the stage logs above.' }
  }
}
