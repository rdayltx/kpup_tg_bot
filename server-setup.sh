#!/bin/bash
# Script para inicializar o servidor e configurar cron jobs para o Keepa Telegram Bot
# Uso: sudo bash server-setup.sh

# Cores para saída no terminal
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Função para imprimir mensagens com timestamp
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERRO:${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] AVISO:${NC} $1"
}

# Verificar se está rodando como root
if [ "$EUID" -ne 0 ]; then
    error "Este script precisa ser executado como root (sudo)."
    exit 1
fi

# Verificar requisitos
log "Verificando requisitos do sistema..."

# Verificar se Docker está instalado
if ! command -v docker &> /dev/null; then
    warn "Docker não encontrado. Instalando Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    
    # Verificar se a instalação foi bem-sucedida
    if ! command -v docker &> /dev/null; then
        error "Falha ao instalar Docker. Por favor, instale manualmente."
        exit 1
    fi
    log "Docker instalado com sucesso!"
else
    log "Docker já está instalado."
fi

# Verificar se Docker Compose está instalado
if ! command -v docker-compose &> /dev/null; then
    warn "Docker Compose não encontrado. Instalando Docker Compose..."
    COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep 'tag_name' | cut -d\" -f4)
    curl -L "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    
    # Verificar se a instalação foi bem-sucedida
    if ! command -v docker-compose &> /dev/null; then
        error "Falha ao instalar Docker Compose. Por favor, instale manualmente."
        exit 1
    fi
    log "Docker Compose instalado com sucesso!"
else
    log "Docker Compose já está instalado."
fi

# Verificar se o crontab está disponível
if ! command -v crontab &> /dev/null; then
    warn "Crontab não encontrado. Instalando cron..."
    apt-get update
    apt-get install -y cron
    
    # Verificar se a instalação foi bem-sucedida
    if ! command -v crontab &> /dev/null; then
        error "Falha ao instalar cron. Por favor, instale manualmente."
        exit 1
    fi
    log "Cron instalado com sucesso!"
    # Iniciar serviço cron
    systemctl enable cron
    systemctl start cron
else
    log "Cron já está instalado."
fi

# Criar diretórios necessários se não existirem
log "Criando diretórios necessários..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
mkdir -p ${SCRIPT_DIR}/{data,logs,backups,chrome-data}
chmod 777 ${SCRIPT_DIR}/chrome-data
log "Diretórios criados com sucesso."

# Verificar se os scripts de healthcheck e limpeza têm permissão de execução
log "Configurando permissões dos scripts..."
chmod +x ${SCRIPT_DIR}/healthcheck.sh
chmod +x ${SCRIPT_DIR}/cleanup-chrome.sh
chmod +x ${SCRIPT_DIR}/rebuild-container.sh
log "Permissões configuradas."

# Configura o cron para o usuário atual
log "Configurando tarefas cron para manutenção automática..."

# Verificar se já existem entradas para os scripts no crontab
CURRENT_USER=$(logname || echo $SUDO_USER)
CRON_CONTENT=$(crontab -u $CURRENT_USER -l 2>/dev/null || echo "")

# Adicionar cron jobs apenas se ainda não existirem
if ! echo "$CRON_CONTENT" | grep -q "healthcheck.sh"; then
    # Healthcheck a cada 15 minutos
    echo "$CRON_CONTENT" > /tmp/crontab.tmp
    echo "# Keepa Bot - Healthcheck a cada 15 minutos" >> /tmp/crontab.tmp
    echo "*/15 * * * * ${SCRIPT_DIR}/healthcheck.sh >> ${SCRIPT_DIR}/logs/healthcheck.log 2>&1" >> /tmp/crontab.tmp
    crontab -u $CURRENT_USER /tmp/crontab.tmp
    log "Cron job para healthcheck configurado."
else
    log "Cron job para healthcheck já existe."
fi

# Atualizar variável de conteúdo do crontab
CRON_CONTENT=$(crontab -u $CURRENT_USER -l 2>/dev/null || echo "")

