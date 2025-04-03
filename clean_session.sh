#!/bin/bash
# Script para limpar seletivamente uma sessão do Chrome
# Uso: bash clean_session.sh [nome_da_conta]

if [ -z "$1" ]; then
  echo "Por favor, especifique o nome da conta"
  echo "Uso: bash clean_session.sh [nome_da_conta]"
  exit 1
fi

ACCOUNT=$1
SESSION_DIR="./chrome-sessions/$ACCOUNT"

if [ -d "$SESSION_DIR" ]; then
  echo "Limpando seletivamente a sessão para conta: $ACCOUNT"
  
  # Preservar apenas cookies e configurações básicas
  find "$SESSION_DIR" -type f -not -path "*/Cookies*" -not -path "*/Login Data*" -not -path "*/Preferences*" -delete
  
  # Remover caches e dados temporários
  rm -rf "$SESSION_DIR/Cache"
  rm -rf "$SESSION_DIR/Code Cache"
  rm -rf "$SESSION_DIR/GPUCache"
  rm -rf "$SESSION_DIR/Service Worker"
  
  echo "Sessão limpa seletivamente com sucesso!"
else
  echo "Diretório de sessão não encontrado para: $ACCOUNT"
  mkdir -p "$SESSION_DIR"
  echo "Diretório de sessão criado!"
fi