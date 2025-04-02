FROM python:3.10-slim

# Configuração para evitar perguntas durante a instalação de pacotes
ENV DEBIAN_FRONTEND=noninteractive

# Instalar dependências
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    tar \
    curl \
    xvfb \
    build-essential \
    procps \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcb-dri3-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Instalar Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Instalar ChromeDriver para Chrome versão 135
RUN wget -q "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/135.0.7049.42/linux64/chromedriver-linux64.zip" -O /tmp/chromedriver.zip \
    && unzip /tmp/chromedriver.zip -d /tmp/ \
    && mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
    && chmod +x /usr/local/bin/chromedriver \
    && rm -rf /tmp/chromedriver.zip /tmp/chromedriver-linux64

# Definir o caminho do ChromeDriver
ENV CHROMEDRIVER_PATH=/usr/local/bin/chromedriver
ENV PATH="${PATH}:/usr/local/bin/chromedriver"

# Configurar o diretório de trabalho
WORKDIR /app

# Criar diretórios necessários
RUN mkdir -p /app/logs /app/data /app/backups /app/chrome-data

# Copiar arquivo de requisitos e instalar dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar o código da aplicação
COPY . .

# Configurar variáveis de ambiente
ENV PYTHONUNBUFFERED=1
ENV CHROME_USER_DATA_DIR=/app/chrome-data

# Criar volume para dados persistentes
VOLUME ["/app/data", "/app/logs", "/app/backups"]

# Executar o bot
CMD ["python", "main.py"]