# Подготовка хоста LitServe с NVIDIA GPU («золотой путь»)

Один раз вручную или через `deploy/bootstrap-litserve-node-gpu.sh` из job **Deploy → install_litserve_gpu_stack**, затем повтор job после **reboot**, если скрипт завершился с кодом **10**.

Цель хоста: проприетарный модуль **`nvidia` в ягдре**, **`nvidia-smi`**, узлы **`/dev/nvidia*`**, **[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)** и перезапуск Docker.

## 1. Снять версии ОС и ядра

```bash
cat /etc/os-release
uname -r
```

## 2. Установить драйвер NVIDIA (Ubuntu)

```bash
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y ubuntu-drivers-common
ubuntu-drivers devices
sudo DEBIAN_FRONTEND=noninteractive ubuntu-drivers install
```

После установки пакета драйвера часто нужен **`sudo reboot`**.

Проверка после перезагрузки:

```bash
nvidia-smi
lsmod | grep nvidia
ls -la /dev/nvidia*
```

## 3. NVIDIA Container Toolkit и Docker

См. официальный install guide (stable deb). После установки:

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

## 4. Дымовые тесты

```bash
sudo docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu22.04 nvidia-smi
```

С образом платформы (подставьте свой тег):

```bash
sudo docker run --rm --gpus all ghcr.io/zamb124/agent-lab:latest \
  python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.device_count()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
```

## 5. Деплой LitServe с GPU

На ноде: `docker compose -f docker-compose-litserve.yaml` уже запрашивает GPU через `deploy.resources.reservations.devices`; переменная **`PROVIDER_LITSERVE__INFRA__ACCELERATOR`** (по умолчанию `auto`) выбирает `cuda:0`, если CUDA видна контейнеру.

Первый вывод ноды с нуля может быть в **два захода**: установка стека (+ reboot), затем job **deploy-litserve** без установки GPU (или второй запуск установки уже no-op после `nvidia-smi`).

## 6. Проверка после деплоя (нагрузка и API)

На хосте во время запросов: `watch -n1 nvidia-smi` — в списке процессов должен появиться Python внутри контейнера, растёт использование памяти GPU.

Локально на ноде (подставьте `model` из `PROVIDER_LITSERVE__INFRA__EMBEDDING_MODEL_ID` / `PROVIDER_LITSERVE__INFRA__MODEL_ID`, совпадающие с `conf.json` или env compose):

```bash
curl -fsS http://127.0.0.1:8014/health

curl -fsS http://127.0.0.1:8014/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{"model":"BAAI/bge-m3","input":"smoke test"}'

curl -fsS http://127.0.0.1:8014/v1/rerank \
  -H 'Content-Type: application/json' \
  -d '{"model":"BAAI/bge-reranker-v2-gemma","query":"q","passages":["a","b"]}'
```

Автоматическая проверка CUDA в контейнере после job: `bash deploy/verify-litserve-gpu-node.sh` (из `/opt/agent-lab`). В логах контейнера при старте движков ищите выбранный `device` (ожидаемо `cuda:0` при доступной CUDA и `accelerator` `auto` или `cuda`).
