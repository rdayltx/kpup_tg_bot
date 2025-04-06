#!/usr/bin/env python3
"""
Conversor de CSV para o formato do banco de dados de produtos
"""
import pandas as pd
import json
import os
import argparse
from datetime import datetime

# Função para limpar strings
def clean_string(text):
    if not isinstance(text, str) or pd.isna(text):
        return ""
    text = text.replace('"', "'")
    return text.strip()

def normalize_price(price_str):
    if not price_str or pd.isna(price_str):
        return "0.00"
    price_str = str(price_str).replace('R$', '').replace('$', '').strip()
    return price_str

def parse_date(date_str, asin_for_debug=""):
    if not date_str or pd.isna(date_str):
        return datetime.now().isoformat()
    formats = [
        "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M",
        "%Y/%m/%d", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(str(date_str), fmt)
            return dt.isoformat()
        except ValueError:
            continue
    print(f"Aviso: Não foi possível interpretar a data '{date_str}' para o ASIN '{asin_for_debug}'. Usando data atual.")
    return datetime.now().isoformat()

def convert_csv_to_db(csv_file, account_id, output_file=None):
    if not os.path.exists(csv_file):
        print(f"Erro: Arquivo CSV não encontrado: {csv_file}")
        return None
    
    if not output_file:
        dir_name = os.path.dirname(csv_file)
        base_name = os.path.basename(csv_file).split('.')[0]
        output_file = os.path.join(dir_name, f"products_{account_id}.json")
    
    try:
        df = pd.read_csv(csv_file, header=None, names=['asin', 'title', 'price', 'date'], 
                        quotechar='"', on_bad_lines='warn')
        
        products = {}
        for index, row in df.iterrows():
            if pd.isna(row['asin']) or str(row['asin']).strip() == "":
                print(f"Aviso: Pulando linha {index} com ASIN vazio")
                continue
            
            asin = str(row['asin']).strip().upper()
            title = clean_string(row['title'])
            price = normalize_price(row['price'])
            date_str = str(row['date']).strip()
            last_updated = parse_date(date_str, asin)  # Passa o ASIN para depuração
            
            product_entry = {
                "price": price,
                "last_updated": last_updated,
                "product_title": title
            }
            
            products[asin] = product_entry
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(products, f, indent=2, ensure_ascii=False)
        
        print(f"Conversão concluída! {len(products)} produtos convertidos.")
        print(f"Arquivo salvo em: {output_file}")
        return products
    
    except pd.errors.ParserError as e:
        print(f"Erro de parsing no CSV: {str(e)}")
        return None
    except Exception as e:
        print(f"Erro ao processar arquivo CSV: {str(e)}")
        return None

def main():
    """Função principal"""
    parser = argparse.ArgumentParser(description='Converter CSV para o formato do banco de dados de produtos')
    parser.add_argument('csv_file', help='Caminho para o arquivo CSV')
    parser.add_argument('account_id', help='Identificador da conta (ex: Premium, Meraxes)')
    parser.add_argument('--output', '-o', help='Caminho para salvar o arquivo de saída')
    
    args = parser.parse_args()
    
    # Executar conversão
    convert_csv_to_db(args.csv_file, args.account_id, args.output)

if __name__ == "__main__":
    main()