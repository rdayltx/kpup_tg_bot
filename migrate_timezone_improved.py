# migrate_timezone_fixed.py
# Script corrigido para migrar timestamps existentes para o timezone do Brasil

import os
import json
import glob
from datetime import datetime
import pytz
import dateutil.parser
import sys
import re

# Definir o timezone do Brasil
BRAZIL_TIMEZONE = pytz.timezone('America/Sao_Paulo')

# Expressão regular para verificar se um timestamp ISO 8601 já contém informação de timezone
# Procura por +HH:MM, -HH:MM ou Z no final da string
TZ_PATTERN = re.compile(r'.*[+-][0-9]{2}:[0-9]{2}$|.*Z$')

def has_timezone_info(timestamp):
    """
    Verifica corretamente se um timestamp ISO 8601 já contém informação de timezone
    
    Args:
        timestamp: String de timestamp
        
    Returns:
        bool: True se já contém timezone, False caso contrário
    """
    # Usar expressão regular para verificar corretamente
    return bool(TZ_PATTERN.match(timestamp))

def migrate_product_database(file_path, dry_run=False):
    """
    Migrar timestamps em um arquivo products_*.json
    
    Args:
        file_path: Caminho para o arquivo de produtos
        dry_run: Se True, apenas simula sem fazer alterações
    """
    try:
        print(f"\n{'=' * 50}")
        print(f"Processando arquivo: {file_path}")
        
        # Verificar se o arquivo existe
        if not os.path.exists(file_path):
            print(f"ERRO: Arquivo não encontrado: {file_path}")
            return 0
            
        # Verificar permissões
        if not os.access(file_path, os.R_OK):
            print(f"ERRO: Sem permissão de leitura para o arquivo: {file_path}")
            return 0
            
        if not dry_run and not os.access(file_path, os.W_OK):
            print(f"ERRO: Sem permissão de escrita para o arquivo: {file_path}")
            return 0
            
        # Carregar o arquivo
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                data = json.loads(content)
        except json.JSONDecodeError as e:
            print(f"ERRO: Arquivo JSON inválido: {e}")
            return 0
        except Exception as e:
            print(f"ERRO ao ler o arquivo: {e}")
            return 0
            
        # Contador de itens atualizados
        updated_count = 0
        
        # Processar cada produto
        for asin, product_data in list(data.items()):
            if 'last_updated' in product_data:
                timestamp = product_data['last_updated']
                
                print(f"Produto {asin}: timestamp atual = '{timestamp}'")
                
                try:
                    # Tentar converter o timestamp para datetime
                    if isinstance(timestamp, str):
                        # Verificar CORRETAMENTE se já contém informação de timezone
                        if has_timezone_info(timestamp):
                            print(f"  - Já contém timezone: {timestamp}")
                            continue
                            
                        # Tentar com formato ISO
                        try:
                            dt = datetime.fromisoformat(timestamp)
                        except ValueError:
                            # Usar parser mais flexível se falhar
                            dt = dateutil.parser.parse(timestamp)
                        
                        # Verificar se já tem timezone
                        if dt.tzinfo is None:
                            # Adicionar timezone do Brasil
                            dt = BRAZIL_TIMEZONE.localize(dt)
                            new_timestamp = dt.isoformat()
                            print(f"  - Convertido para: {new_timestamp}")
                            
                            if not dry_run:
                                product_data['last_updated'] = new_timestamp
                            updated_count += 1
                        else:
                            # Já tem timezone, converter para timezone do Brasil
                            dt = dt.astimezone(BRAZIL_TIMEZONE)
                            new_timestamp = dt.isoformat()
                            print(f"  - Já tem timezone, convertido para: {new_timestamp}")
                            
                            if not dry_run:
                                product_data['last_updated'] = new_timestamp
                            updated_count += 1
                except Exception as e:
                    print(f"  - ERRO ao processar timestamp '{timestamp}': {e}")
        
        # Salvar o arquivo atualizado
        if updated_count > 0 and not dry_run:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"Arquivo atualizado com sucesso.")
            except Exception as e:
                print(f"ERRO ao salvar arquivo: {e}")
                return 0
        
        print(f"Migração {'' if not dry_run else 'simulada '} concluída. {updated_count} timestamps {'seriam' if dry_run else 'foram'} atualizados.")
        return updated_count
    
    except Exception as e:
        print(f"ERRO geral ao migrar arquivo {file_path}: {e}")
        return 0

def run_migration(target_file=None, dry_run=False):
    """
    Executar a migração de arquivos
    
    Args:
        target_file: Se fornecido, migra apenas este arquivo específico
        dry_run: Se True, apenas simula sem fazer alterações
    """
    print(f"{'SIMULAÇÃO DE ' if dry_run else ''}MIGRAÇÃO DE TIMEZONE PARA BRASIL")
    print(f"{'=' * 50}")
    print(f"Timezone alvo: America/Sao_Paulo (UTC-3)")
    print(f"{'Nenhuma alteração será feita (modo simulação)' if dry_run else 'As alterações serão aplicadas aos arquivos'}")
    print(f"{'=' * 50}")
    
    total_updated = 0
    
    if target_file:
        # Migrar apenas o arquivo específico
        if os.path.exists(target_file):
            total_updated += migrate_product_database(target_file, dry_run)
        else:
            print(f"ERRO: Arquivo alvo não encontrado: {target_file}")
    else:
        # Migrar arquivos de produtos
        data_dir = "/app/data"
        if os.path.exists(data_dir) and os.path.isdir(data_dir):
            print(f"Verificando diretório: {data_dir}")
            product_files = glob.glob(os.path.join(data_dir, "products_*.json"))
            print(f"Encontrados {len(product_files)} arquivos de produto.")
            
            for product_file in product_files:
                total_updated += migrate_product_database(product_file, dry_run)
        else:
            print(f"AVISO: Diretório de dados não encontrado: {data_dir}")
            
            # Tentar diretório atual como fallback
            current_dir = os.getcwd()
            print(f"Tentando diretório atual: {current_dir}")
            product_files = glob.glob(os.path.join(current_dir, "products_*.json"))
            print(f"Encontrados {len(product_files)} arquivos de produto.")
            
            for product_file in product_files:
                total_updated += migrate_product_database(product_file, dry_run)
    
    print(f"\n{'=' * 50}")
    print(f"Migração {'simulada ' if dry_run else ''}completa. Total de {total_updated} timestamps {'seriam' if dry_run else 'foram'} atualizados.")
    print(f"{'=' * 50}")

if __name__ == "__main__":
    # Verificar argumentos da linha de comando
    import argparse
    parser = argparse.ArgumentParser(description='Migrar timestamps para o timezone do Brasil')
    parser.add_argument('--file', '-f', help='Arquivo específico para migrar')
    parser.add_argument('--dry-run', '-d', action='store_true', help='Apenas simular, sem fazer alterações')
    
    args = parser.parse_args()
    
    run_migration(args.file, args.dry_run)