# 益志领导师匹配系统 · 容器镜像（Zeabur / 任意容器平台通用）
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# 先装依赖（利用 Docker 层缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再拷代码
COPY . .

# Zeabur 默认要求监听 8080
EXPOSE 8080

# gunicorn 生产启动；timeout 给足飞书 API 调用余量
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "--timeout", "120", "app:app"]
