#!/bin/bash
set -e

AWS_REGION="ap-southeast-2"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
APP_NAME="it-support-bot"
ECS_CLUSTER="${APP_NAME}-cluster"
ECS_SERVICE="${APP_NAME}-service"
ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${APP_NAME}"
IMAGE_TAG=$(git rev-parse --short HEAD 2>/dev/null || echo "latest")

export $(grep -v '^#' .env | xargs)

echo "🚀 Deploying ${APP_NAME}:${IMAGE_TAG}"
echo "Account: ${AWS_ACCOUNT_ID}"
echo "ECR: ${ECR_REPO}"

# Step 1: Authenticate Docker to ECR
echo "🔐 Authenticating Docker to ECR..."
aws ecr get-login-password --region ${AWS_REGION} | \
    docker login --username AWS --password-stdin ${ECR_REPO}
echo "✅ Authenticated"

# Step 2: Build image
echo "🐳 Building image for linux/amd64..."
docker build --platform linux/amd64 \
    -t ${ECR_REPO}:${IMAGE_TAG} \
    -t ${ECR_REPO}:latest .
echo "✅ Built"

# Step 3: Push to ECR
echo "⬆️  Pushing to ECR..."
docker push ${ECR_REPO}:${IMAGE_TAG}
docker push ${ECR_REPO}:latest
echo "✅ Pushed: ${ECR_REPO}:${IMAGE_TAG}"

# Step 4: Register task definition
echo "📋 Registering task definition..."
TASK_DEF=$(cat << TASKEOF
{
  "family": "${APP_NAME}",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::${AWS_ACCOUNT_ID}:role/ecsTaskExecutionRole",
  "containerDefinitions": [{
    "name": "${APP_NAME}",
    "image": "${ECR_REPO}:${IMAGE_TAG}",
    "portMappings": [{"containerPort": 8000, "protocol": "tcp"}],
    "environment": [
      {"name": "APP_ENV", "value": "production"},
      {"name": "LOG_LEVEL", "value": "INFO"},
      {"name": "VECTOR_STORE", "value": "chroma"},
      {"name": "CHROMA_PERSIST_DIR", "value": "/data/chroma"},
      {"name": "GROQ_API_KEY", "value": "${GROQ_API_KEY}"},
      {"name": "TAVILY_API_KEY", "value": "${TAVILY_API_KEY}"},
      {"name": "REDIS_URL", "value": "redis://localhost:6379"},
      {"name": "RETRIEVAL_TOP_K", "value": "4"},
      {"name": "MAX_CONVERSATION_TURNS", "value": "10"}
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/${APP_NAME}",
        "awslogs-region": "${AWS_REGION}",
        "awslogs-stream-prefix": "ecs"
      }
    },
    "healthCheck": {
      "command": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
      "interval": 30,
      "timeout": 10,
      "retries": 3,
      "startPeriod": 60
    }
  }]
}
TASKEOF
)
aws ecs register-task-definition \
    --cli-input-json "${TASK_DEF}" \
    --region ${AWS_REGION} > /dev/null
echo "✅ Task definition registered"

# Step 5: Create ECS cluster
echo "🏗️  Creating ECS cluster..."
aws ecs create-cluster \
    --cluster-name ${ECS_CLUSTER} \
    --capacity-providers FARGATE \
    --region ${AWS_REGION} 2>/dev/null || true
echo "✅ Cluster ready"

# Step 6: Create or update service
echo "🔄 Deploying service..."
SERVICE_STATUS=$(aws ecs describe-services \
    --cluster ${ECS_CLUSTER} \
    --services ${ECS_SERVICE} \
    --region ${AWS_REGION} \
    --query 'services[0].status' \
    --output text 2>/dev/null || echo "NONE")

if [ "${SERVICE_STATUS}" = "ACTIVE" ]; then
    aws ecs update-service \
        --cluster ${ECS_CLUSTER} \
        --service ${ECS_SERVICE} \
        --task-definition ${APP_NAME} \
        --force-new-deployment \
        --region ${AWS_REGION} > /dev/null
    echo "✅ Service updated — rolling deploy started"
else
    echo "Creating new service..."
    VPC_ID=$(aws ec2 describe-vpcs \
        --filters "Name=isDefault,Values=true" \
        --query 'Vpcs[0].VpcId' \
        --output text --region ${AWS_REGION})
    SUBNET_ID=$(aws ec2 describe-subnets \
        --filters "Name=vpc-id,Values=${VPC_ID}" \
        --query 'Subnets[0].SubnetId' \
        --output text --region ${AWS_REGION})
    SG_ID=$(aws ec2 describe-security-groups \
        --filters "Name=vpc-id,Values=${VPC_ID}" "Name=group-name,Values=default" \
        --query 'SecurityGroups[0].GroupId' \
        --output text --region ${AWS_REGION})

    echo "VPC: ${VPC_ID} | Subnet: ${SUBNET_ID} | SG: ${SG_ID}"

    aws ecs create-service \
        --cluster ${ECS_CLUSTER} \
        --service-name ${ECS_SERVICE} \
        --task-definition ${APP_NAME} \
        --desired-count 1 \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={subnets=[${SUBNET_ID}],securityGroups=[${SG_ID}],assignPublicIp=ENABLED}" \
        --region ${AWS_REGION} > /dev/null
    echo "✅ Service created"
fi

echo ""
echo "🎉 Deployment complete!"
echo "   Image  : ${ECR_REPO}:${IMAGE_TAG}"
echo "   Cluster: ${ECS_CLUSTER}"
echo "   Check  : https://${AWS_REGION}.console.aws.amazon.com/ecs/v2/clusters/${ECS_CLUSTER}/services"
