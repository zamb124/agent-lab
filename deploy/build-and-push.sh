#!/bin/bash
set -e

# Docker Hub репозиторий
REGISTRY="zambas/repo"
# Платформа для сервера (amd64 для большинства VPS)
PLATFORM="${DOCKER_PLATFORM:-linux/amd64}"

echo "=== Build and Push Docker Images ==="
echo "Registry: $REGISTRY"
echo "Platform: $PLATFORM"
echo ""

# Проверяем авторизацию в Docker Hub
if ! docker info 2>/dev/null | grep -q "Username"; then
    echo "Необходимо авторизоваться в Docker Hub:"
    docker login
fi

cd "$(dirname "$0")/.."

echo "[1/3] Building agents..."
docker buildx build --platform $PLATFORM --target agents -t ${REGISTRY}:agents --load .

echo "[2/3] Building frontend..."
docker buildx build --platform $PLATFORM --target frontend -t ${REGISTRY}:frontend --load .

echo "[3/3] Building worker..."
docker buildx build --platform $PLATFORM --target worker -t ${REGISTRY}:worker --load .

echo ""
echo "=== Pushing images to Docker Hub ==="

docker push ${REGISTRY}:agents
docker push ${REGISTRY}:frontend
docker push ${REGISTRY}:worker

echo ""
echo "=== Done! ==="
echo "Images pushed to Docker Hub:"
echo "  - ${REGISTRY}:agents"
echo "  - ${REGISTRY}:frontend"
echo "  - ${REGISTRY}:worker"
echo ""
echo "Now run: ./deploy/deploy.sh"
