from playwright.sync_api import sync_playwright
from datetime import datetime
import re
import time
import random
import json
import os
import requests

from dotenv import load_dotenv

# ==========================================================
# CONFIGURAÇÕES
# ==========================================================

load_dotenv()

BASE = "https://www.sipros.pa.gov.br"

# manter assim durante os testes
DATA_ALVO = datetime.strptime(
    "26/06/2026",
    "%d/%m/%Y"
)

TELEGRAM_TOKEN = os.getenv(
    "TELEGRAM_TOKEN"
)

TELEGRAM_USER_ID = os.getenv(
    "TELEGRAM_USER_ID"
)

ARQUIVO_ENVIADOS = "processos_enviados.json"

MESES = {
    "Janeiro": 1,
    "Fevereiro": 2,
    "Março": 3,
    "Abril": 4,
    "Maio": 5,
    "Junho": 6,
    "Julho": 7,
    "Agosto": 8,
    "Setembro": 9,
    "Outubro": 10,
    "Novembro": 11,
    "Dezembro": 12
}

# ==========================================================
# CONTROLE DE PROCESSOS ENVIADOS
# ==========================================================

def carregar_enviados():
    if not os.path.exists(
        ARQUIVO_ENVIADOS
    ):
        return []

    with open(
        ARQUIVO_ENVIADOS,
        "r",
        encoding="utf-8"
    ) as arquivo:
        return json.load(
            arquivo
        )

def salvar_enviados(lista):
    with open(
        ARQUIVO_ENVIADOS,
        "w",
        encoding="utf-8"
    ) as arquivo:
        json.dump(
            lista,
            arquivo,
            indent=4,
            ensure_ascii=False
        )

# ==========================================================
# TELEGRAM
# ==========================================================

def enviar_telegram(texto):
    if not TELEGRAM_TOKEN:
        print(
            "Telegram não configurado."
        )
        return

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/sendMessage"
    )

    dados = {
        "chat_id": TELEGRAM_USER_ID,
        "text": texto,
        "disable_web_page_preview": True
    }

    try:
        resposta = requests.post(
            url,
            data=dados,
            timeout=20
        )

        if resposta.status_code == 200:
            print(
                "✓ Telegram enviado"
            )
        else:
            print(
                "Erro Telegram:",
                resposta.text
            )

    except Exception as erro:
        print(
            "Falha Telegram:",
            erro
        )

# ==========================================================
# DATAS
# ==========================================================

def obter_periodo(texto):
    texto = texto.replace(
        "Inscrições:",
        ""
    ).strip()

    resultado = re.search(
        r'(\d+)\s*a\s*(\d+)\s*de\s*'
        r'([A-Za-zÇçãÃéÉ]+)\s*de\s*(\d+)',
        texto
    )

    if not resultado:
        return None, None

    inicio = datetime(
        int(resultado.group(4)),
        MESES[resultado.group(3)],
        int(resultado.group(1))
    )

    fim = datetime(
        int(resultado.group(4)),
        MESES[resultado.group(3)],
        int(resultado.group(2))
    )

    return inicio, fim

# ==========================================================
# CARGOS
# ==========================================================

def obter_cargos(page):
    try:
        dados = page.locator(
            "#ver_lista_cargo"
        ).get_attribute(
            "data-bind"
        )

        if dados:
            return [
                cargo.strip()
                for cargo in dados.split("|")
            ]
    except:
        pass

    return []

# ==========================================================
# CONSULTA
# ==========================================================

def consultar(page, detalhe):
    enviados = carregar_enviados()

    page.goto(
        BASE + "/selecoes/disponiveis",
        wait_until="domcontentloaded",
        timeout=60000
    )

    cards = page.locator(
        "div.col-sm-4.plan"
    )

    total = cards.count()

    print()
    print("=" * 60)
    print(
        "Consulta SIPROS"
    )
    print(
        "Data alvo:",
        DATA_ALVO.strftime("%d/%m/%Y")
    )
    print(
        "Processos:",
        total
    )
    print("=" * 60)

    encontrados = 0

    for i in range(total):
        card = cards.nth(i)

        bloco = card.locator(
            "li[id^='processo_seletivo_']"
        )

        if bloco.count() == 0:
            continue

        orgao = bloco.locator(
            "h1"
        ).inner_text().strip()

        titulo = bloco.locator(
            "span"
        ).inner_text().strip()

        itens = card.locator(
            "li"
        )

        inscricoes = ""
        salario = ""
        vagas = ""

        for x in range(
            itens.count()
        ):
            texto = itens.nth(x).inner_text().strip()

            if texto.startswith(
                "Inscrições"
            ):
                inscricoes = texto

            elif texto.startswith(
                "Vencimento"
            ):
                salario = texto

            elif texto.startswith(
                "Vagas"
            ):
                vagas = texto

        inicio, fim = obter_periodo(
            inscricoes
        )

        if not inicio:
            continue

        print(
            f"{i+1}/{total}",
            orgao,
            end=" -> "
        )

        if fim < DATA_ALVO:
            print(
                "fim do período"
            )
            break

        if inicio > DATA_ALVO:
            print(
                "mais recente"
            )
            continue

        link = card.locator(
            "a:has-text('Ler mais')"
        ).get_attribute(
            "href"
        )

        url = BASE + link

        if url in enviados:
            print(
                "já enviado"
            )
            continue

        print(
            "NOVO!"
        )

        detalhe.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        cargos = obter_cargos(
            detalhe
        )

        mensagem = f"""
🚨 NOVO PROCESSO SIPROS

🏢 Órgão:
{orgao}

📌 Processo:
{titulo}

📅 Inscrições:
{inscricoes}

💰 Salário:
{salario}

📌 {vagas}

🎯 Cargos:
"""

        for cargo in cargos:
            mensagem += (
                f"\n• {cargo}"
            )

        mensagem += (
            f"\n\n🔗 {url}"
        )

        print(
            mensagem
        )

        enviar_telegram(
            mensagem
        )

        enviados.append(
            url
        )

        salvar_enviados(
            enviados
        )

        encontrados += 1

    print()
    print("=" * 60)

    print(
        "Novos encontrados:",
        encontrados
    )

    print("=" * 60)

# ==========================================================
# PROGRAMA
# ==========================================================

def main():
    print("Iniciando varredura automatizada na nuvem...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True # <- Alterado para o servidor poder rodar sem erro
        )

        contexto = browser.new_context(
            locale="pt-BR",
            timezone_id="America/Belem"
        )

        page = contexto.new_page()
        detalhe = contexto.new_page()

        # Roda a consulta apenas uma vez e se desliga. O GitHub chama isso a cada 30 minutos.
        consultar(
            page,
            detalhe
        )

        browser.close()
        print("Varredura concluída. Desligando servidor.")

if __name__ == "__main__":
    main()
