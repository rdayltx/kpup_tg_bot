#!/bin/bash
# Script simplificado para iniciar o Keepa Telegram Bot
# Uso: bash startup.sh

# Cores para saída no terminal
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== INICIANDO KEEPA TELEGRAM BOT ===${NC}"

# Verificar se scripts possuem permissão de execução
chmod +x *.sh

# Verificar se diretórios necessários existem
echo -e "${YELLOW}Verificando diretórios...${NC}"
mkdir -p data logs backups chrome-data
chmod 777 chrome-data
echo -e "${GREEN}✓ Diretórios verificados${NC}"

# Verificar se o arquivo .env existe
if [ ! -f ".env" ]; then
    echo -e "${RED}Arquivo .env não encontrado!${NC}"
    echo -e "${YELLOW}Criando arquivo .env de exemplo...${NC}"
    cat > .env << EOL
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
    echo -e "${RED}ATENÇÃO: Edite o arquivo .env antes de continuar!${NC}"
    echo -e "${YELLOW}Pressione ENTER após editar o arquivo para continuar ou Ctrl+C para cancelar...${NC}"
    read
fi

# Iniciar o bot
echo -e "${YELLOW}Iniciando o Keepa Telegram Bot...${NC}"
docker-compose down >/dev/null 2>&1 || true
docker-compose up -d --build

# Verificar se o container está rodando
if docker ps | grep -q keepa_telegram_bot; then
    echo -e "${GREEN}✓ Keepa Telegram Bot iniciado com sucesso!${NC}"
    echo -e "${YELLOW}Para ver os logs em tempo real: ${NC}docker-compose logs -f"
else
    echo -e "${RED}✗ Falha ao iniciar o Keepa Telegram Bot.${NC}"
    echo -e "${YELLOW}Verificando logs:${NC}"
    docker-compose logs
    exit 1
fi

# Perguntar se deseja configurar cron jobs
echo -e "\n${YELLOW}Deseja configurar tarefas de manutenção automática (cron jobs)? [s/N]${NC}"
read -r setup_cron

if [[ "$setup_cron" =~ ^[Ss]$ ]]; then
    echo -e "${YELLOW}Configurando tarefas cron...${NC}"
    
    # Verificar permissões
    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}Para configurar cron jobs, execute este script como root (sudo).${NC}"
        echo -e "${YELLOW}Comando: ${NC}sudo bash server-setup.sh"
        exit 1
    fi
    
    # Conseguir usuário atual
    CURRENT_USER=$(logname || echo $SUDO_USER)
    
    # Configurar cron jobs
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
    CRON_CONTENT=$(crontab -u $CURRENT_USER -l 2>/dev/null || echo "")
    
    # Healthcheck a cada 15 minutos
    if ! echo "$CRON_CONTENT" | grep -q "healthcheck.sh"; then
        echo "$CRON_CONTENT" > /tmp/crontab.tmp
        echo "# Keepa Bot - Healthcheck a cada 15 minutos" >> /tmp/crontab.tmp
        echo "*/15 * * * * ${SCRIPT_DIR}/healthcheck.sh >> ${SCRIPT_DIR}/logs/healthcheck.log 2>&1" >> /tmp/crontab.tmp
        crontab -u $CURRENT_USER /tmp/crontab.tmp
        echo -e "${GREEN}✓ Cron job para healthcheck configurado.${NC}"
    else
        echo -e "${GREEN}✓ Cron job para healthcheck já existe.${NC}"
    fi
    
    # Atualizar variável
    CRON_CONTENT=$(crontab -u $CURRENT_USER -l 2>/dev/null || echo "")
    
    # Limpeza Chrome a cada 2 horas
    if ! echo "$CRON_CONTENT" | grep -q "cleanup-chrome.sh"; then
        echo "$CRON_CONTENT" > /tmp/crontab.tmp
        echo "# Keepa Bot - Limpeza de processos Chrome a cada 2 horas" >> /tmp/crontab.tmp
        echo "0 */2 * * * ${SCRIPT_DIR}/cleanup-chrome.sh >> ${SCRIPT_DIR}/logs/cleanup.log 2>&1" >> /tmp/crontab.tmp
        crontab -u $CURRENT_USER /tmp/crontab.tmp
        echo -e "${GREEN}✓ Cron job para limpeza de Chrome configurado.${NC}"
    else
        echo -e "${GREEN}✓ Cron job para limpeza de Chrome já existe.${NC}"
    fi
    
    # Atualizar variável
    CRON_CONTENT=$(crontab -u $CURRENT_USER -l 2>/dev/null || echo "")
    
    # Reconstrução semanal
    if ! echo "$CRON_CONTENT" | grep -q "rebuild-container.sh"; then
        echo "$CRON_CONTENT" > /tmp/crontab.tmp
        echo "# Keepa Bot - Reconstrução semanal do container (domingo às 4am)" >> /tmp/crontab.tmp
        echo "0 4 * * 0 ${SCRIPT_DIR}/rebuild-container.sh >> ${SCRIPT_DIR}/logs/rebuild.log 2>&1" >> /tmp/crontab.tmp
        crontab -u $CURRENT_USER /tmp/crontab.tmp
        echo -e "${GREEN}✓ Cron job para reconstrução semanal configurado.${NC}"
    else
        echo -e "${GREEN}✓ Cron job para reconstrução semanal já existe.${NC}"
    fi
    
    # Limpar arquivo temporário
    rm -f /tmp/crontab.tmp
    
    echo -e "${GREEN}✓ Tarefas cron configuradas com sucesso!${NC}"
else
    echo -e "${YELLOW}Pulando configuração de cron jobs.${NC}"
    echo -e "${YELLOW}Para configurar posteriormente, execute: ${NC}sudo bash server-setup.sh"
fi

echo -e "\n${GREEN}=== KEEPA TELEGRAM BOT INICIALIZADO COM SUCESSO ===${NC}"
echo -e "${YELLOW}Status: ${NC}docker-compose ps"
echo -e "${YELLOW}Logs: ${NC}docker-compose logs -f"
echo -e "${YELLOW}Parar: ${NC}docker-compose down"
echo -e "${YELLOW}Reiniciar: ${NC}./rebuild-container.sh\n"