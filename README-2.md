# Keepa Telegram Bot

Bot do Telegram para monitoramento e atualização automática de preços no Keepa com base em mensagens do Telegram.

## Instalação Rápida

1. Clone o repositório ou baixe os arquivos para seu servidor
2. Execute o script de configuração do servidor:

```bash
sudo bash server-setup.sh
```

O script vai:

- Verificar e instalar dependências necessárias (Docker, Docker Compose, cron)
- Criar diretórios necessários
- Configurar cron jobs para manutenção automática
- Criar um arquivo `.env` modelo se não existir
- Iniciar o bot

## Configuração Manual

Se preferir configurar manualmente:

1. Instale Docker e Docker Compose
2. Crie um arquivo `.env` com as configurações (use o arquivo de exemplo)
3. Crie os diretórios necessários:

```bash
mkdir -p data logs backups chrome-data
chmod 777 chrome-data
```

4. Configure os cron jobs para manutenção:

```bash
# Adicione ao crontab (crontab -e):
# Verificação de saúde a cada 15 minutos
*/15 * * * * /caminho/para/healthcheck.sh >> /caminho/para/logs/healthcheck.log 2>&1
# Limpeza de processos Chrome a cada 2 horas
0 */2 * * * /caminho/para/cleanup-chrome.sh >> /caminho/para/logs/cleanup.log 2>&1
# Reconstrução semanal (domingo às 4am)
0 4 * * 0 /caminho/para/rebuild-container.sh >> /caminho/para/logs/rebuild.log 2>&1
```

5. Inicie o bot:

```bash
docker-compose up -d --build
```

## Comandos do Bot

- `/start` - Iniciar o bot
- `/status` - Verificar status do bot e configurações
- `/accounts` - Listar contas Keepa configuradas
- `/test_account [conta]` - Testar login em uma conta específica
- `/start_keepa [conta]` - Iniciar sessão Keepa para uma conta
- `/update [ASIN] [PREÇO] [CONTA]` - Atualizar preço manualmente
- `/clear` - Limpar cache de posts rastreados
- `/close_sessions` - Fechar todas as sessões de navegador
- `/backup` - Criar backup de dados e logs
- `/list_backups` - Listar backups disponíveis
- `/download_backup [NOME]` - Baixar um backup específico
- `/delete_backup [NOME]` - Excluir um backup específico

## Manutenção

O sistema inclui três scripts para manutenção automática:

- **healthcheck.sh**: Verifica a saúde do container a cada 15 minutos
- **cleanup-chrome.sh**: Limpa processos Chrome zumbis a cada 2 horas
- **rebuild-container.sh**: Reconstrói o container semanalmente para evitar problemas de memória

## Solução de Problemas

### Logs

Visualize os logs do bot:

```bash
docker-compose logs -f
```

### Reiniciar o Bot

Se o bot travar ou apresentar problemas:

```bash
./rebuild-container.sh
```

### Problemas com Chrome

Se houver muitos processos Chrome:

```bash
./cleanup-chrome.sh
```

## Estrutura de Diretórios

- `data/`: Armazena dados persistentes do bot
- `logs/`: Logs do sistema
- `backups/`: Backups automáticos
- `chrome-data/`: Dados temporários do Chrome (montado como tmpfs)
