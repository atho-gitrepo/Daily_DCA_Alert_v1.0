# ============================================================
# DCA Day Trading Bot - Makefile
# Version: 1.0.0
# ============================================================

.PHONY: help install run test docker-build docker-run docker-stop k8s-deploy k8s-delete clean

# Variables
PROJECT_NAME := dca-trading-bot
DOCKER_IMAGE := $(PROJECT_NAME):latest
K8S_NAMESPACE := trading

help:
	@echo "Available commands:"
	@echo "  make install        - Install Python dependencies"
	@echo "  make run           - Run the bot locally"
	@echo "  make test          - Run tests"
	@echo "  make docker-build  - Build Docker image"
	@echo "  make docker-run    - Run with Docker Compose"
	@echo "  make docker-stop   - Stop Docker containers"
	@echo "  make k8s-deploy    - Deploy to Kubernetes"
	@echo "  make k8s-delete    - Delete Kubernetes resources"
	@echo "  make clean         - Clean temporary files"
	@echo "  make logs          - Show logs"

install:
	pip install -r requirements.txt

run:
	python main.py

test:
	pytest tests/ -v

docker-build:
	docker build -t $(DOCKER_IMAGE) .

docker-run:
	docker-compose up -d

docker-stop:
	docker-compose down

docker-logs:
	docker-compose logs -f

k8s-deploy:
	@echo "Deploying to Kubernetes..."
	kubectl create namespace $(K8S_NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	kubectl apply -f kubernetes/configmap.yaml
	kubectl apply -f kubernetes/secrets.yaml
	kubectl apply -f kubernetes/persistent-volume.yaml
	kubectl apply -f kubernetes/deployment.yaml
	kubectl apply -f kubernetes/service.yaml
	kubectl apply -f kubernetes/hpa.yaml
	@echo "Deployment complete!"
	@echo "Check status: kubectl get pods -n $(K8S_NAMESPACE)"

k8s-delete:
	@echo "Deleting Kubernetes resources..."
	kubectl delete -f kubernetes/hpa.yaml --ignore-not-found
	kubectl delete -f kubernetes/service.yaml --ignore-not-found
	kubectl delete -f kubernetes/deployment.yaml --ignore-not-found
	kubectl delete -f kubernetes/persistent-volume.yaml --ignore-not-found
	kubectl delete -f kubernetes/secrets.yaml --ignore-not-found
	kubectl delete -f kubernetes/configmap.yaml --ignore-not-found
	@echo "Cleanup complete"

k8s-status:
	kubectl get pods -n $(K8S_NAMESPACE)
	kubectl get services -n $(K8S_NAMESPACE)
	kubectl get hpa -n $(K8S_NAMESPACE)

k8s-logs:
	kubectl logs -f -n $(K8S_NAMESPACE) deployment/dca-trading-bot

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name "*.egg" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".coverage" -delete
	rm -rf logs/*.log
	rm -rf data/*.db
	@echo "Clean complete!"

# Deploy to Railway
railway-deploy:
	@echo "Deploying to Railway..."
	railway up

# Deploy to production
deploy-prod: docker-build
	@echo "Deploying to production..."
	ENVIRONMENT=production RUN_MODE=PRODUCTION docker-compose up -d

# Quick local development
dev: install
	python main.py