if ! echo "$CRON_CONTENT" | grep -q "cleanup-chrome.sh"; then
    # Limpeza de processos Chrome a cada 2 horas
    echo "$CRON_CONTENT" > /tmp/crontab.tmp
    echo "# Keepa Bot - Limpeza de processos Chrome a cada 2 horas" >> /tmp/crontab.tmp
    echo "0 */2 * * * ${SCRIPT_DIR}/cleanup-chrome.sh >> ${SCRIPT_DIR}/logs/cleanup.log 2>&1" >> /tmp/crontab.tmp
    crontab -u $CURRENT_USER /tmp/crontab.tmp
    log "Cron job para limpeza de Chrome configurado."
else
    log "Cron job para limpeza de Chrome já existe."
fi

# Atualizar variável de conteúdo do crontab
CRON_CONTENT=$(crontab -u $CURRENT_USER -l 2>/dev/null || echo "")

if ! echo "$CRON_CONTENT" | grep -q "rebuild-container.sh"; then
    # Reconstrução semanal do container
    echo "$CRON_CONTENT" > /tmp/crontab.tmp
    echo "# Keepa Bot - Reconstrução semanal do container (domingo às 4am)" >> /tmp/crontab.tmp
    echo "0 4 * * 0 ${SCRIPT_DIR}/rebuild-container.sh >> ${SCRIPT_DIR}/logs/rebuild.log 2>&1" >> /tmp/crontab.tmp
    crontab -u $CURRENT_USER /tmp/crontab.tmp
    log "Cron job para reconstrução semanal configurado."
else
    log "Cron job para reconstrução semanal já existe."
fi

# Limpar arquivo temporário
rm -f /tmp/crontab.tmp

log "Tarefas cron configuradas com sucesso!"

# Verificar se o arquivo .env existe
if [ ! -f "${SCRIPT_DIR}/.env" ]; then
    warn "Arquivo .env não encontrado. Criando modelo..."
    cat > ${SCRIPT_DIR}/.env << EOL
# Configurações do Bot Telegram
TELEGRAM_BOT_TOKEN=
SOURCE_CHAT_ID=
DESTINATION_CHAT_ID=
ADMIN_ID=

# Configurações Keepa
UPDATE_EXISTING_TRACKING=true
DEFAULT_KEEPA_ACCOUNT=Premium

# Contas Keepa
# Premium
KEEPA_PREMIUM_USERNAME=
KEEPA_PREMIUM_PASSWORD=

# Outras contas (se necessário)
# KEEPA_MERAXES_USERNAME=
# KEEPA_MERAXES_PASSWORD=
# KEEPA_BALERION_USERNAME=
# KEEPA_BALERION_PASSWORD=
EOL
    warn "Um arquivo .env de modelo foi criado. Por favor, edite-o com suas configurações antes de iniciar o bot."
else
    log "Arquivo .env encontrado."
fi

# Iniciar o bot
log "Iniciando o Keepa Telegram Bot..."
cd ${SCRIPT_DIR}
docker-compose down || true
docker-compose up -d --build

# Verificar se o container está rodando
if docker ps | grep -q keepa_telegram_bot; then
    log "Keepa Telegram Bot iniciado com sucesso!"
    log "Para ver os logs em tempo real: docker-compose logs -f"
    log "Para reiniciar o bot: ./rebuild-container.sh"
else
    error "Falha ao iniciar o Keepa Telegram Bot. Verifique os logs para mais detalhes."
    docker-compose logs
    exit 1
fi

log "Configuração do servidor concluída!"
log "Os seguintes serviços foram configurados:"
log "- Bot do Telegram para monitoramento de preços Keepa"
log "- Verificação automática de saúde a cada 15 minutos"
log "- Limpeza de processos Chrome a cada 2 horas"
log "- Reconstrução semanal do container (domingo às 4am)"

echo -e "\n${GREEN}=== KEEPA TELEGRAM BOT INICIALIZADO COM SUCESSO ===${NC}\n"