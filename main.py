import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import json
import os
import time
import random
from dotenv import load_dotenv
import urllib.parse

# ==========================================================
# CONFIGURAÇÕES
# ==========================================================
load_dotenv()

BASE = "https://www.sipros.pa.gov.br"
DATA_ALVO = datetime.strptime("26/06/2026", "%d/%m/%Y")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_USER_ID = os.getenv("TELEGRAM_USER_ID")
SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY")
ARQUIVO_ENVIADOS = "processos_enviados.json"

MESES = {
    "Janeiro": 1, "Fevereiro": 2, "Março": 3, "Abril": 4, "Maio": 5, "Junho": 6,
    "Julho": 7, "Agosto": 8, "Setembro": 9, "Outubro": 10, "Novembro": 11, "Dezembro": 12
}

# ==========================================================
# UTILIDADES
# ==========================================================
def carregar_enviados():
    if os.path.exists(ARQUIVO_ENVIADOS):
        with open(ARQUIVO_ENVIADOS, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def salvar_enviados(lista):
    with open(ARQUIVO_ENVIADOS, "w", encoding="utf-8") as f:
        json.dump(lista, f, indent=4, ensure_ascii=False)

def enviar_telegram(texto):
    if not TELEGRAM_TOKEN:
        print("Telegram não configurado.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    dados = {"chat_id": TELEGRAM_USER_ID, "text": texto, "disable_web_page_preview": True, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=dados, timeout=10)
    except Exception as e:
        print("Erro no Telegram:", e)

def obter_periodo(texto):
    texto = texto.replace("Inscrições:", "").strip()
    resultado = re.search(r'(\d+)\s*a\s*(\d+)\s*de\s*([A-Za-zÇçãÃéÉ]+)\s*de\s*(\d+)', texto)
    
    if not resultado:
        return None, None
        
    ano = int(resultado.group(4))
    mes = MESES.get(resultado.group(3))
    
    if not mes:
        return None, None
        
    inicio = datetime(ano, mes, int(resultado.group(1)))
    fim = datetime(ano, mes, int(resultado.group(2)))
    return inicio, fim

def buscar_com_proxy(url_alvo):
    """
    Roteia a requisição pelo ScraperAPI para simular um acesso do Brasil
    e burlar bloqueios de firewall governamental.
    """
    if not SCRAPER_API_KEY:
        # Se estiver sem chave, tenta o acesso direto (para testes locais)
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        return requests.get(url_alvo, headers=headers, timeout=30)
    
    payload = {
        'api_key': SCRAPER_API_KEY, 
        'url': url_alvo, 
        'country_code': 'br'
    }
    proxy_url = 'http://api.scraperapi.com/?' + urllib.parse.urlencode(payload)
    return requests.get(proxy_url, timeout=60)

# ==========================================================
# NÚCLEO DO MONITOR
# ==========================================================
def main():
    # Pausa aleatória entre 0 e 120 segundos. 
    # Somado aos 5 minutos do cron, gera um intervalo variável de 3 a 7 min.
    espera = random.randint(0, 120)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Iniciando máquina. Aguardando {espera}s para simular comportamento humano...")
    time.sleep(espera)
    
    enviados = carregar_enviados()

    # 1. Puxa a página inicial usando o Proxy
    try:
        print("Acessando a página principal do SIPROS...")
        resposta = buscar_com_proxy(BASE + "/selecoes/disponiveis")
        resposta.raise_for_status()
    except Exception as erro:
        print("Erro ao acessar o SIPROS via proxy:", erro)
        return

    soup = BeautifulSoup(resposta.text, 'html.parser')
    cards = soup.select("div.col-sm-4.plan")
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {len(cards)} processos carregados no HTML.")
    encontrados = 0

    for card in cards:
        bloco = card.find('li', id=re.compile(r'^processo_seletivo_'))
        if not bloco:
            continue

        orgao = bloco.find('h1').text.strip() if bloco.find('h1') else "Sem Órgão"
        titulo = bloco.find('span').text.strip() if bloco.find('span') else "Sem Título"

        itens = card.find_all('li')
        inscricoes = salario = vagas = ""
        
        for item in itens:
            texto = item.text.strip()
            if texto.startswith("Inscrições"): inscricoes = texto
            elif texto.startswith("Vencimento"): salario = texto
            elif texto.startswith("Vagas"): vagas = texto

        inicio, fim = obter_periodo(inscricoes)
        
        if not inicio:
            continue

        print(f"Analisando: {orgao}", end=" -> ")

        if fim < DATA_ALVO:
            print("Fim do período atingido (Mais antigos). Interrompendo busca.")
            break

        if inicio > DATA_ALVO:
            print("Mais recente. Pulando.")
            continue

        link_tag = card.find('a', string=re.compile(r'Ler mais'))
        if not link_tag:
            continue
            
        url_detalhe = BASE + link_tag['href']

        if url_detalhe in enviados:
            print("Já está na memória.")
            continue

        print("NOVO! Acessando detalhes...")

        # 2. Puxa a página de detalhes usando o Proxy
        cargos = []
        try:
            resp_detal = buscar_com_proxy(url_detalhe)
            soup_detal = BeautifulSoup(resp_detal.text, 'html.parser')
            
            tag_cargo = soup_detal.find(id="ver_lista_cargo")
            if tag_cargo and tag_cargo.has_attr('data-bind'):
                dados_bind = tag_cargo['data-bind']
                cargos = [c.strip() for c in dados_bind.split("|")]
        except Exception as e:
            print(f"Erro ao raspar cargos de {orgao}: {e}")

        # 3. Monta e envia a mensagem formatada para o Telegram
        mensagem = f"🚨 *NOVO PROCESSO SIPROS*\n\n"
        mensagem += f"🏢 *Órgão:*\n{orgao}\n\n"
        mensagem += f"📌 *Processo:*\n{titulo}\n\n"
        mensagem += f"📅 *{inscricoes}*\n"
        mensagem += f"💰 *{salario}*\n"
        mensagem += f"📌 *{vagas}*\n\n"
        
        if cargos:
            mensagem += "🎯 *Cargos:*\n"
            for c in cargos:
                mensagem += f"• {c}\n"
                
        mensagem += f"\n🔗 [Clique aqui para ler o Edital]({url_detalhe})"

        enviar_telegram(mensagem)
        enviados.append(url_detalhe)
        salvar_enviados(enviados)
        encontrados += 1

    print("=" * 50)
    print(f"Consulta finalizada com sucesso! Novos processos: {encontrados}")

if __name__ == "__main__":
    main()
