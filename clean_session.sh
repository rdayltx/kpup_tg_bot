#!/bin/bash
# Script para limpar uma sessão específica do Chrome
# Uso: bash clean_session.sh [nome_da_conta]

if [ -z "$1" ]; then
  echo "Por favor, especifique o nome da conta"
  echo "Uso: bash clean_session.sh [nome_da_conta]"
  exit 1
fi

ACCOUNT=$1
SESSION_DIR="./chrome-sessions/$ACCOUNT"

if [ -d "$SESSION_DIR" ]; then
  echo "Limpando sessão para conta: $ACCOUNT"
  rm -rf "$SESSION_DIR"
  mkdir -p "$SESSION_DIR"
  echo "Sessão limpa com sucesso!"
else
  echo "Diretório de sessão não encontrado para: $ACCOUNT"
  mkdir -p "$SESSION_DIR"
  echo "Diretório de sessão criado!"
fi