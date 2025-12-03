#!/bin/bash
set -e

# Docker Hub репозиторий
REGISTRY="zambas/repo"

echo "=== Build and Push Docker Images ==="
echo "Registry: $REGISTRY"
echo ""

# Проверяем авторизацию в Docker Hub
if ! docker info 2>/dev/null | grep -q "Username"; then
    echo "Необходимо авторизоваться в Docker Hub:"
    docker login
fi

cd "$(dirname "$0")/.."

echo "[1/6] Building base-core..."
docker build --target base-core -t ${REGISTRY}:base-core .

echo "[2/6] Building base-rag..."
docker build --target base-rag -t ${REGISTRY}:base-rag .

echo "[3/6] Building base-docs..."
docker build --target base-docs -t ${REGISTRY}:base-docs .

echo "[4/6] Building agents..."
docker build --target agents -t ${REGISTRY}:agents .

echo "[5/6] Building frontend..."
docker build --target frontend -t ${REGISTRY}:frontend .

echo "[6/6] Building worker..."
docker build --target worker -t ${REGISTRY}:worker .

echo ""
echo "=== Pushing images to Docker Hub ==="

docker push ${REGISTRY}:base-core
docker push ${REGISTRY}:base-rag
docker push ${REGISTRY}:base-docs
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

