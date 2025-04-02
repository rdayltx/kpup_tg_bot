#!/bin/bash
# Script para reconstruir o container do zero

echo "Parando containers existentes..."
docker-compose down

echo "Removendo imagens antigas..."
docker rmi -f $(docker images | grep keepa | awk '{print $3}') 2>/dev/null

echo "Limpando o cache do Docker..."
docker builder prune -f

echo "Reconstruindo o container..."
docker-compose up -d --build

echo "Mostrando logs..."
docker-compose logs -f