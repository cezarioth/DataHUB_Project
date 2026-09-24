#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
# cspell:disable
DataHub - automatizando cadastros.

Unifica:
1. Coleta das fotos da variação/cor aberta na URL.
2. Coleta da descrição estruturada para Mercado Livre.
3. Consulta e confirmação da homologação ANATEL.
4. Assistente de cadastro com IA.

As funções usam a mesma URL e a mesma referência do produto.

V32:
  * Somente Decathlon (código de Gazin e Colombo removido).
  * Interface em tema escuro.
  * Layout responsivo: tudo acompanha o tamanho da janela, com
    divisória arrastável entre o painel de controles e o de conteúdo.
"""

import csv
import json
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import platform
import re
import shutil
import subprocess
import tempfile
import threading
import time
import unicodedata
import zipfile
import webbrowser

import tkinter as tk
import customtkinter as ctk
import urllib.parse
from io import BytesIO
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import sys

if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys.executable).parent
    ASSETS_DIR = Path(sys._MEIPASS) / "assets"
else:
    APP_DIR = Path(__file__).resolve().parent
    ASSETS_DIR = APP_DIR / "assets"

import requests
from bs4 import BeautifulSoup

try:
    from PIL import Image, ImageTk
    PILLOW = True
except ImportError:
    PILLOW = False

SECTION_ORDER = ["Sobre o produto", "Informações técnicas", "Características", "Garantia"]

STOP_WORDS = {
    "avaliações", "avaliação", "avaliações do produto", "comentários", "comentário", "reviews", "review", "customer reviews", "avis clients",
    "perguntas e respostas", "você também pode gostar", "compre junto",
    "produtos similares", "veja também", "relacionados",
    "códigos internos do produto", "codigo interno do produto", "códigos internos", "codigos internos"
}

TECH_ALIASES = {
    "informações técnicas", "informacao tecnica", "informações tecnica",
    "informações tecnicas", "ficha técnica", "ficha tecnica", "dados técnicos",
    "dados tecnicos"
}
CHAR_ALIASES = {"características", "caracteristicas", "características do produto", "caracteristicas do produto"}
GAR_ALIASES = {"garantia"}

# Cabeçalhos usados nas requisições da página e das imagens.
# Mantém a mesma aparência de um navegador comum para reduzir bloqueios do site.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Referer": "https://www.decathlon.com.br/",
    "Connection": "close",
}

# Campos que aparecem em algumas páginas de parceiros/vendedores em formato corrido.
INLINE_LABELS = [
    "Nome", "Gênero", "Indicado para", "Detalhes", "Composição", "Armação", "História do design",
    "Que tamanho escolher?", "O que envolve a parceria com a NBA?", "Armazenamento",
    "Restrição de Uso", "Teste de Qualidade", "Cabedal", "Lingueta", "Palmilha",
    "Solado", "Terreno", "Fechamento", "Marca", "Código do Artigo", "Tecnologia",
    "Tecnologias", "Nível", "Material", "Peso", "Dimensões", "Facilidade de transporte",
    "Conselhos de Manutenção", "Conselhos de manutenção", "Manutenção", "Tipo de jogo",
    "Equilíbrio", "Garantia"
]

# Rótulos de atributo (Nome do item: valor) que a IA às vezes converte para
# "Nome do item. valor" por engano. Depois da resposta da IA, forçamos de
# volta o formato com dois pontos para esses rótulos conhecidos.
ATRIBUTOS_COM_DOIS_PONTOS = sorted(
    set(INLINE_LABELS) | {
        "Altura", "Largura", "Profundidade", "Peso do produto", "Peso bruto",
        "Composição", "Cor", "Voltagem", "Capacidade", "Potência", "Tamanho",
        "Modelo", "Referência", "Código EAN", "Códigos EAN13 do produto",
        "Códigos internos do produto",
    },
    key=len, reverse=True,
)



def formatar_espacamento_informacoes_tecnicas(texto):
    """Padroniza o espaçamento das Informações Técnicas.

    A V36 originalmente procurava apenas "Características:". O template atual
    usa "Características do Produto:", então esta função reconhece os dois
    formatos e normaliza o bloco técnico sem mexer no conteúdo.
    """
    if not texto:
        return texto

    inicio_match = re.search(r'(?im)^\s*Informações\s+T[eé]cnicas\s*:?\s*$', texto)
    if not inicio_match:
        return texto

    fim_match = re.search(
        r'(?im)^\s*(?:Características(?:\s+do\s+Produto)?|Garantia(?:\s+do\s+(?:Fornecedor|fabricante))?)\s*:?\s*$',
        texto[inicio_match.end():]
    )
    if not fim_match:
        return texto

    inicio = inicio_match.end()
    fim = inicio + fim_match.start()
    bloco = texto[inicio:fim]

    linhas = [linha.strip() for linha in bloco.splitlines() if linha.strip()]
    if not linhas:
        return texto

    bloco_formatado = "\n\n".join(linhas)
    return texto[:inicio].rstrip() + "\n\n" + bloco_formatado + "\n\n" + texto[fim:].lstrip()


def _limpar_marcador_linha(linha):
    """Remove marcadores de lista apenas no início da linha."""
    linha = linha.strip()
    linha = re.sub(r'^(?:[-*•▪◦‣]+|\d+[.)])\s+', '', linha)
    return linha.strip()


def normalizar_estrutura_descricao(texto):
    """Normaliza a descrição final da V36 sem criar conteúdo.

    O objetivo é garantir as quatro seções obrigatórias e o padrão de
    espaçamento definido para Decathlon. O conteúdo textual é preservado;
    somente cabeçalhos, marcadores e espaçamento estrutural são ajustados.
    """
    if not texto or not texto.strip():
        return ""

    aliases = {
        "sobre o produto": "Sobre o Produto:",
        "informações técnicas": "Informações Técnicas:",
        "informacao tecnica": "Informações Técnicas:",
        "informações tecnicas": "Informações Técnicas:",
        "informacoes tecnicas": "Informações Técnicas:",
        "características": "Características do Produto:",
        "caracteristicas": "Características do Produto:",
        "características do produto": "Características do Produto:",
        "caracteristicas do produto": "Características do Produto:",
        "garantia": "Garantia do Fornecedor:",
        "garantia do fornecedor": "Garantia do Fornecedor:",
        "garantia do fabricante": "Garantia do Fornecedor:",
    }

    section_re = re.compile(
        r'^\s*(?:\d+[.)]\s*)?(.+?)\s*:?\s*$', re.IGNORECASE
    )

    secoes = {}
    atual = None
    conteudo_sem_secao = []

    for raw in texto.replace("\r\n", "\n").split("\n"):
        linha = _limpar_marcador_linha(raw)
        if not linha:
            if atual:
                secoes.setdefault(atual, []).append("")
            continue

        chave = norm(re.sub(r':\s*$', '', linha))
        chave = re.sub(r'^\d+[.)]\s*', '', chave)
        if chave in aliases:
            atual = chave
            secoes.setdefault(atual, [])
            continue

        if atual:
            secoes[atual].append(linha)
        else:
            conteudo_sem_secao.append(linha)

    # Se a IA omitiu o cabeçalho inicial, não perdemos o conteúdo: ele entra
    # em Sobre o Produto. O validador final continua exigindo as quatro seções.
    if conteudo_sem_secao:
        secoes.setdefault("sobre o produto", [])
        if secoes["sobre o produto"]:
            secoes["sobre o produto"] = conteudo_sem_secao + [""] + secoes["sobre o produto"]
        else:
            secoes["sobre o produto"] = conteudo_sem_secao

    def compactar_paragrafos(linhas):
        blocos = []
        atual_bloco = []
        for linha in linhas:
            if linha:
                atual_bloco.append(linha)
            elif atual_bloco:
                blocos.append(" ".join(atual_bloco).strip())
                atual_bloco = []
        if atual_bloco:
            blocos.append(" ".join(atual_bloco).strip())
        return [b for b in blocos if b]

    sobre = compactar_paragrafos(secoes.get("sobre o produto", []))
    tecnicas = [x.strip() for x in secoes.get("informações técnicas", []) if x.strip()]
    if not tecnicas:
        # Aceita variantes sem acento já normalizadas no alias.
        for chave in ("informacao tecnica", "informações tecnicas", "informacoes tecnicas"):
            if chave in secoes:
                tecnicas = [x.strip() for x in secoes[chave] if x.strip()]
                break

    caracteristicas = [
        _limpar_marcador_linha(x) for x in secoes.get("características do produto", []) if x.strip()
    ]
    if not caracteristicas:
        for chave in ("características", "caracteristicas"):
            if chave in secoes:
                caracteristicas = [_limpar_marcador_linha(x) for x in secoes[chave] if x.strip()]
                break

    garantia = compactar_paragrafos(secoes.get("garantia do fornecedor", []))
    if not garantia:
        for chave in ("garantia", "garantia do fabricante"):
            if chave in secoes:
                garantia = compactar_paragrafos(secoes[chave])
                break

    # Regra já definida para a V36: fallback exato quando a fonte não trouxe
    # garantia específica. Não fechamos o parêntese porque o texto exigido é
    # exatamente esse.
    if not garantia:
        garantia = ["Garantia de 24 meses (Somente para defeitos de fabrica"]

    partes = []
    partes.append("Sobre o Produto:")
    partes.extend(sobre or [""])
    partes.append("")
    partes.append("Informações Técnicas:")
    for i, item in enumerate(tecnicas):
        partes.append(item)
        if i < len(tecnicas) - 1:
            partes.append("")
    partes.append("")
    partes.append("Características do Produto:")
    partes.extend(caracteristicas)
    partes.append("")
    partes.append("Garantia do Fornecedor:")
    partes.extend(garantia)

    return "\n".join(partes).strip()


def _extrair_secoes_descricao(texto):
    """Retorna as quatro seções canônicas da descrição para validação."""
    texto = normalizar_estrutura_descricao(texto)
    padroes = [
        ("sobre", r'(?im)^Sobre o Produto:\s*$'),
        ("tecnicas", r'(?im)^Informações Técnicas:\s*$'),
        ("caracteristicas", r'(?im)^Características do Produto:\s*$'),
        ("garantia", r'(?im)^Garantia do Fornecedor:\s*$'),
    ]
    encontrados = []
    for chave, padrao in padroes:
        m = re.search(padrao, texto)
        if not m:
            return None
        encontrados.append((chave, m))

    ordem = [m.start() for _, m in encontrados]
    if ordem != sorted(ordem):
        return None

    secoes = {}
    for i, (chave, m) in enumerate(encontrados):
        inicio = m.end()
        fim = encontrados[i + 1][1].start() if i + 1 < len(encontrados) else len(texto)
        secoes[chave] = texto[inicio:fim].strip("\n")
    return secoes


def validar_descricao_deterministica(fonte, descricao):
    """Validador final local: estrutura, marcadores e números não suportados.

    Ele não tenta julgar fatos por conta própria. Apenas bloqueia padrões
    objetivos que podem ser verificados sem IA.
    """
    erros = []
    secoes = _extrair_secoes_descricao(descricao)
    if secoes is None:
        return False, ["As quatro seções não estão presentes na ordem obrigatória."]

    linhas = descricao.replace("\r\n", "\n").split("\n")
    for i, linha in enumerate(linhas, 1):
        if re.match(r'^\s*(?:[-*•▪◦‣]+|\d+[.)])\s+', linha):
            erros.append(f"Marcador de lista encontrado na linha {i}.")

    # Características: uma por linha, sem linha em branco.
    if any(not l.strip() for l in secoes["caracteristicas"].splitlines()):
        erros.append("Há linha em branco dentro de Características do Produto.")

    # Informações técnicas: exatamente um separador em branco entre blocos.
    bloco = secoes["tecnicas"].strip()
    if bloco:
        if re.search(r'\n{3,}', bloco):
            erros.append("Há mais de uma linha em branco entre informações técnicas.")
        if "\n" in bloco and not re.search(r'\S\n\n\S', bloco):
            erros.append("As informações técnicas não estão separadas por uma linha em branco.")

    # Números presentes na saída devem existir na fonte, com exceções de
    # transformações permitidas (ex.: garantia de 2 anos -> 24 meses).
    def numeros(txt):
        return re.findall(r'(?<![A-Za-zÀ-ÿ])(\d+(?:[.,]\d+)?)(?![A-Za-zÀ-ÿ])', txt or "")

    fonte_nums = set(numeros(fonte))
    desc_nums = set(numeros(descricao))
    permitidos = {"24"}
    inesperados = sorted(n for n in desc_nums if n not in fonte_nums and n not in permitidos)
    if inesperados:
        erros.append("Números não encontrados na fonte: " + ", ".join(inesperados))

    garantia = secoes["garantia"].strip()
    if not garantia:
        erros.append("A garantia está vazia.")

    return not erros, erros

def restaurar_dois_pontos_atributos(texto):
    """Corrige linhas em que a IA trocou 'Rótulo: valor' por 'Rótulo. valor'
    para os rótulos técnicos conhecidos (ex.: 'Composição. 86,8 por cento'
    -> 'Composição: 86,8 por cento')."""
    if not texto:
        return texto
    linhas = texto.split("\n")
    saida = []
    for linha in linhas:
        nova = linha
        for label in ATRIBUTOS_COM_DOIS_PONTOS:
            padrao = re.compile(rf"^(\s*{re.escape(label)})\.(\s+)", re.IGNORECASE)
            m = padrao.match(nova)
            if m:
                nova = f"{m.group(1)}:{m.group(2)}" + nova[m.end():]
                break
        saida.append(nova)
    return "\n".join(saida)



def norm(s):
    s = (s or "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip().casefold()




def normalize_celsius(text):
    """Converte temperaturas no formato numérico seguido de C para Graus Celsius."""
    return re.sub(r'(?<![\w])(\d+(?:[.,]\d+)?)\s*[°º]?\s*C\b', r'\1 Graus Celsius', text)

def clean_text(text, keep_parentheses=False):
    text = (text or "").replace("\xa0", " ")
    text = text.replace("™", "").replace("®", "").replace("²", "")
    text = re.sub(r"(\d+(?:[.,]\d+)?)\s*%", r"\1 por cento", text)
    text = text.replace("/", " e ")
    if not keep_parentheses:
        text = text.replace(":", ",")
        text = re.sub(r"\(([^()]*)\)", r"\1", text)
    # Remove símbolos indesejados, mas preserva acentos e pontuação permitida.
    allowed = r"[^\wÀ-ÿ\s.,?!():]" if keep_parentheses else r"[^\wÀ-ÿ\s.,?!]"
    text = re.sub(allowed, " ", text, flags=re.UNICODE)
    text = text.replace("–", " ").replace("—", " ").replace("-", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[ \t]*([.,?!])[ \t]*", r"\1 ", text)
    text = re.sub(r"([.!?])([A-Za-zÀ-ÿ0-9])", r"\1 \2", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return normalize_celsius(text.strip())


def normalize_guarantee(text):
    """Converte prazos de garantia expressos em anos para meses."""
    text = clean_text(text, True)
    def repl(m):
        raw = m.group(1).replace(',', '.')
        try:
            months = float(raw) * 12
            if months.is_integer():
                value = str(int(months))
            else:
                value = str(months).replace('.', ',')
            return f"{value} meses"
        except ValueError:
            return m.group(0)
    text = re.sub(r"(?i)\b(\d+(?:[.,]\d+)?)\s*anos?\b", repl, text)

    # A integração do Mercado Livre aceita a garantia somente em meses.
    # Converte também garantias expressas em dias (ex.: 365 dias -> 12 meses).
    def days_to_months(m):
        days = float(m.group(1).replace(',', '.'))
        months = round(days / 30)
        if months < 1 and days > 0:
            months = 1
        return f"{months} meses"

    text = re.sub(r"(?i)\b(\d+(?:[.,]\d+)?)\s*dias?\b", days_to_months, text)
    text = re.sub(r"(?i)\bgarantia\s+de\s+(\d+(?:[.,]\d+)?)\s*mes(?:es)?\b", lambda m: f"Garantia de {m.group(1).replace(',', '.').rstrip('0').rstrip('.') if '.' in m.group(1) else m.group(1)} meses", text)
    return text


def clean_char(label, answer):
    label = clean_text(label, True).rstrip(".,?!: ")
    answer = clean_text(answer, True).lstrip(" ,:; ")
    return f"{label}: {answer}" if answer else label


# ============================================================
# PADRÃO DE CADASTRO (PROMPT MASTER) - PRECODE / CASAS BAHIA
# ============================================================
# Reorganiza o conteúdo já extraído (Sobre o produto / Informações
# técnicas / Características / Garantia) no formato de cadastro para
# marketplaces definido no Prompt Master: Título, Descrição Comercial,
# Características, Dimensões, Garantia, Recomendações de Conservação
# e Observações (padrão PRECODE), ou Descrição Comercial, Diferenciais,
# Características, Dimensões e Informações Importantes (padrão CASAS
# BAHIA). Nenhuma informação é inventada: apenas o que já foi coletado
# da página é reorganizado e reformatado.

FORMATOS_CADASTRO = ("PRECODE", "CASAS BAHIA")

DIMENSAO_LABELS = {"altura", "largura", "profundidade", "peso", "peso do produto", "peso bruto"}
DIMENSAO_ORDEM = ["altura", "largura", "profundidade", "peso do produto", "peso bruto", "peso"]

RECOMENDACOES_CONSERVACAO = (
    "Evitar exposição direta à luz solar e à umidade.\n"
    "Limpar com pano macio e seco.\n"
    "Não utilizar produtos químicos como álcool, alvejante, desinfetante, "
    "detergente, sabão em pó ou sabão líquido."
)

OBSERVACOES_PADRAO = (
    "Imagens meramente ilustrativas.\n"
    "Objetos decorativos, eletrodomésticos e demais itens ambientados não "
    "acompanham o produto.\n"
    "As cores podem sofrer variações de acordo com o monitor, iluminação "
    "do ambiente e percepção visual."
)

DIFERENCIAIS_LABELS = {
    "estrutura": "Estrutura em {valor}",
    "material": "Estrutura em {valor}",
    "pintura": "Pintura {valor}",
    "tipo de pintura": "Pintura {valor}",
    "quantidade de portas": "{valor} porta(s)",
    "quantidade de gavetas": "{valor} gaveta(s)",
    "quantidade de nichos": "{valor} nicho(s)",
    "quantidade de prateleiras": "{valor} prateleira(s)",
    "tipo de dobradiças": "Dobradiças {valor}",
    "material dos puxadores": "Puxadores em {valor}",
}


def extrair_nome_produto(soup, referencia=""):
    """Nome comercial do produto (via <title> ou JSON-LD), usado como
    Título do cadastro. Nunca inventa: se não achar, cai na referência."""
    nome = ""
    try:
        if soup.title:
            nome = soup.title.get_text(" ", strip=True)
            nome = re.sub(r"\s*[\|\-–]\s*Decathlon.*$", "", nome, flags=re.I).strip()
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or tag.get_text())
            except Exception:
                continue
            itens = data if isinstance(data, list) else [data]
            for d in itens:
                if not isinstance(d, dict):
                    continue
                grafo = d.get("@graph", [d])
                grafo = grafo if isinstance(grafo, list) else [grafo]
                for x in grafo:
                    if isinstance(x, dict) and x.get("@type") == "Product" and x.get("name"):
                        nome = x["name"]
    except Exception:
        pass
    return nome.strip() or referencia


def _rotulo(item):
    return norm(item.split(":", 1)[0]) if ":" in item else ""


def separar_dimensoes(itens):
    """Tira da lista de características/informações técnicas os campos que
    são dimensões (Altura, Largura, Profundidade, Peso), pois o Prompt
    Master exige uma seção Dimensões separada."""
    restantes, encontradas = [], {}
    for item in itens:
        rotulo = _rotulo(item)
        if rotulo in DIMENSAO_LABELS:
            encontradas.setdefault(rotulo, item)
        else:
            restantes.append(item)
    dimensoes = [encontradas[r] for r in DIMENSAO_ORDEM if r in encontradas]
    return restantes, dimensoes


def formatar_garantia_padrao(itens):
    """'<tempo> contra defeitos de fabricação.', com 90 dias/3 meses
    sempre convertidos para '3 Meses contra defeitos de fabricação.'."""
    texto = " ".join(t for t in itens if t).strip()
    if not texto:
        return ""
    normalizado = normalize_guarantee(texto)
    m = re.search(r"(\d+)\s*meses?\b", normalizado, re.I)
    if m:
        valor = m.group(1)
        if valor == "3" or re.search(r"\b90\s*dias?\b", texto, re.I):
            return "3 Meses contra defeitos de fabricação."
        valor = valor.zfill(2)
        return f"{valor} Meses contra defeitos de fabricação."
    if "contra defeitos de fabricação" in normalizado.lower():
        return normalizado
    return f"{normalizado.rstrip('.')} contra defeitos de fabricação."


def montar_diferenciais(itens):
    diferenciais = []
    for item in itens:
        if ":" not in item:
            continue
        rotulo, valor = item.split(":", 1)
        molde = DIFERENCIAIS_LABELS.get(norm(rotulo))
        valor = valor.strip()
        if molde and valor:
            diferenciais.append(molde.format(valor=valor))
    return dedupe(diferenciais)


def montar_cadastro_precode(nome, sobre, tecnicos, caracteristicas, garantia_itens):
    """Monta o cadastro no padrão PRECODE do Prompt Master."""
    chars_finais, dimensoes = separar_dimensoes(dedupe(list(tecnicos) + list(caracteristicas)))
    blocos = []
    if nome:
        blocos.append(nome.strip())
    if sobre:
        texto_sobre = "\n\n".join(s for s in sobre if s).strip()
        if texto_sobre:
            blocos.append(texto_sobre)
    if chars_finais:
        blocos.append("Características\n\n" + "\n".join(chars_finais))
    if dimensoes:
        blocos.append("Dimensões\n\n" + "\n".join(dimensoes))
    garantia = formatar_garantia_padrao(garantia_itens)
    if garantia:
        blocos.append("Garantia\n\n" + garantia)
    blocos.append("Recomendações de Conservação\n\n" + RECOMENDACOES_CONSERVACAO)
    blocos.append("Observações\n\n" + OBSERVACOES_PADRAO)
    return "\n\n".join(b for b in blocos if b)


def montar_cadastro_casas_bahia(nome, sobre, tecnicos, caracteristicas, garantia_itens):
    """Monta o cadastro no padrão CASAS BAHIA do Prompt Master."""
    chars_finais, dimensoes = separar_dimensoes(dedupe(list(tecnicos) + list(caracteristicas)))
    diferenciais = montar_diferenciais(chars_finais)
    blocos = []
    if nome:
        blocos.append(nome.strip())
    if sobre:
        texto_sobre = "\n\n".join(s for s in sobre if s).strip()
        if texto_sobre:
            blocos.append(texto_sobre)
    if diferenciais:
        blocos.append("Diferenciais\n\n" + "\n".join(diferenciais))
    if chars_finais:
        blocos.append("Características\n\n" + "\n".join(chars_finais))
    if dimensoes:
        blocos.append("Dimensões\n\n" + "\n".join(dimensoes))
    garantia = formatar_garantia_padrao(garantia_itens)
    if garantia:
        blocos.append("Informações Importantes\n\n" + "Garantia de " + garantia)
    return "\n\n".join(b for b in blocos if b)


def montar_cadastro(formato, nome, sobre, tecnicos, caracteristicas, garantia_itens):
    if (formato or "").strip().upper() == "CASAS BAHIA":
        return montar_cadastro_casas_bahia(nome, sobre, tecnicos, caracteristicas, garantia_itens)
    return montar_cadastro_precode(nome, sobre, tecnicos, caracteristicas, garantia_itens)


def get_page(url):
    last = None
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "close",
    }
    for attempt in range(3):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=35) as r:
                return r.read()
        except (HTTPError, URLError, TimeoutError, OSError) as e:
            last = e
            time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"Não foi possível acessar a página da Decathlon. {last}")


def visible_soup(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    return soup


def exact_markers(soup, aliases):
    found = []
    for tag in soup.find_all(True):
        txt = norm(tag.get_text(" ", strip=True))
        if txt in aliases and len(txt) < 100:
            found.append(tag)
    return found


def best_marker(soup, aliases):
    candidates = exact_markers(soup, aliases)
    if not candidates:
        return None
    # Prefer headings and candidates followed by meaningful headings/paragraphs.
    score = {}
    for tag in candidates:
        s = 0
        if tag.name in {"h1", "h2", "h3", "h4", "h5", "h6"}: s += 10
        nxt = tag.find_next(["h3", "h4", "h5", "p"])
        if nxt: s += 5
        score[id(tag)] = s
    return max(candidates, key=lambda x: score[id(x)])


def iter_blocks_after(marker, stop_aliases, limit=800):
    """Extrai apenas blocos de conteúdo, sem repetir texto de wrappers HTML.

    A Decathlon costuma colocar o mesmo texto em uma árvore de div/span/p.
    Percorrer todos os elementos gera exatamente o problema que apareceu no
    teste: o mesmo parágrafo é capturado 2 ou 3 vezes. Aqui só aceitamos o
    bloco semântico mais interno e deduplicamos pelo TEXTO, não pelo tipo de tag.
    """
    if not marker:
        return []

    candidates = ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "strong", "b")
    blocks = []
    seen_text = set()

    # Começa depois do marcador e para na próxima seção de primeiro nível.
    for tag in marker.find_all_next(candidates):
        txt = tag.get_text(" ", strip=True)
        if not txt:
            continue
        n = norm(txt)

        if n in stop_aliases or n in STOP_WORDS:
            break
        if tag.name in {"h1", "h2"} and n in TECH_ALIASES | CHAR_ALIASES | GAR_ALIASES:
            break

        # Não capture um p que seja apenas o conteúdo de um título strong/b.
        if tag.name == "p":
            strong_children = tag.find_all(["strong", "b"], recursive=False)
            if strong_children and norm(tag.get_text(" ", strip=True)) == norm(strong_children[0].get_text(" ", strip=True)):
                continue

        # Evita que um bloco pai e seus filhos gerem a mesma informação.
        # O texto é a identidade real do conteúdo para a nossa finalidade.
        key = norm(txt)
        if key in seen_text:
            continue

        # Ignora containers comerciais/navegação que escapem pelos títulos.
        if len(txt) > 2000:
            continue

        seen_text.add(key)
        blocks.append((tag.name, txt))
        if len(blocks) >= limit:
            break

    return blocks


def split_technical_inline_fields(text):
    """Separa especificações que a página entregou dentro do mesmo bloco de texto."""
    if not text:
        return []
    labels = sorted(INLINE_LABELS, key=len, reverse=True)
    # Só usa rótulos que fazem sentido na área técnica.
    labels = [x for x in labels if x not in {"Nome", "Gênero", "Indicado para", "Detalhes", "Características", "Garantia"}]
    alt = "|".join(re.escape(x) for x in labels)
    rx = re.compile(rf"(?<!\w)({alt})\s*(?::|,|\u00a0)", re.I)
    matches = list(rx.finditer(text))
    if not matches:
        return [text]
    parts = []
    # Texto anterior ao primeiro rótulo também é preservado.
    if matches[0].start() > 0:
        prefix = text[:matches[0].start()].strip(" \t,;|-")
        if prefix:
            parts.append(prefix)
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        value = text[m.start():end].strip(" \t,;|-")
        if value:
            parts.append(value)
    return parts or [text]


def group_technical(blocks):
    """Mantém somente o conteúdo técnico oficial, na ordem original.

    Regra crítica da Decathlon:
    depois dos blocos técnicos (ex.: Conselhos de Manutenção), a página pode
    inserir nomes/notas de avaliadores antes de Características. Esses itens
    são descartados como um grupo, nunca como conteúdo do produto.
    """
    result = []
    current_title = None
    current_text = []
    after_maintenance = False
    possible_review_names = []

    technical_titles = {
        "composição", "armazenamento", "restrição de uso",
        "conselhos de manutenção", "conselhos de manutenção do produto",
        "teste de qualidade", "garantia"
    }

    def looks_like_person_name(txt):
        txt = txt.strip()
        if not txt or len(txt) > 50 or len(txt.split()) > 3:
            return False
        if re.search(r"\d", txt):
            return False
        # Nome próprio simples; não considera títulos técnicos conhecidos.
        if norm(txt) in technical_titles:
            return False
        return bool(re.fullmatch(
            r"[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý'’.-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý'’.-]*){0,2}",
            txt
        ))

    def flush():
        nonlocal current_title, current_text
        if current_title:
            title = clean_text(current_title, True).rstrip(".,?!: ")
            if current_text:
                result.append(title)
                for body_part in current_text:
                    body = clean_text(body_part, True)
                    if body:
                        result.append(body)
            else:
                result.append(title)
        elif current_text:
            for part in current_text:
                cleaned = clean_text(part, True)
                if cleaned:
                    result.append(cleaned)
        current_title, current_text = None, []

    def discard_review_run():
        nonlocal possible_review_names
        possible_review_names = []

    for name, txt in blocks:
        n = norm(txt)
        stripped = txt.strip()

        # Marcadores explícitos de avaliação.
        if n in {
            "guillaume", "thomas", "ryan", "christophe", "aliès", "alies",
            "klaudia", "6076", "5 e 5", "5/5"
        }:
            if after_maintenance:
                discard_review_run()
                continue
            continue

        if re.fullmatch(
            r"\d+(?:[.,]\d+)?\s*(?:e|de|/)\s*\d+(?:[.,]\d+)?"
            r"(?:\s*(?:de\s*)?5)?",
            n
        ):
            continue

        # "Características" é o marcador de saída da ficha técnica.
        if n in CHAR_ALIASES:
            flush()
            break

        is_question_title = stripped.endswith("?") and len(stripped) <= 320
        is_known_title = n in technical_titles
        is_title = (
            name in {"h3", "h4", "h5", "h6", "strong", "b"}
            or is_question_title
            or is_known_title
            or n in {norm(x) for x in INLINE_LABELS}
        )

        # Quando estamos no fim da ficha e encontramos uma sequência de nomes
        # curtos, não os adicionamos ao resultado. "Características" encerra
        # definitivamente essa região.
        if after_maintenance and not is_title and looks_like_person_name(stripped):
            possible_review_names.append(stripped)
            if len(possible_review_names) >= 2:
                # Remove também eventual primeiro nome já colocado no buffer.
                if result and result[-1] == possible_review_names[0]:
                    result.pop()
                possible_review_names = []
            continue

        # Se um nome isolado foi seguido por conteúdo real, ele não deve ser
        # perdido automaticamente; ele só é considerado avaliação quando há
        # sequência de pelo menos dois nomes.
        if possible_review_names:
            if len(possible_review_names) >= 2:
                possible_review_names = []
            else:
                # Um único nome entre blocos técnicos não é descartado por si só.
                current_text.extend(possible_review_names)
                possible_review_names = []

        if is_title and len(stripped) <= 300:
            flush()
            current_title = stripped
            if n in {"conselhos de manutenção", "conselhos de manutenção do produto"}:
                after_maintenance = True
        else:
            if stripped:
                cleaned = strip_review_content(stripped)
                if cleaned:
                    parts = (
                        [cleaned]
                        if n.startswith("como ") and len(cleaned) > 80
                        else split_technical_inline_fields(cleaned)
                    )
                    current_text.extend(parts)

    # Nunca deixa nomes de avaliação pendurados no final.
    possible_review_names = []
    flush()

    # Segurança final: remove grupos de 2+ nomes soltos que tenham escapado.
    cleaned_result = []
    i = 0
    while i < len(result):
        if looks_like_person_name(result[i]):
            j = i
            while j < len(result) and looks_like_person_name(result[j]):
                j += 1
            if j - i >= 2:
                i = j
                continue
        cleaned_result.append(result[i])
        i += 1

    return cleaned_result


COMMERCIAL_PATTERNS = [
    r"\b\d[\d.]*\s+vendidos?\b", r"\b\d[\d.]*\s+pessoas\s+favoritaram\b",
    r"\bref\s*[:.]", r"\bc[oó]digo\s+do\s+artigo\b", r"\bvendido\s+e\s+entregue\s+por\b",
    r"\bpor\s+r\$", r"\br\$\s*[\d.,]+", r"\bpre[cç]o\b", r"\bparcel", r"\bfrete\b",
    r"\bcalcular\s+frete\b", r"\bcompre\b", r"\bcashback\b", r"\bavalia[cç][oõ]es?\b", r"\bcoment[aá]rios?\b", r"\breviews?\b",
]

def strip_review_content(text):
    """Remove qualquer conteúdo de avaliações que tenha sido anexado ao bloco do produto."""
    if not text:
        return text
    # Alguns componentes da Decathlon inserem a avaliação dentro do mesmo bloco
    # HTML do texto oficial, sem um título separado. Nesses casos aparecem padrões
    # como "5 e 5", "5/5", "5 estrelas" e, em seguida, nome/opinião do cliente.
    patterns = [
        r"\s+\d+(?:[.,]\d+)?\s*e\s*\d+(?:[.,]\d+)?\s*$",
        r"\s+\d+(?:[.,]\d+)?\s+de\s+5\b.*$",
        r"\s+\d+(?:[.,]\d+)?\s*/\s*5\b.*$",
        r"\s+\d+(?:[.,]\d+)?\s+estrelas?\b.*$",
    ]
    # O primeiro padrão só remove a parte de nota quando ela estiver no final.
    # Para o caso observado, a nota é seguida pelo conteúdo do avaliador, então
    # truncamos no primeiro marcador inequívoco de avaliação.
    marker_patterns = [
        r"\s+\d+(?:[.,]\d+)?\s*e\s*\d+(?:[.,]\d+)?\b",
        r"\s+\d+(?:[.,]\d+)?\s*/\s*5\b",
        r"\s+\d+(?:[.,]\d+)?\s+de\s+5\b",
        r"\s+\d+(?:[.,]\d+)?\s+estrelas?\b",
    ]
    positions = []
    for p in marker_patterns:
        m = re.search(p, text, re.I)
        if m:
            positions.append(m.start())
    if positions:
        text = text[:min(positions)].rstrip()
    return text

def strip_style_review_noise(text):
    """Remove blocos de avaliações que aparecem como 'Estilo' + nome do avaliador."""
    if not text:
        return text
    # Alguns blocos de avaliações da Decathlon aparecem como conteúdo curto,
    # sem o título 'Avaliações'. Exemplos: 'Estilo', 'Charlene', 'Rui Lopes'.
    lines = [x.strip() for x in re.split(r"\n+", text) if x.strip()]
    if not lines:
        return text
    review_names = re.compile(r"^[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-ÿ'’-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-ÿ'’-]*){1,3}$")
    out = []
    skip_name = False
    for line in lines:
        n = norm(line)
        if n == "estilo":
            # 'Estilo' isolado é ruído quando está acompanhado por nomes de clientes.
            skip_name = True
            continue
        if skip_name and review_names.match(line) and len(line) <= 60:
            skip_name = False
            continue
        skip_name = False
        out.append(line)
    return "\n".join(out).strip()

def strip_style_suggestion(text):
    """Remove sugestões de outros produtos e nomes soltos de produtos sugeridos."""
    if not text:
        return text
    lines = [x.strip() for x in re.split(r"\n+", text) if x.strip()]
    out = []
    suggestion_patterns = [
        r"\bcombinam?\s+(?:perfeitamente\s+)?com\b",
        r"\bcombina\s+(?:perfeitamente\s+)?com\b",
        r"\bcombine\s+(?:este|esta|estes|estas)?\s*(?:produto|peça|peca|look)?\s*com\b",
        r"\bideal\s+para\s+combinar\b",
        r"\bperfeito\s+para\s+combinar\b",
        r"\bcomplete\s+(?:o|a)\s+look\b",
        r"\bveja\s+(?:também|tambem)\b",
        r"\bvocê\s+(?:também|tambem)\s+pod(?:e|em)\b",
        r"\bprodutos?\s+relacionados?\b",
        r"\bprodutos?\s+similares?\b",
        r"\bsugest(?:ão|oes|ões)\s+(?:de|para)\b",
    ]
    standalone_name = re.compile(r"^[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý'’.-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý'’.-]*){0,2}$")
    skip_names = False
    for line in lines:
        is_suggestion = any(re.search(p, line, re.I) for p in suggestion_patterns)
        if is_suggestion:
            skip_names = True
            continue
        # Após uma sugestão removida, a página costuma deixar o nome do modelo
        # ou da pessoa/produto recomendado em uma linha isolada (ex.: Charlene, Christelle).
        if skip_names and (norm(line) == "estilo" or standalone_name.match(line)) and len(line) <= 60:
            continue
        skip_names = False
        # O marcador "Estilo" só é ruído quando aparece isolado; não remova
        # a palavra quando estiver dentro de uma frase descritiva do produto.
        if norm(line) == "estilo":
            continue
        out.append(line)
    # Algumas páginas deixam, após o texto oficial de uso, uma sequência de
    # nomes de modelos/produtos sugeridos em linhas isoladas (ex.: Charlene,
    # Christelle). Como são dois ou mais nomes consecutivos e não formam uma
    # frase do produto atual, removemos somente essa sequência final.
    standalone_name = re.compile(r"^[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý'’.-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý'’.-]*){0,2}$")
    while len(out) >= 2 and all(standalone_name.match(x) for x in out[-2:]) and not any(norm(x) in {"composição", "armação", "cabedal", "palmilha", "lingueta"} for x in out[-2:]):
        out.pop()
    return "\n".join(out).strip()

def is_review_only_text(text):
    """Remove qualquer conteúdo que pertença a avaliações de clientes.
    A descrição do produto nunca deve conter nomes, notas ou comentários de clientes.
    """
    if not text:
        return False
    n = norm(text)
    review_terms = (
        "avaliação", "avaliações", "avaliacao", "avaliacoes",
        "comentário de cliente", "comentários de clientes",
        "comentario de cliente", "comentarios de clientes",
        "review", "reviews", "customer review", "customer reviews",
        "nota dos clientes", "opinião dos clientes", "opiniao dos clientes",
        "classificação dos clientes", "classificacao dos clientes",
        "pergunta de cliente", "perguntas de clientes",
    )
    if any(t in n for t in review_terms):
        return True
    # Padrões de nota que aparecem em blocos de avaliação.
    if re.search(r"\b\d(?:[.,]\d)?\s*(?:/\s*5|de\s*5|estrelas?)\b", n, re.I):
        return True
    # Blocos muito curtos que são apenas nomes de pessoas não são conteúdo do produto.
    if re.fullmatch(r"[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý'’.-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý'’.-]*){0,3}", text.strip()) and len(text.strip()) <= 60:
        return True
    return False

def is_commercial_text(text):
    n=norm(text)
    if not n: return True
    return any(re.search(p, n, re.I) for p in COMMERCIAL_PATTERNS)

def jsonld_descriptions(raw_html):
    vals=[]
    soup=BeautifulSoup(raw_html, "html.parser")
    for script in soup.find_all("script", attrs={"type":"application/ld+json"}):
        txt=script.string or script.get_text()
        if not txt: continue
        try:
            import json
            data=json.loads(txt)
        except Exception:
            continue
        stack=data if isinstance(data,list) else [data]
        while stack:
            obj=stack.pop()
            if isinstance(obj,dict):
                # Nunca usar texto de avaliações/reviews como descrição do produto.
                obj_type = obj.get("@type")
                if isinstance(obj_type, str) and norm(obj_type) in {"review", "aggregateRating"}:
                    continue
                if "review" in obj or "aggregateRating" in obj:
                    # O objeto pode ser um Product legítimo, então não descartamos
                    # o objeto inteiro; apenas evitamos descrições claramente ligadas a review.
                    pass
                d=obj.get("description")
                if isinstance(d,str) and len(d.strip())>40 and not re.search(r"(?i)\b(?:avalia[cç][oõ]es?|coment[aá]rios?|reviews?)\b", d):
                    vals.append(d.strip())
                for v in obj.values():
                    if isinstance(v,(dict,list)): stack.append(v)
            elif isinstance(obj,list):
                stack.extend(obj)
    return vals

def find_product_description(soup, char_marker, tech_marker, gar_marker, raw_html=None):
    """Captura somente a descrição principal, sem invadir a ficha técnica.

    A página da Decathlon possui containers que englobam a descrição e a seção
    técnica. Por isso não podemos simplesmente percorrer divs depois do título:
    um div pai pode conter a descrição e todo o bloco técnico ao mesmo tempo.
    Priorizamos os parágrafos reais da descrição e só usamos um container como
    fallback quando ele não contém outro título de seção.
    """
    result = []
    stops = CHAR_ALIASES | TECH_ALIASES | GAR_ALIASES | STOP_WORDS

    def contains_section_title(text):
        lines = [norm(x) for x in re.split(r"\n+", text or "") if norm(x)]
        return any(x in stops for x in lines)

    # JSON-LD / dados estruturados continuam sendo a primeira fonte para a
    # descrição, porque não misturam a ficha técnica quando presentes.
    if raw_html:
        for d in jsonld_descriptions(raw_html):
            d = clean_text(BeautifulSoup(d, "html.parser").get_text("\n", strip=True), True)
            if d and not is_commercial_text(d):
                result.append(d)
                break

    markers = exact_markers(
        soup,
        {"descrição", "descricao", "sobre o produto", "descrição do produto", "descricao do produto"}
    )

    # O formato atual da Decathlon usa um <p> para o texto da descrição.
    # Capturamos apenas esses parágrafos até o próximo marcador de seção.
    for marker in markers:
        for tag in marker.find_all_next(["p", "h2", "h3", "h4", "h1"], limit=80):
            if tag is marker:
                continue
            txt = tag.get_text(" ", strip=True)
            if not txt:
                continue
            n = norm(txt)
            if n in stops or contains_section_title(txt):
                break
            if tag.name in {"h1", "h2", "h3", "h4"}:
                break
            if len(txt) >= 25 and not is_commercial_text(txt):
                result.append(clean_text(txt, True))
        if result:
            return dedupe(result)

    # Fallback: somente um bloco curto que não contenha marcadores de seção.
    for marker in markers:
        for tag in marker.find_all_next(["div", "article"], limit=30):
            txt = tag.get_text("\n", strip=True)
            if not txt or len(txt) < 25 or len(txt) > 1200:
                continue
            if contains_section_title(txt) or is_commercial_text(txt):
                continue
            result.append(clean_text(txt, True))
            if result:
                return dedupe(result)

    return dedupe(result)



def extract_characteristics(soup, marker, tech_marker, gar_marker):
    if not marker:
        return []
    stop_aliases = TECH_ALIASES | GAR_ALIASES | STOP_WORDS
    items = []
    seen = set()
    for tag in marker.find_all_next(["h3", "h4", "h5", "p", "h2"]):
        txt = tag.get_text("\n", strip=True)
        if not txt: continue
        n = norm(txt)
        if n in stop_aliases or any(term in n for term in ("avaliação", "avaliações", "comentário", "comentários", "reviews", "review")):
            break
        if tag.name in {"h2", "h3", "h4"} and any(term in n for term in ("avaliação", "avaliações", "comentário", "comentários", "reviews", "review")):
            break
        if tag.name == "h2" and n not in CHAR_ALIASES:
            break
        if tag.name not in {"h3", "h4"}:
            continue
        label = txt
        # Próximo parágrafo antes do próximo card/section.
        answer = ""
        for p in tag.find_all_next("p"):
            prev = p.find_previous(["h2", "h3", "h4", "h5"])
            if prev is not tag:
                break
            pt = p.get_text(" ", strip=True)
            if pt:
                answer = pt
                break
        if not answer:
            # Algumas versões colocam o texto no irmão/mesmo card sem p.
            parent = tag.parent
            if parent:
                texts = []
                for child in parent.find_all(recursive=True):
                    if child.name in {"h3", "h4", "p"} and child is not tag:
                        t = child.get_text(" ", strip=True)
                        if t and norm(t) != n: texts.append(t)
                if texts: answer = texts[-1]
        if answer:
            item = clean_char(label, answer)
            k = norm(item)
            if k not in seen:
                items.append(item); seen.add(k)
    return items


def extract_inline_blob(soup):
    """Extrai páginas em que vários campos aparecem em um bloco corrido."""
    # Aceita tanto "Nome:" quanto "Nome," e "Nome" como separadores quando o HTML
    # separa visualmente o rótulo e o valor.
    labels = sorted(INLINE_LABELS, key=len, reverse=True)
    label_alt = "|".join(re.escape(x) for x in labels)
    rx = re.compile(rf"(?<!\w)({label_alt})\s*(?::|,|\u00a0)", re.I)
    best = None; best_score = 0
    for tag in soup.find_all(["p", "div", "section", "article"]):
        txt = tag.get_text("\n", strip=True)
        if not (80 <= len(txt) <= 20000): continue
        ms = list(rx.finditer(txt))
        if len(ms) < 2: continue
        score = len(ms)
        if re.search(r"\bNome\s*[:,]", txt, re.I): score += 4
        if re.search(r"\bCaracterísticas\s*[:,]", txt, re.I): score += 4
        if score > best_score:
            best, best_score = txt, score
    if not best: return []
    ms = list(rx.finditer(best)); fields=[]
    for i,m in enumerate(ms):
        label=m.group(1).strip(); start=m.end(); end=ms[i+1].start() if i+1<len(ms) else len(best)
        value=best[start:end].strip(" \t,;|-\n")
        if value and not re.search(r"(?i)\b(?:avalia[cç][oõ]es?|coment[aá]rios?|reviews?)\b", value):
            fields.append((label,value))
    return fields


def add_inline(sections, fields):
    about={norm(x) for x in ["Nome","Gênero","Indicado para","Detalhes"]}
    tech={norm(x) for x in INLINE_LABELS if x not in {"Nome","Gênero","Indicado para","Detalhes","Garantia","Características"}}
    for label,value in fields:
        n=norm(label)
        if n==norm("Características"):
            # Se o valor vier como uma sequência de características, não tenta
            # inventar nomes. Mantém o campo como informação da seção.
            sections["Características"].append(clean_text(value,True))
        elif n in about:
            sections["Sobre o produto"].append(clean_text(value,True))
        elif n in tech:
            sections["Informações técnicas"].append(clean_text(f"{label}, {value}",True))
        elif n==norm("Garantia"):
            sections["Garantia"].append(clean_text(f"Garantia de {value}",True))


def format_guarantee_items(items):
    """Normaliza a garantia para o formato do Mercado Livre e mantém tudo em um bloco final."""
    if not items:
        return []
    text = clean_text(" ".join(items), True)
    # Converte prazos para meses antes de montar o texto final.
    text = normalize_guarantee(text)
    # Se a página disser "Este produto conta com X meses de garantia...",
    # transforma para o padrão aprovado, preservando o restante da informação.
    m = re.search(r"(?i)\b(\d+(?:[.,]\d+)?)\s*mes(?:es)?\s+de\s+garantia\b", text)
    if m:
        prazo = m.group(1)
        before = text[:m.start()].strip(" ,.-")
        after = text[m.end():].strip(" ,.-")
        # Remove frases introdutórias sem perder a informação sobre a cobertura.
        if after:
            after = re.sub(r"(?i)^contra\s+", "contra ", after)
            return [f"Garantia de {prazo} meses, {after}"]
        return [f"Garantia de {prazo} meses"]
    # Caso a página já use "Garantia de X meses".
    m = re.search(r"(?i)\bgarantia\s+de\s+(\d+(?:[.,]\d+)?)\s*mes(?:es)?\b", text)
    if m:
        prazo = m.group(1)
        rest = (text[m.end():]).strip(" ,.-")
        return [f"Garantia de {prazo} meses" + (f", {rest}" if rest else "")]
    return [text]


def dedupe(items):
    out=[]; seen=set()
    for x in items:
        x=x.strip()
        if not x: continue
        k=norm(x)
        if k not in seen:
            out.append(x); seen.add(k)
    return out


def remove_standalone_suggestion_names(sections):
    """Remove nomes soltos de modelos/produtos sugeridos capturados como linhas independentes.

    Alguns componentes da Decathlon colocam os nomes de produtos sugeridos dentro
    do mesmo bloco HTML do texto oficial. Por isso a limpeza precisa funcionar
    também quando vários conteúdos estão dentro de um único item.
    """
    known = {norm(x) for x in INLINE_LABELS} | {
        "estilo", "termos e condições de uso", "teste de qualidade",
        "conselhos de manutenção", "composição", "armação"
    }
    name_only = re.compile(
        r"^[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý'’.-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý'’.-]*){0,2}$"
    )

    # Nomes que aparecem nos módulos de recomendação da Decathlon como itens
    # isolados. A regra é aplicada apenas a linhas isoladas, nunca a uma frase.
    def clean_item(item):
        lines = [x.strip() for x in re.split(r"\n+", item) if x.strip()]
        out = []
        for line in lines:
            n = norm(line)
            words = line.split()
            if (
                n not in known
                and 1 <= len(words) <= 3
                and name_only.fullmatch(line)
                and not any(ch in line for ch in ".,!?;:")
                and not re.search(r"\d", line)
            ):
                # Nome/modelo isolado de produto sugerido ou conteúdo de recomendação.
                continue
            out.append(line)
        return "\n\n".join(out).strip()

    for section in ("Sobre o produto", "Informações técnicas"):
        cleaned = []
        for item in sections.get(section, []):
            item = clean_item(item)
            if item:
                cleaned.append(item)
        sections[section] = cleaned
    return sections


def dedupe_sections(sections):
    """Remove duplicatas entre seções, dando prioridade à Garantia para que ela permaneça no final."""
    def key_of(item):
        return re.sub(r"[^\wÀ-ÿ]+", " ", item, flags=re.UNICODE).strip().casefold()

    # A garantia tem prioridade: se o mesmo texto foi capturado também
    # em Informações técnicas, ele deve sair de lá e permanecer no bloco Garantia.
    guarantee_keys = {key_of(x) for x in sections.get("Garantia", []) if x.strip()}

    seen = set()
    for section in SECTION_ORDER[:-1]:
        unique = []
        for item in sections[section]:
            item = item.strip()
            if not item:
                continue
            key = key_of(item)
            if key in guarantee_keys:
                continue
            if key not in seen:
                seen.add(key)
                unique.append(item)
        sections[section] = unique

    # Processa a Garantia por último, garantindo que nunca seja descartada
    # por ter sido encontrada anteriormente em outro bloco da página.
    unique = []
    for item in sections.get("Garantia", []):
        item = item.strip()
        if not item:
            continue
        key = key_of(item)
        if key not in {key_of(x) for x in unique}:
            unique.append(item)
    sections["Garantia"] = unique
    return sections



def remove_size_information(text):
    """Remove conteúdo de tamanho, numeração e tabelas/medidas de tamanho."""
    if not text:
        return text

    headings = [
        r"como\s+escolher\s+(?:o\s+)?tamanho",
        r"como\s+escolher\s+seu\s+tamanho",
        r"que\s+tamanho\s+escolher",
        r"qual\s+tamanho\s+escolher",
        r"escolha\s+seu\s+tamanho",
        r"guia\s+de\s+tamanhos?",
        r"tabela\s+de\s+tamanhos?",
        r"tabela\s+de\s+medidas?",
        r"tamanhos?\s+disponíveis",
    ]

    section_titles = {
        "sobre o produto", "informações técnicas", "características", "garantia",
        "composição", "história do design", "armazenamento", "restrição de uso",
        "teste de qualidade"
    }

    lines = text.splitlines()
    result = []
    skip = False

    for raw in lines:
        norm_line = re.sub(r"\s+", " ", raw.strip()).lower()

        if any(re.search(p, norm_line, re.I) for p in headings):
            skip = True
            continue

        if skip:
            if norm_line in section_titles:
                skip = False
            else:
                continue

        # Qualquer linha explicitamente de tamanho/numeração.
        if re.match(r"^(?:tamanho|numeração|numeracao|número|numero)\s*[:\-]?\s*.+$", norm_line, re.I):
            continue

        if re.search(r"\btamanho\s+único\b", norm_line, re.I):
            continue

        # Linhas com medidas corporais ligadas a tamanho.
        if re.search(r"\b(?:panturrilha|cintura|quadril|peito|tórax|torax|busto|circunferência|circunferencia)\b", norm_line, re.I):
            if re.search(r"\b(?:cm|mm|tamanho|medida|medidas)\b", norm_line, re.I):
                continue

        # Lista isolada de tamanhos.
        if re.fullmatch(
            r"(?:pp|pm|p|m|mg|g|gg|xg|xxg|xs|s|l|xl|xxl)"
            r"(?:\s*[,/;\-]\s*(?:pp|pm|p|m|mg|g|gg|xg|xxg|xs|s|l|xl|xxl))+",
            norm_line, re.I
        ):
            continue

        result.append(raw)

    return re.sub(r"\n{3,}", "\n\n", "\n".join(result)).strip()



TAMANHOS_PRESET = ["1000x1000", "800x800", "500x500", "Personalizado..."]
FORMATOS = ["JPG"]

# https://loja.vteximg.com.br/arquivos/ids/1234567-500-500/nome.jpg
# https://loja.vtexassets.com/arquivos/ids/1234567-800-auto?v=638...
RE_VTEX = re.compile(
    r"https?://[\w.-]*vtex(?:img\.com\.br|assets\.com)/arquivos/ids/(\d+)",
    re.IGNORECASE,
)

# A Decathlon atual usa URLs VTEX embrulhadas pelo CDN "unsafe/..." e
# codificadas com %2F. Por isso procuramos também a URL VTEX interna.
RE_VTEX_URL_COMPLETA = re.compile(
    r"https?://[^\s\"'\<>]+vtex(?:img\.com\.br|assets\.com)[^\s\"'\<>]*",
    re.IGNORECASE,
)

# https://contents.mediadecathlon.com/p/p/<hash>/...jpg?f=500x500
RE_MEDIA = re.compile(
    r"https?://contents\.mediadecathlon\.com/[^\s\"'\<>]+",
    re.IGNORECASE,
)


def _caminho_media_embutido(url: str) -> str:
    """Retorna o caminho do contents.mediadecathlon.com mesmo quando a URL
    está embrulhada por um CDN/VTEX (/unsafe/.../contents.mediadecathlon.com/...)."""
    texto = (url or "").replace("\\/", "/").replace("\u002F", "/")
    for _ in range(4):
        texto = urllib.parse.unquote(texto)
    m = re.search(
        r"https?://contents\.mediadecathlon\.com(?P<path>/[^\s\"'<>]*)",
        texto,
        re.IGNORECASE,
    )
    if m:
        return m.group("path").rstrip("),;]}")
    parsed = urllib.parse.urlparse(texto)
    if parsed.netloc.lower() == "contents.mediadecathlon.com":
        return parsed.path or "/"
    return ""


def _e_foto_produto_mediadecathlon(url: str) -> bool:
    """Aceita somente fotos de produto do CDN MediaDecathlon.

    As fotos de produto ficam em /p/... . Os módulos de benefícios da página,
    como os ícones "Elasticidade" (/b82630/...) e "Fixação" (/b82710/...),
    ficam em /b<número>/ e não podem entrar na galeria. Manuais/PDFs ficam em
    /s<número>/. A checagem também funciona quando a URL está embrulhada em
    /unsafe/ ou outro proxy da VTEX.
    """
    caminho = _caminho_media_embutido(url)
    if not caminho:
        # Não é uma URL MediaDecathlon; deixe a validação VTEX cuidar dela.
        return True

    # Bloqueio explícito dos ícones/benefícios e documentos.
    if re.match(r"^/b\d+(?:/|$)", caminho, re.IGNORECASE):
        return False
    if re.match(r"^/s\d+(?:/|$)", caminho, re.IGNORECASE):
        return False

    # Para MediaDecathlon, a galeria deve apontar para /p/ (fotos de produto).
    return bool(re.match(r"^/p(?:/|$)", caminho, re.IGNORECASE))


def _e_imagem_nao_produto(url: str) -> bool:
    """Detecta recursos MediaDecathlon que aparecem dentro de uma URL VTEX.

    Isso é necessário porque, em URLs /unsafe/..., _id_vtex pode enxergar o
    domínio VTEX externo antes que a URL interna contents.mediadecathlon.com/b...
    seja validada.
    """
    caminho = _caminho_media_embutido(url)
    if not caminho:
        return False
    return not bool(re.match(r"^/p(?:/|$)", caminho, re.IGNORECASE))


RE_JSONLD = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


# --------------------------------------------------------------------------
# Identificação da referência (a partir da URL da página)
# --------------------------------------------------------------------------


def referencia_da_url(url: str) -> str:
    """Extrai a referência do produto a partir da URL da Decathlon."""
    path = urllib.parse.urlparse(url).path
    numeros = re.findall(r"(\d{5,})", path)
    return numeros[-1] if numeros else "produto"


# --------------------------------------------------------------------------
# Serviço de Busca de URL por REF (Decathlon)
# --------------------------------------------------------------------------

REF_CACHE = {}


def normalizar_ref(raw_ref: str) -> str:
    """Limpa e normaliza a REF informada pelo usuário."""
    if not raw_ref:
        return ""
    ref_limpa = raw_ref.strip()
    apenas_numeros = re.sub(r"\D", "", ref_limpa)
    return apenas_numeros if apenas_numeros else ref_limpa


def buscar_produto_por_ref(ref: str, cache: bool = True, log=None) -> dict:
    """Busca a URL e informações de um produto na Decathlon Brasil a partir da REF.

    Retorna um dicionário padronizado:
    {
        "sucesso": bool,
        "ref": str,
        "ref_encontrada": str,
        "nome": str,
        "url": str,
        "status_texto": str,
        "codigo_status": str
    }
    """
    ref_limpa = normalizar_ref(ref)
    if not ref_limpa:
        return {
            "sucesso": False,
            "ref": ref,
            "ref_encontrada": "",
            "nome": "—",
            "url": "—",
            "status_texto": "⚠ REF inválida ou vazia.",
            "codigo_status": "INVALID_REF",
        }

    if cache and ref_limpa in REF_CACHE:
        if log:
            log(f"Busca por REF {ref_limpa}: resultado obtido do cache.")
        return REF_CACHE[ref_limpa]

    search_url = f"https://www.decathlon.com.br/pesquisa?q={ref_limpa}"
    headers = dict(HEADERS)
    headers["Referer"] = "https://www.decathlon.com.br/"

    try:
        if log:
            log(f"Consultando a Decathlon para a REF {ref_limpa}...")
        resp = requests.get(search_url, headers=headers, timeout=20, allow_redirects=True)

        if resp.status_code != 200:
            res = {
                "sucesso": False,
                "ref": ref_limpa,
                "ref_encontrada": "",
                "nome": "—",
                "url": "—",
                "status_texto": f"⚠ Não foi possível consultar o site da Decathlon (HTTP {resp.status_code}).",
                "codigo_status": "BLOCK",
            }
            return res

        match = re.search(r'window\.pageData\s*=\s*(\{.*?\});\s*/\*', resp.text)
        if match:
            try:
                data = json.loads(match.group(1))
                search_res = data.get("result", {}).get("serverData", {}).get("searchResult", {})
                products = search_res.get("products", [])

                for p in products:
                    p_name = p.get("productName", "").strip()
                    p_ref = str(p.get("productReference", "")).strip()
                    p_link = p.get("link") or p.get("linkText") or ""
                    skus = [str(s.get("itemId", "")) for s in p.get("items", []) if isinstance(s, dict)]

                    match_ref = (
                        p_ref == ref_limpa
                        or ref_limpa in skus
                        or f"-{ref_limpa}-" in p_link
                        or p_link.endswith(f"-{ref_limpa}")
                        or ref_limpa in p_link
                    )

                    if match_ref:
                        if p_link and not p_link.startswith("http"):
                            canonical_url = "https://www.decathlon.com.br/" + p_link.lstrip("/")
                            if not canonical_url.endswith("/p"):
                                canonical_url += "/p"
                        else:
                            canonical_url = p_link

                        res = {
                            "sucesso": True,
                            "ref": ref_limpa,
                            "ref_encontrada": p_ref or ref_limpa,
                            "nome": p_name or "Produto Decathlon",
                            "url": canonical_url,
                            "status_texto": "✓ Produto encontrado",
                            "codigo_status": "OK",
                        }
                        if cache:
                            REF_CACHE[ref_limpa] = res
                        if log:
                            log(f"REF {ref_limpa}: encontrado '{res['nome']}' -> {res['url']}")
                        return res
            except Exception as err_json:
                if log:
                    log(f"REF {ref_limpa}: aviso ao ler dados do JSON — {err_json}")

        if "/p" in resp.url and "pesquisa" not in resp.url and "busca" not in resp.url:
            try:
                soup = BeautifulSoup(resp.text, "html.parser")
                title = soup.title.get_text(" ", strip=True) if soup.title else ""
                nome = title.replace(" | Decathlon", "").strip() or f"Produto REF {ref_limpa}"
                res = {
                    "sucesso": True,
                    "ref": ref_limpa,
                    "ref_encontrada": ref_limpa,
                    "nome": nome,
                    "url": resp.url,
                    "status_texto": "✓ Produto encontrado",
                    "codigo_status": "OK",
                }
                if cache:
                    REF_CACHE[ref_limpa] = res
                return res
            except Exception:
                pass

        res = {
            "sucesso": False,
            "ref": ref_limpa,
            "ref_encontrada": "",
            "nome": "—",
            "url": "—",
            "status_texto": "⚠ Produto não encontrado",
            "codigo_status": "NOT_FOUND",
        }
        if cache:
            REF_CACHE[ref_limpa] = res
        if log:
            log(f"REF {ref_limpa}: nenhum produto correspondente encontrado.")
        return res

    except requests.RequestException as erro_http:
        res = {
            "sucesso": False,
            "ref": ref_limpa,
            "ref_encontrada": "",
            "nome": "—",
            "url": "—",
            "status_texto": "⚠ Erro ao consultar a Decathlon. Verifique sua conexão com a internet.",
            "codigo_status": "CONNECTION_ERROR",
        }
        if log:
            log(f"REF {ref_limpa}: erro de conexão — {erro_http}")
        return res
    except Exception as erro_geral:
        res = {
            "sucesso": False,
            "ref": ref_limpa,
            "ref_encontrada": "",
            "nome": "—",
            "url": "—",
            "status_texto": f"⚠ Erro inesperado: {erro_geral}",
            "codigo_status": "ERROR",
        }
        if log:
            log(f"REF {ref_limpa}: erro inesperado — {erro_geral}")
        return res


# --------------------------------------------------------------------------
# Leitura do código-fonte
# --------------------------------------------------------------------------


def baixar_html_fotos(url: str) -> str:
    headers = dict(HEADERS)
    headers["Referer"] = "https://www.decathlon.com.br/"
    try:
        resp = requests.get(url, headers=headers, timeout=40, allow_redirects=True)
        resp.raise_for_status(); resp.encoding = resp.encoding or "utf-8"
        return resp.text
    except requests.RequestException as erro_requests:
        try:
            return get_page(url).decode("utf-8", errors="replace")
        except Exception as erro_urllib:
            raise RuntimeError(
                "Não foi possível acessar a página da Decathlon. "
                f"Requests: {erro_requests}. Tentativa alternativa: {erro_urllib}"
            ) from erro_urllib


def _achar_produtos(no):
    """Percorre o JSON-LD e devolve todo objeto @type == Product, não importa
    o nível de aninhamento (isso inclui cada cor dentro de hasVariant)."""
    if isinstance(no, dict):
        tipo = no.get("@type")
        tipos = tipo if isinstance(tipo, list) else [tipo]
        if any(isinstance(t, str) and t.lower() == "product" for t in tipos):
            yield no
        for valor in no.values():
            yield from _achar_produtos(valor)
    elif isinstance(no, list):
        for item in no:
            yield from _achar_produtos(item)


def _imagens_do_no(produto: dict):
    campo = produto.get("image")
    urls = []
    if isinstance(campo, str):
        urls.append(campo)
    elif isinstance(campo, list):
        for item in campo:
            if isinstance(item, str):
                urls.append(item)
            elif isinstance(item, dict) and isinstance(item.get("url"), str):
                urls.append(item["url"])
    return urls


def _pontuar_variante(produto: dict, referencia: str, url_pagina: str) -> int:
    """Quanto maior, mais provável que este nó Product seja a variação (cor)
    que está aberta na URL informada, e não outra cor do mesmo produto."""
    pontos = 0
    campos_texto = []
    for chave in ("sku", "productID", "mpn", "gtin13", "gtin", "@id"):
        valor = produto.get(chave)
        if isinstance(valor, str):
            campos_texto.append(valor)

    oferta = produto.get("offers")
    if isinstance(oferta, dict):
        for chave in ("sku", "mpn", "gtin13", "@id", "url"):
            valor = oferta.get(chave)
            if isinstance(valor, str):
                campos_texto.append(valor)
    elif isinstance(oferta, list):
        for item in oferta:
            if isinstance(item, dict):
                for chave in ("sku", "mpn", "gtin13", "@id", "url"):
                    valor = item.get(chave)
                    if isinstance(valor, str):
                        campos_texto.append(valor)

    url_no = produto.get("url")
    if isinstance(url_no, str):
        campos_texto.append(url_no)

    for texto in campos_texto:
        if referencia and referencia in texto:
            pontos += 10
        if url_pagina and (texto == url_pagina or url_pagina.endswith(texto) or texto.endswith(url_pagina)):
            pontos += 15

    return pontos


def imagens_do_jsonld(html: str, referencia: str, url_pagina: str, log):
    """Imagens da variação certa (a aberta na página), não das outras cores."""
    candidatos = []  # (pontuacao, imagens)

    for bruto in RE_JSONLD.findall(html):
        try:
            dados = json.loads(bruto.strip())
        except json.JSONDecodeError:
            continue
        for produto in _achar_produtos(dados):
            imagens = _imagens_do_no(produto)
            if not imagens:
                continue
            pontuacao = _pontuar_variante(produto, referencia, url_pagina)
            candidatos.append((pontuacao, imagens))

    if not candidatos:
        return []

    melhor_pontuacao = max(p for p, _ in candidatos)
    melhores = [imgs for p, imgs in candidatos if p == melhor_pontuacao]

    if melhor_pontuacao <= 0:
        log("AVISO: não consegui confirmar qual variação (cor) é a da URL —")
        log("       nenhum sku/productID bateu com a referência. Usando o")
        log("       primeiro bloco de imagens encontrado; CONFIRA o resultado.")
    elif len(melhores) > 1:
        log(f"AVISO: {len(melhores)} variações empataram na pontuação de match;")
        log("       usando a primeira. Confira se são todas a mesma cor.")

    log(f"Variação identificada com confiança {melhor_pontuacao} "
        f"(nós candidatos avaliados: {len(candidatos)}).")
    return melhores[0]


# --------------------------------------------------------------------------
# Plano B "inteligente": bloco de estado JS (__NEXT_DATA__, window.__STATE__,
# etc.). Muitas lojas VTEX/FastStore só colocam a imagem "principal" no
# JSON-LD e escondem a galeria completa (todas as 10 fotos) num desses
# blocos. A lógica de pontuação por SKU/referência é a mesma do JSON-LD,
# mas aqui ela é aplicada a QUALQUER dicionário do JSON que tenha uma lista
# de imagens, não só a nós "@type": "Product".
# --------------------------------------------------------------------------

RE_NEXT_DATA_ABERTURA = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>',
    re.IGNORECASE,
)

# outras stacks (Nuxt, apps React que fazem hidratação manual, etc.) deixam
# o estado numa variável global do tipo "window.__ALGO__ = {...};"
RE_MARCADORES_ESTADO = re.compile(
    r'window\.(?:__[a-zA-Z0-9_]+__|pageData)\s*=\s*',
    re.IGNORECASE,
)

CHAVES_LISTA_IMAGEM = ("images", "image", "pictures", "gallery", "photos")
CHAVES_URL_DENTRO_DO_ITEM = ("imageUrl", "url", "src", "imageURL", "href")

CHAVES_ID_GENERICO = (
    "sku", "skuId", "itemId", "productId", "productReferenceId",
    "referenceId", "gtin", "gtin13", "mpn", "productID", "@id", "id",
    "slug", "linkText", "detailUrl", "url",
)


def _extrair_blocos_apos_marcador(html: str, regex_marcador):
    """Para cada ocorrência de 'algumaVar = ', devolve a fatia JSON bruta que
    vem logo em seguida ({...} ou [...]), cortando no lugar certo por
    contagem de chaves/colchetes (respeitando strings e escapes, sem
    depender de um parser completo de JS)."""
    resultados = []
    for m in regex_marcador.finditer(html):
        inicio = m.end()
        while inicio < len(html) and html[inicio] in " \t\r\n":
            inicio += 1
        if inicio >= len(html) or html[inicio] not in "{[":
            continue
        abre = html[inicio]
        fecha = "}" if abre == "{" else "]"
        profundidade = 0
        dentro_string = False
        char_string = ""
        escapando = False
        fim = None
        for i in range(inicio, len(html)):
            c = html[i]
            if dentro_string:
                if escapando:
                    escapando = False
                elif c == "\\":
                    escapando = True
                elif c == char_string:
                    dentro_string = False
            else:
                if c in "\"'":
                    dentro_string = True
                    char_string = c
                elif c == abre:
                    profundidade += 1
                elif c == fecha:
                    profundidade -= 1
                    if profundidade == 0:
                        fim = i + 1
                        break
        if fim:
            resultados.append(html[inicio:fim])
    return resultados


def _blocos_json_de_estado(html: str):
    blocos = []

    for m in RE_NEXT_DATA_ABERTURA.finditer(html):
        fim_abertura = html.find(">", m.start())
        if fim_abertura == -1:
            continue
        fim_tag = html.find("</script>", fim_abertura)
        if fim_tag == -1:
            continue
        blocos.append(html[fim_abertura + 1: fim_tag])

    blocos.extend(_extrair_blocos_apos_marcador(html, RE_MARCADORES_ESTADO))
    return blocos


def _imagens_genericas_do_no(no: dict):
    for chave in CHAVES_LISTA_IMAGEM:
        valor = no.get(chave)
        if isinstance(valor, list) and valor:
            urls = []
            for item in valor:
                if isinstance(item, str):
                    urls.append(item)
                elif isinstance(item, dict):
                    for k in CHAVES_URL_DENTRO_DO_ITEM:
                        if isinstance(item.get(k), str):
                            urls.append(item[k])
                            break
            if urls:
                return urls
    return []


def _pontuar_no_generico(no: dict, referencia: str, url_pagina: str) -> int:
    pontos = 0
    textos = []
    for chave in CHAVES_ID_GENERICO:
        valor = no.get(chave)
        if isinstance(valor, str):
            textos.append(valor)
        elif isinstance(valor, int):
            textos.append(str(valor))
    for texto in textos:
        if referencia and referencia in texto:
            pontos += 10
        if url_pagina and (texto == url_pagina or url_pagina.endswith(texto) or texto.endswith(url_pagina)):
            pontos += 15
    return pontos


def _varrer_estado(no, referencia: str, url_pagina: str, candidatos: list, profundidade: int = 0):
    if profundidade > 60:  # trava de segurança contra JSON patológico
        return
    if isinstance(no, dict):
        imagens = _imagens_genericas_do_no(no)
        if imagens:
            pontuacao = _pontuar_no_generico(no, referencia, url_pagina)
            candidatos.append((pontuacao, imagens))
        for valor in no.values():
            _varrer_estado(valor, referencia, url_pagina, candidatos, profundidade + 1)
    elif isinstance(no, list):
        for item in no:
            _varrer_estado(item, referencia, url_pagina, candidatos, profundidade + 1)


def imagens_de_estado_js(html: str, referencia: str, url_pagina: str, log):
    """Plano A-2: procura a galeria completa em blocos de estado JS
    (__NEXT_DATA__, window.__STATE__ etc.), quando eles existirem. Ajuda nos
    casos em que o JSON-LD só declara a imagem "capa" do produto."""
    blocos = _blocos_json_de_estado(html)
    if not blocos:
        return []

    candidatos = []
    for bruto in blocos:
        try:
            dados = json.loads(bruto)
        except json.JSONDecodeError:
            continue
        _varrer_estado(dados, referencia, url_pagina, candidatos)

    if not candidatos:
        return []

    melhor_pontuacao = max(p for p, _ in candidatos)
    melhores = [imgs for p, imgs in candidatos if p == melhor_pontuacao]
    melhores.sort(key=len, reverse=True)  # entre empates, prioriza a galeria maior

    if melhor_pontuacao <= 0:
        log("AVISO: no estado JS da página, não consegui confirmar a variação por")
        log("       sku/id — usando o bloco de imagens mais completo encontrado;")
        log("       CONFIRA o resultado.")

    return melhores[0]


def imagens_por_varredura(html: str):
    """Plano B, sem filtro por variação: varre o HTML cru atrás de imagens
    conhecidas. Só é usado se não houver JSON-LD nenhum — pode trazer outras
    cores junto, por isso o aviso no log."""
    media = [u for u in RE_MEDIA.findall(html) if _e_foto_produto_mediadecathlon(u)]
    return RE_VTEX_URL_COMPLETA.findall(html) + media


# --------------------------------------------------------------------------
# Identificação da galeria da variação aberta
# --------------------------------------------------------------------------

def _normalizar_texto(texto: str) -> str:
    import unicodedata
    import re
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()
    texto = re.sub(r'\bpret[ao]s?\b', 'preto', texto)
    texto = re.sub(r'\bbranc[ao]s?\b', 'branco', texto)
    texto = re.sub(r'\bvermelh[ao]s?\b', 'vermelho', texto)
    texto = re.sub(r'\bamarel[ao]s?\b', 'amarelo', texto)
    return texto


def _desembrulhar_url_vtex(url: str) -> str:
    """Extrai a URL VTEX real mesmo quando está dentro de /unsafe/... ."""
    atual = (url or "").replace("&amp;", "&").strip().strip("\"' ,;)")
    atual = atual.replace("\\/", "/").replace("\u002F", "/")
    if atual.startswith("//"):
        atual = "https:" + atual

    for _ in range(4):
        decodificada = urllib.parse.unquote(atual)
        decodificada = decodificada.replace("\\/", "/")

        # Antes de procurar VTEX, detecta também uma URL MediaDecathlon
        # embutida. Isso é importante para os /b... dos ícones: se deixarmos
        # a URL /unsafe/... intacta, ela pode ser interpretada como uma imagem
        # VTEX e escapar do filtro.
        m_media = re.search(
            r"https?://contents\.mediadecathlon\.com/[^\s\"'<>]+",
            decodificada,
            re.IGNORECASE,
        )
        if m_media:
            return m_media.group(0).rstrip("),]}")

        # A URL atual pode ser, por exemplo:
        # https://xxx.vtexassets.com/unsafe/.../https://xxx.vtexassets.com/arquivos/ids/12345-...
        m = re.search(
            r"https?://[^\s\"'<>]*vtex(?:img\.com\.br|assets\.com)"
            r"[^\s\"'<>]*?/arquivos/ids/(\d+)(?:[^\s\"'<>]*)",
            decodificada,
            re.IGNORECASE,
        )
        if m:
            trecho = m.group(0).rstrip("),]}")
            # Se encontrou a URL direta embutida, usa somente ela.
            return trecho

        if decodificada == atual:
            break
        atual = decodificada
    return atual


def _id_vtex(url: str):
    """Retorna (id, host) para URLs VTEX diretas ou embrulhadas em CDN."""
    u = (url or "").replace("\\/", "/").replace("\u002F", "/")
    u = urllib.parse.unquote(u)
    m = re.search(
        r"https?://([^/\s\"'<>]*vtex(?:img\.com\.br|assets\.com))"
        r"[^\s\"'<>]*?/arquivos/ids/(\d+)",
        u,
        re.IGNORECASE,
    )
    if m:
        return m.group(2), m.group(1)
    return None, None

def _atributos_tag(tag: str):
    """Extrai atributos básicos de uma tag HTML."""
    resultado = {}
    padrao = re.compile(
        r'''([:\w-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))''',
        re.IGNORECASE,
    )
    for m in padrao.finditer(tag):
        resultado[m.group(1).lower()] = m.group(2) or m.group(3) or m.group(4) or ""
    return resultado


def _identidade_da_pagina(url_pagina: str, referencia: str):
    """Obtém palavras do produto e a variante/cor a partir do slug."""
    partes_path = [p for p in urllib.parse.urlparse(url_pagina).path.split("/") if p]
    slug = partes_path[-2] if partes_path and partes_path[-1].lower() == "p" and len(partes_path) >= 2 else (partes_path[-1] if partes_path else "")
    slug = re.sub(r"-?p$", "", slug, flags=re.IGNORECASE)
    tokens = [t for t in re.split(r"[-_]+", slug.lower()) if t]
    ref = referencia.lower()

    pos = next((i for i, t in enumerate(tokens) if ref in t), len(tokens))
    antes = tokens[:pos]

    # No padrão Decathlon "...-cor-REF-marca", a última palavra antes
    # da referência é a cor/modelo da variante aberta.
    variante = antes[-1] if antes else ""

    stop = {
        "de", "da", "do", "das", "dos", "e", "para", "com",
        "feminina", "feminino", "masculina", "masculino",
        "a", "o", "um", "uma",
    }
    base = [t for t in antes[:-1] if len(t) >= 3 and t not in stop]
    return base, variante


def _extrair_imagens_das_tags(html: str):
    """Extrai URLs de img/source, inclusive srcset e data-srcset."""
    resultados = []
    for m in re.finditer(r"<(?:img|source)\b[^>]*>", html, re.IGNORECASE):
        attrs = _atributos_tag(m.group(0))
        contexto = " ".join(
            x for x in (
                attrs.get("alt", ""),
                attrs.get("title", ""),
                attrs.get("aria-label", ""),
            ) if x
        )

        for chave in ("src", "data-src", "data-original", "data-lazy-src",
                      "srcset", "data-srcset"):
            valor = attrs.get(chave, "")
            if not valor:
                continue
            urls = re.findall(r"https?://[^\s,]+|//[^\s,]+", valor)
            for url in urls:
                resultados.append((url.strip("\"'"), contexto))
    return resultados


def _extrair_urls_imagem_do_html(html: str):
    """Extrai URLs de imagens de tags E de JSON/estado embutido na página.

    A Decathlon atual pode esconder a galeria em JSON, sem criar 10 tags
    <img> no HTML inicial. Por isso não dependemos somente de <img>.
    """
    texto = (html or "").replace("\\/", "/").replace("\u002F", "/")
    padrao = re.compile(
        r"https?://[^\s\"'<>\\]+(?:vtex(?:img\.com\.br|assets\.com)|contents\.mediadecathlon\.com)[^\s\"'<>\\]*",
        re.IGNORECASE,
    )
    encontrados = []
    vistos = set()
    for m in padrao.finditer(texto):
        url = m.group(0).rstrip("),;]}")
        chave = (m.start(), url)
        if chave in vistos:
            continue
        vistos.add(chave)
        encontrados.append((url, m.start()))
    return encontrados


def _extrair_candidatos_por_tag(html: str):
    """Retorna (url, posição, contexto) das tags img/source.

    A página atual da Decathlon expõe a galeria em várias tags <img>, mas as
    URLs aparecem dentro de um CDN /unsafe/... que embrulha a URL VTEX real.
    O alt/title dessas tags contém o nome da cor da foto, o que é uma pista
    muito mais confiável do que procurar um SKU genérico a milhares de
    caracteres de distância.
    """
    resultados = []
    for m in re.finditer(r"<(?:img|source)\b[^>]*>", html, re.IGNORECASE):
        tag = m.group(0)
        attrs = _atributos_tag(tag)
        contexto = " ".join(
            attrs.get(k, "") for k in ("alt", "title", "aria-label", "data-alt")
        )
        for chave in (
            "src", "data-src", "data-original", "data-lazy-src",
            "srcset", "data-srcset",
        ):
            valor = attrs.get(chave, "")
            if not valor:
                continue
            # srcset pode conter "url 425w, url 800w".
            urls = re.findall(r"(?:https?:)?//[^\s,]+|https?://[^\s,]+", valor)
            for u in urls:
                u = u.strip('"\'()[];,')
                if u:
                    resultados.append((u, m.start(), contexto))
    return resultados


def _nome_arquivo_vtex(url: str) -> str:
    """Nome do arquivo da URL VTEX, depois de desembrulhar /unsafe."""
    real = _desembrulhar_url_vtex(url)
    caminho = urllib.parse.urlparse(real).path
    return caminho.rstrip('/').split('/')[-1].lower()


def imagens_da_galeria_html(html: str, url_pagina: str, referencia: str, log):
    """Seleciona a galeria da variante aberta sem depender de SKU distante.

    Estratégia, em ordem:
      1. imagens cujo alt/contexto identifica explicitamente a cor da URL;
      2. agrupa essas imagens pelo prefixo do nome do arquivo VTEX;
      3. usa a sequência maior do mesmo produto/galeria;
      4. como fallback, procura URLs no HTML bruto.

    Para a página de exemplo, as 10 fotos têm nomes como
    ...run-dry--roxo-noite-roxo-noite-3g1.jpg até ...3g10.jpg e o alt também
    contém "Roxo-noite". Isso permite separar a galeria roxa das miniaturas
    de outras cores/produtos.
    """
    base, variante = _identidade_da_pagina(url_pagina, referencia)
    variante_n = _normalizar_texto(variante)
    if not variante_n:
        variante_n = variante.lower()

    candidatos = []

    # Primeiro: tags HTML, preservando o contexto (alt/title) de cada imagem.
    for url_bruta, pos, contexto_tag in _extrair_candidatos_por_tag(html):
        # Rejeita primeiro: ícones /b... e documentos /s... podem estar
        # escondidos dentro de uma URL /unsafe/... e, nesse caso, parecer VTEX.
        if _e_imagem_nao_produto(url_bruta):
            continue
        real = _desembrulhar_url_vtex(url_bruta)
        if _e_imagem_nao_produto(real):
            continue
        vid, host = _id_vtex(real)
        if not vid and "contents.mediadecathlon.com" not in real.lower():
            continue
        if not vid and not _e_foto_produto_mediadecathlon(real):
            continue

        contexto = _normalizar_texto(contexto_tag + " " + real)
        pontos = 0

        # A cor da URL pode ser "roxo", enquanto o alt diz "roxo-noite".
        if variante_n and variante_n in contexto:
            pontos += 200

        # Referência explícita perto da própria tag é excelente evidência.
        janela = html[max(0, pos - 1200):min(len(html), pos + 1200)]
        if "<script" not in janela.lower() and re.search(
            rf"(?<!\d){re.escape(referencia)}(?!\d)", janela, re.IGNORECASE
        ):
            pontos += 80

        nome = _nome_arquivo_vtex(real)
        # Uma URL VTEX com o nome da cor no arquivo é evidência adicional.
        if variante_n and variante_n in _normalizar_texto(nome):
            pontos += 120

        if pontos <= 0:
            continue

        if vid:
            chave = f"vtex:{vid}"
        else:
            chave = f"media:{urllib.parse.urlparse(real).path}"
        candidatos.append((pontos, pos, url_bruta, chave, nome))

    # Se as tags deram imagens com a cor, não misture com outros produtos.
    if candidatos:
        # Uma mesma imagem pode aparecer em src + srcset; mantém a melhor.
        melhores = {}
        for item in candidatos:
            chave = item[3]
            if chave not in melhores or item[0] > melhores[chave][0]:
                melhores[chave] = item
        candidatos = list(melhores.values())

        # Agrupa pela sequência física no HTML. A galeria principal aparece
        # como uma sequência de imagens, antes de conteúdo/recomendados.
        candidatos.sort(key=lambda x: x[1])
        grupos = []
        atual = []
        ultima = None
        for item in candidatos:
            if ultima is None or item[1] - ultima <= 25000:
                atual.append(item)
            else:
                if atual:
                    grupos.append(atual)
                atual = [item]
            ultima = item[1]
        if atual:
            grupos.append(atual)

        # Prefere grupo maior; em empate, maior soma de pontuação.
        grupo = max(grupos, key=lambda g: (len(g), sum(x[0] for x in g)))
        grupo.sort(key=lambda x: x[1])
        urls = [x[2] for x in grupo]

        log(
            f"Galeria da variação '{variante}' encontrada nas tags/HTML: "
            f"{len(urls)} imagem(ns)."
        )
        if len(urls) >= 2:
            return urls

    # Segundo: URLs no HTML/JSON sem tag <img>. Aqui usamos nome de arquivo e
    # contexto local, mas não descartamos tudo só porque o SKU interno difere
    # da referência comercial da URL.
    brutas = _extrair_urls_imagem_do_html(html)
    fallback = []
    for url_bruta, pos in brutas:
        # Mesmo filtro no fallback de HTML/JSON bruto.
        if _e_imagem_nao_produto(url_bruta):
            continue
        real = _desembrulhar_url_vtex(url_bruta)
        if _e_imagem_nao_produto(real):
            continue
        vid, host = _id_vtex(real)
        if not vid and "contents.mediadecathlon.com" not in real.lower():
            continue
        if not vid and not _e_foto_produto_mediadecathlon(real):
            continue
        nome = _normalizar_texto(_nome_arquivo_vtex(real))
        janela = _normalizar_texto(html[max(0, pos-1800):min(len(html), pos+1800)])
        pontos = 0
        if variante_n and variante_n in nome:
            pontos += 250
        if variante_n and variante_n in janela:
            pontos += 80
        if re.search(rf"(?<!\d){re.escape(referencia)}(?!\d)", janela):
            pontos += 100
        if pontos:
            chave = f"vtex:{vid}" if vid else f"media:{urllib.parse.urlparse(real).path}"
            fallback.append((pontos, pos, url_bruta, chave))

    unicos = {}
    for item in fallback:
        if item[3] not in unicos or item[0] > unicos[item[3]][0]:
            unicos[item[3]] = item
    fallback = sorted(unicos.values(), key=lambda x: x[1])

    if fallback:
        urls = [x[2] for x in fallback]
        log(
            f"Galeria da variação '{variante}' encontrada no HTML bruto: "
            f"{len(urls)} imagem(ns)."
        )
        return urls

    return []


# --------------------------------------------------------------------------
# Normalização: ID canônico (dedupe) + reescrita de tamanho
# --------------------------------------------------------------------------

def normalizar(url: str, largura: int, altura: int):
    """Devolve (chave_para_dedupe, URL no tamanho pedido)."""
    original = (url or "").replace("&amp;", "&").strip()
    # Nunca normalizar um ícone/manual como se fosse uma imagem VTEX.
    if _e_imagem_nao_produto(original):
        return None
    url = _desembrulhar_url_vtex(original)
    if _e_imagem_nao_produto(url):
        return None

    vid, host = _id_vtex(url)
    if vid and host:
        nova = f"https://{host}/arquivos/ids/{vid}-{largura}-{altura}"
        return f"vtex:{vid}", nova

    if "contents.mediadecathlon.com" in url.lower() and _e_foto_produto_mediadecathlon(url):
        partes = urllib.parse.urlparse(url)
        query = dict(urllib.parse.parse_qsl(partes.query))
        query["f"] = f"{largura}x{altura}"
        query.setdefault("format", "auto")
        nova = urllib.parse.urlunparse(
            (partes.scheme or "https", partes.netloc, partes.path, "",
             urllib.parse.urlencode(query), "")
        )
        return f"media:{partes.path}", nova

    return None


def imagens_de_pagedata(html: str, url_pagina: str, referencia: str, log):
    """Procura a galeria do SKU / variação específica dentro de window.pageData
    (padrão FastStore / Decathlon)."""
    if "window.pageData" not in html:
        return []
    blocos = _extrair_blocos_apos_marcador(html, re.compile(r"window\.pageData\s*=\s*"))
    if not blocos:
        return []
    try:
        data = json.loads(blocos[0])
    except Exception:
        return []

    res = data.get("result", {})
    server_data = res.get("serverData", {}) if isinstance(res, dict) else {}
    prod = server_data.get("product", {}) if isinstance(server_data, dict) else {}
    if not isinstance(prod, dict) or not prod:
        return []

    items = prod.get("items", [])
    if not isinstance(items, list) or not items:
        return []

    base, variante = _identidade_da_pagina(url_pagina, referencia)
    var_norm = _normalizar_texto(variante)
    ref_clean = normalizar_ref(referencia)
    prod_ref = normalizar_ref(str(prod.get("productReference", "") or ""))

    candidatos = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_name = _normalizar_texto(item.get("name", ""))
        item_ref = normalizar_ref(str(item.get("reference", "") or ""))
        name_complete = _normalizar_texto(item.get("nameComplete", ""))
        cores = [_normalizar_texto(c) for c in (item.get("Cor") or []) if isinstance(c, str)]

        imgs = []
        raw_imgs = item.get("images", [])
        if isinstance(raw_imgs, list):
            for img in raw_imgs:
                if isinstance(img, dict):
                    u = img.get("imageUrl") or img.get("url") or img.get("src")
                    if u:
                        imgs.append(u)
                elif isinstance(img, str):
                    imgs.append(img)

        if not imgs:
            continue

        pontos = 0
        if ref_clean and (ref_clean == item_ref or ref_clean in item_name or ref_clean == prod_ref):
            pontos += 100

        if var_norm:
            if var_norm in item_name or var_norm in name_complete or any(var_norm in c for c in cores):
                pontos += 300
            else:
                pontos -= 200
        else:
            pontos += 50

        candidatos.append((pontos, len(imgs), imgs))

    if candidatos:
        candidatos.sort(key=lambda x: (x[0], x[1]), reverse=True)
        if candidatos[0][0] > 0:
            if log:
                log(f"Usando galeria pageData da variação: {candidatos[0][1]} imagem(ns).")
            return candidatos[0][2]
    return []


def coletar(html: str, referencia: str, url_pagina: str, largura: int, altura: int, log):
    """
    Prioriza a galeria da própria página. JSON-LD normalmente traz apenas a
    capa; estado JS traz estruturas da variação.
    """
    brutas_pagedata = imagens_de_pagedata(html, url_pagina, referencia, log)
    brutas_galeria = imagens_da_galeria_html(
        html, url_pagina, referencia, log
    )

    brutas_estado = imagens_de_estado_js(html, referencia, url_pagina, log)
    brutas_jsonld = imagens_do_jsonld(html, referencia, url_pagina, log)

    if brutas_galeria and len(brutas_galeria) >= 2:
        brutas = brutas_galeria
        log(f"Usando a galeria HTML da variação: {len(brutas)} imagem(ns).")
    elif brutas_pagedata and len(brutas_pagedata) >= 2:
        brutas = brutas_pagedata
    elif brutas_estado and len(brutas_estado) >= 2:
        brutas = brutas_estado
        log(f"Usando o estado JS da variação: {len(brutas)} imagem(ns).")
    elif brutas_jsonld:
        brutas = brutas_jsonld
        log(f"Usando JSON-LD: {len(brutas)} imagem(ns).")
    elif brutas_galeria:
        brutas = brutas_galeria
        log(f"Usando galeria HTML: {len(brutas)} imagem(ns).")
    else:
        log(
            "AVISO: não encontrei uma galeria identificada. "
            "Caindo na varredura geral do HTML."
        )
        brutas = imagens_por_varredura(html)

    vistas, finais = set(), []
    descartadas = 0

    for bruta in brutas:
        resultado = normalizar(bruta, largura, altura)
        if resultado is None:
            continue
        chave, url = resultado
        if chave in vistas:
            descartadas += 1
            continue
        vistas.add(chave)
        finais.append(url)

    if descartadas:
        log(
            f"{descartadas} repetida(s) descartada(s) "
            f"(mesma imagem em outro tamanho)."
        )

    log("----- URLs de origem das imagens coletadas (debug) -----")
    for i, url in enumerate(finais, start=1):
        log(f"  origem [{i:02d}]: {url}")

    return finais


# --------------------------------------------------------------------------
# Download + conversão de formato
# --------------------------------------------------------------------------

EXTENSAO_POR_TIPO = {"png": ".png", "webp": ".webp", "jpeg": ".jpg", "jpg": ".jpg"}


def salvar(urls, destino: Path, referencia: str, largura: int, altura: int,
           formato_forcado: str, log):
    destino.mkdir(parents=True, exist_ok=True)
    # Limpar imagens antigas da mesma referência para não acumular
    for arq in destino.glob(f"{referencia}_*.*"):
        try:
            arq.unlink()
        except Exception:
            pass
    salvos = 0

    for indice, url in enumerate(urls, start=1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=60)
            resp.raise_for_status()
        except requests.RequestException as erro:
            log(f"[{indice}] FALHOU: {erro}")
            continue

        conteudo = resp.content
        tipo = resp.headers.get("Content-Type", "").lower()
        extensao_original = next(
            (ext for chave, ext in EXTENSAO_POR_TIPO.items() if chave in tipo), ".jpg"
        )

        extensao_final = extensao_original
        if formato_forcado != "Manter original":
            if not PILLOW:
                log(f"[{indice}] Pillow não instalado — não dá para converter, "
                    f"salvando como veio ({extensao_original}).")
            else:
                try:
                    imagem = Image.open(BytesIO(conteudo))
                    from PIL import ImageOps
                    alvo = formato_forcado.upper()
                    if alvo == "JPG":
                        alvo, extensao_final = "JPEG", ".jpg"
                        if imagem.mode in ("RGBA", "P"):
                            imagem = imagem.convert("RGBA")
                            fundo_branco = Image.new("RGB", imagem.size, (255, 255, 255))
                            fundo_branco.paste(imagem, mask=imagem)
                            imagem = fundo_branco
                        else:
                            imagem = imagem.convert("RGB")
                        imagem = ImageOps.pad(imagem, (largura, altura), color=(255, 255, 255))
                    else:
                        extensao_final = f".{formato_forcado.lower()}"
                        if imagem.mode == "P":
                            imagem = imagem.convert("RGBA")
                        cor_fundo = (255, 255, 255, 0) if imagem.mode == "RGBA" else (255, 255, 255)
                        imagem = ImageOps.pad(imagem, (largura, altura), color=cor_fundo)
                    buffer = BytesIO()
                    imagem.save(buffer, format=alvo)
                    conteudo = buffer.getvalue()
                except Exception as erro:
                    log(f"[{indice}] Arquivo ignorado, não é uma imagem válida: {erro}")
                    continue

        caminho = destino / f"{referencia}_{indice:02d}{extensao_final}"
        caminho.write_bytes(conteudo)

        if PILLOW:
            try:
                with Image.open(caminho) as img:
                    w, h = img.size
                marca = "OK" if (w, h) == (largura, altura) else "atenção: original pode ser menor"
                log(f"[{indice}] {caminho.name} — {w}x{h} ({marca})")
            except Exception:
                log(f"[{indice}] {caminho.name} — salvo (não consegui ler dimensões)")
        else:
            log(f"[{indice}] {caminho.name} — salvo")

        salvos += 1

    return salvos


def abrir_pasta(caminho: Path):
    sistema = platform.system()
    if sistema == "Windows":
        os.startfile(caminho)  # noqa: S606
    elif sistema == "Darwin":
        subprocess.Popen(["open", str(caminho)])
    else:
        subprocess.Popen(["xdg-open", str(caminho)])



# --------------------------------------------------------------------------
# ANATEL - BUSCA E CONFIRMACAO
# --------------------------------------------------------------------------

def normalizar_homologacao_anatel(value: str) -> str:
    """Normaliza número de homologação para comparação com a base ANATEL."""
    value = str(value or "").strip()
    if not value:
        return ""
    # Aceita o formato comum 12345-67-89012 e variações com espaços/pontos.
    digits = re.sub(r"[^0-9]", "", value)
    if 7 <= len(digits) <= 15:
        return digits.lstrip("0")
    m = re.search(r"(?i)n(?:ú|u)mero\s+de\s+homologa(?:ç|c)(?:a|ã)o\s*[:\-]?\s*([0-9][0-9\s.\-]{7,20}[0-9])", value)
    if m:
        digits = re.sub(r"[^0-9]", "", m.group(1))
        if 7 <= len(digits) <= 15:
            return digits.lstrip("0")
    return ""


def localizar_numero_anatel_html(html: str) -> str:
    """Tenta localizar um número de homologação no HTML, sem inventar dados."""
    if not html:
        return ""
    # Só aceita candidatos próximos de termos explícitos de homologação.
    padroes = [
        r"(?is)(?:n(?:ú|u)mero\s+de\s+homologa(?:ç|c)(?:a|ã)o|homologa(?:ç|c)(?:a|ã)o)\s*[:\-]?\s*([0-9][0-9\s.\-]{7,20}[0-9])",
        r"(?is)anatel[^0-9]{0,80}([0-9]{5}[\s.\-][0-9]{2}[\s.\-][0-9]{5})",
        r"(?is)anatel[^0-9]{0,80}(\d{12})",
    ]
    for pat in padroes:
        m = re.search(pat, html)
        if m:
            n = normalizar_homologacao_anatel(m.group(1))
            if n:
                return n
    return ""


ANATEL_CONFIG_FILE = "anatel_config.json"

# URL oficial de dados abertos da ANATEL usada pelo backend original em
# PowerShell: um ZIP contendo o CSV "Produtos_Homologados_Anatel.csv".
ANATEL_URL_OFICIAL = "https://www.anatel.gov.br/dadosabertos/paineis_de_dados/certificacao_de_produtos/produtos_certificados.zip"
ANATEL_CACHE_DIAS = 7

# Nomes de coluna aceitos (normalizados: minúsculo e sem acento) para cada
# campo que usamos. Os nomes oficiais da ANATEL vêm primeiro; o restante
# cobre variações comuns de outras exportações/fontes.
ANATEL_COLUNAS = {
    "numero": [
        "numero de homologacao", "numero homologacao", "numero",
        "num homologacao", "numero_homologacao", "homologacao", "certificado",
        "numero do certificado", "numero certificado", "numero de certificacao",
    ],
    "fabricante": [
        "nome do fabricante", "fabricante",
        "nome fabricante", "razao social do fabricante", "razao social",
    ],
    "modelo": [
        "modelo", "nome do modelo", "modelo comercial", "nome comercial",
    ],
    "pais": [
        "pais do fabricante", "pais",
        "pais de fabricacao", "pais fabricacao", "pais de origem",
    ],
}

# Cache em memória para não reler o arquivo inteiro a cada consulta.
_anatel_cache = {"caminho": None, "mtime": None, "linhas": None, "colunas": None}


def _norm_col(nome: str) -> str:
    """Normaliza nome de coluna para comparação (minúsculo, sem acento)."""
    nome = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode("ascii")
    return nome.strip().lower()


def salvar_caminho_base_anatel(caminho: str):
    """Grava o caminho da base escolhida manualmente, para lembrar da próxima vez."""
    cfg_path = Path(__file__).resolve().with_name(ANATEL_CONFIG_FILE)
    try:
        cfg_path.write_text(
            json.dumps({"caminho_base": str(caminho)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def carregar_caminho_base_anatel_salvo() -> str:
    cfg_path = Path(__file__).resolve().with_name(ANATEL_CONFIG_FILE)
    if not cfg_path.exists():
        return ""
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        return data.get("caminho_base", "") or ""
    except Exception:
        return ""


def _pasta_dados_anatel() -> Path:
    pasta = Path(__file__).resolve().with_name("dados_anatel")
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _caminho_indice_anatel() -> Path:
    return _pasta_dados_anatel() / "indice_anatel.tsv"


def _caminho_zip_anatel() -> Path:
    return _pasta_dados_anatel() / "produtos_certificados.zip"


def _pasta_extraida_anatel() -> Path:
    return _pasta_dados_anatel() / "extraido"


def idade_dias_arquivo(caminho) -> float:
    """Retorna há quantos dias o arquivo foi modificado pela última vez (-1 se não existir)."""
    try:
        mtime = Path(caminho).stat().st_mtime
        return (time.time() - mtime) / 86400
    except Exception:
        return -1


def localizar_base_anatel() -> str:
    """Localiza a base ANATEL a ser usada, nesta ordem de prioridade:
    1) caminho escolhido manualmente pelo usuário (botão 'Selecionar base');
    2) índice já preparado a partir do download oficial;
    3) um arquivo com nome sugestivo (csv/txt/xlsx/zip) na pasta do programa.
    """
    salvo = carregar_caminho_base_anatel_salvo()
    if salvo and Path(salvo).exists():
        return salvo

    indice = _caminho_indice_anatel()
    if indice.exists():
        return str(indice)

    pasta = Path(__file__).resolve().parent
    candidatos = []
    for ext in ("*.csv", "*.txt", "*.xlsx", "*.xls", "*.zip"):
        candidatos.extend(pasta.glob(ext))

    palavras_chave = ("anatel", "homologa", "certificad")
    for arq in candidatos:
        if any(p in arq.name.lower() for p in palavras_chave):
            return str(arq)
    return ""


def _detectar_delimitador(amostra: str) -> str:
    try:
        return csv.Sniffer().sniff(amostra, delimiters=[",", ";", "\t", "|"]).delimiter
    except Exception:
        contagens = {d: amostra.count(d) for d in (",", ";", "\t", "|")}
        return max(contagens, key=contagens.get)


def _mapear_colunas(cabecalho):
    """Mapeia cada campo que usamos (numero/fabricante/modelo/pais) para o
    índice da coluna correspondente no cabeçalho do arquivo."""
    normalizados = [_norm_col(c) for c in cabecalho]
    mapa = {}
    for campo, variantes in ANATEL_COLUNAS.items():
        # Primeira passagem: busca exata para evitar falsos positivos
        for idx, col in enumerate(normalizados):
            if col in variantes:
                mapa[campo] = idx
                break
        if campo in mapa: continue
        
        # Segunda passagem: busca parcial (evitando colunas de data/hora)
        for idx, col in enumerate(normalizados):
            if any(v in col for v in variantes) and "data" not in col:
                mapa[campo] = idx
                break
    return mapa


def _ler_base_csv_txt(caminho: Path):
    with open(caminho, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
        amostra = f.read(8192)
        f.seek(0)
        delim = _detectar_delimitador(amostra)
        leitor = csv.reader(f, delimiter=delim)
        try:
            cabecalho = next(leitor)
        except StopIteration:
            return [], {}
        mapa = _mapear_colunas(cabecalho)
        linhas = list(leitor)
    return linhas, mapa


def _ler_base_xlsx(caminho: Path):
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise RuntimeError(
            "Para ler a base em Excel (.xlsx) é preciso instalar a biblioteca "
            "'openpyxl' (pip install openpyxl), ou exportar a base como CSV/TXT."
        )
    wb = load_workbook(caminho, read_only=True, data_only=True)
    ws = wb.active
    linhas_iter = ws.iter_rows(values_only=True)
    try:
        cabecalho = next(linhas_iter)
    except StopIteration:
        return [], {}
    cabecalho = [c if c is not None else "" for c in cabecalho]
    mapa = _mapear_colunas(cabecalho)
    linhas = [["" if v is None else str(v) for v in linha] for linha in linhas_iter]
    return linhas, mapa


def _extrair_e_localizar_csv_do_zip(caminho_zip: Path) -> Path:
    """Extrai o ZIP da ANATEL e localiza o CSV de produtos homologados dentro dele."""
    destino = _pasta_extraida_anatel()
    if destino.exists():
        shutil.rmtree(destino, ignore_errors=True)
    destino.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(caminho_zip) as zf:
            zf.extractall(destino)
    except PermissionError as e:
        raise RuntimeError(
            "Não foi possível atualizar porque o arquivo da ANATEL está aberto "
            "em outro programa (provavelmente no Excel).\n\n"
            "Por favor, feche o arquivo CSV e tente atualizar novamente."
        )

    candidatos = list(destino.rglob("*.csv"))
    if not candidatos:
        raise RuntimeError("O arquivo ZIP da ANATEL não contém nenhum CSV.")

    for c in candidatos:
        if c.name.lower() == "produtos_homologados_anatel.csv":
            return c
    return candidatos[0]


def _baixar_zip_anatel(destino: Path, log=None):
    """Baixa o ZIP oficial de produtos certificados da ANATEL."""
    tmp = destino.with_suffix(destino.suffix + ".download")
    try:
        with requests.get(ANATEL_URL_OFICIAL, stream=True, timeout=600, headers=HEADERS) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
        tmp.replace(destino)
    except Exception as erro:
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass
        raise RuntimeError(f"Não foi possível baixar a base oficial da ANATEL: {erro}")


def _construir_indice_anatel(csv_path: Path):
    """Lê o CSV oficial da ANATEL e grava um índice normalizado (TSV) enxuto,
    com apenas os 4 campos que usamos, para buscas rápidas depois."""
    linhas, mapa = _ler_base_csv_txt(csv_path)
    faltando = [c for c in ("numero", "fabricante", "modelo", "pais") if c not in mapa]
    if faltando:
        raise RuntimeError(
            "Não encontrei no CSV oficial da ANATEL a(s) coluna(s): " + ", ".join(faltando)
        )

    destino = _caminho_indice_anatel()
    tmp = destino.with_suffix(".tmp")

    def limpo(linha, idx):
        if idx is None or idx >= len(linha):
            return ""
        return re.sub(r"[\r\n\t]+", " ", str(linha[idx]).strip())

    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write("Numero\tFabricante\tModelo\tPais\n")
        for linha in linhas:
            numero = normalizar_homologacao_anatel(limpo(linha, mapa["numero"]))
            if not numero:
                continue
            f.write(
                f"{numero}\t{limpo(linha, mapa.get('fabricante'))}\t"
                f"{limpo(linha, mapa.get('modelo'))}\t{limpo(linha, mapa.get('pais'))}\n"
            )

    tmp.replace(destino)


def garantir_base_anatel_oficial(forcar_download=False, log=None) -> Path:
    """Garante que exista um índice local pronto para busca, baixando e
    processando a base oficial da ANATEL quando necessário."""
    indice = _caminho_indice_anatel()
    zip_path = _caminho_zip_anatel()

    precisa_preparar = forcar_download or not indice.exists()
    if not precisa_preparar:
        idade = idade_dias_arquivo(indice)
        if idade >= 0 and idade > ANATEL_CACHE_DIAS and log:
            log(f"ANATEL: aviso — a base local tem {int(idade)} dia(s); "
                f"use 'Atualizar base oficial' se quiser renová-la.")

    if precisa_preparar:
        if forcar_download or not zip_path.exists():
            if log:
                log("ANATEL: baixando base oficial (produtos_certificados.zip)...")
            _baixar_zip_anatel(zip_path, log=log)
        if log:
            log("ANATEL: extraindo e indexando a base baixada...")
        csv_path = _extrair_e_localizar_csv_do_zip(zip_path)
        _construir_indice_anatel(csv_path)

    return indice


def atualizar_base_anatel_oficial(log=None) -> str:
    """Força o download/reprocessamento da base oficial e passa a usá-la."""
    caminho = garantir_base_anatel_oficial(forcar_download=True, log=log)
    salvar_caminho_base_anatel(str(caminho))
    return str(caminho)


def carregar_base_anatel(caminho: str, forcar=False):
    """Carrega (com cache por caminho+data de modificação) a base local da
    ANATEL a partir do arquivo informado. Aceita CSV/TXT, XLSX ou o ZIP
    oficial da ANATEL (é extraído automaticamente)."""
    caminho_obj = Path(caminho)
    if not caminho_obj.exists():
        raise FileNotFoundError(f"Base ANATEL não encontrada em: {caminho}")

    mtime = caminho_obj.stat().st_mtime
    if (not forcar and _anatel_cache["caminho"] == str(caminho_obj)
            and _anatel_cache["mtime"] == mtime):
        return _anatel_cache["linhas"], _anatel_cache["colunas"]

    ext = caminho_obj.suffix.lower()
    if ext == ".zip":
        csv_path = _extrair_e_localizar_csv_do_zip(caminho_obj)
        linhas, mapa = _ler_base_csv_txt(csv_path)
    elif ext in (".xlsx", ".xls"):
        linhas, mapa = _ler_base_xlsx(caminho_obj)
    else:
        linhas, mapa = _ler_base_csv_txt(caminho_obj)

    if "numero" not in mapa:
        raise RuntimeError(
            "Não encontrei uma coluna de número de homologação na base. "
            "Verifique se a primeira linha do arquivo é um cabeçalho com um "
            "nome reconhecível (ex.: 'Número de Homologação')."
        )

    _anatel_cache.update({
        "caminho": str(caminho_obj), "mtime": mtime,
        "linhas": linhas, "colunas": mapa,
    })
    return linhas, mapa


def consultar_anatel(numero: str, log=None):
    """Busca o número de homologação na base local da ANATEL. Se nenhuma
    base local existir ainda, baixa automaticamente a base oficial."""
    numero = normalizar_homologacao_anatel(numero)
    if not numero:
        raise ValueError("Informe um número de homologação ANATEL válido.")

    caminho = localizar_base_anatel()
    if not caminho:
        if log:
            log("ANATEL: nenhuma base local encontrada; baixando a base oficial...")
        try:
            caminho = str(garantir_base_anatel_oficial(forcar_download=False, log=log))
        except Exception as erro:
            raise FileNotFoundError(
                "Não encontrei uma base local da ANATEL e não consegui baixar a base "
                f"oficial automaticamente ({erro}). Verifique sua conexão com a internet, "
                "coloque um arquivo (CSV, TXT, XLSX ou o ZIP oficial) na pasta do programa, "
                "ou use 'Selecionar base' na aba ANATEL."
            )

    if log:
        log(f"ANATEL: carregando base local ({Path(caminho).name})...")
    inicio_carga = time.time()
    linhas, mapa = carregar_base_anatel(caminho)
    tempo_download = time.time() - inicio_carga

    if log:
        log(f"ANATEL: buscando homologação {numero} em {len(linhas)} registro(s)...")
    inicio_busca = time.time()

    idx_numero = mapa["numero"]
    idx_fab = mapa.get("fabricante")
    idx_mod = mapa.get("modelo")
    idx_pais = mapa.get("pais")

    def pega(linha, idx):
        if idx is None or idx >= len(linha):
            return ""
        return str(linha[idx]).strip()

    registros = []
    for linha in linhas:
        if idx_numero >= len(linha):
            continue
        if normalizar_homologacao_anatel(str(linha[idx_numero])) == numero:
            registros.append({
                "Numero": pega(linha, idx_numero),
                "Fabricante": pega(linha, idx_fab),
                "Modelo": pega(linha, idx_mod),
                "Pais": pega(linha, idx_pais),
            })

    tempo_busca = time.time() - inicio_busca

    return {
        "numero": numero,
        "encontrado": bool(registros),
        "registros": registros,
        "tempo_busca": f"{tempo_busca:.2f}s",
        "tempo_download": f"{tempo_download:.2f}s",
        "base_usada": str(caminho),
    }


# --------------------------------------------------------------------------
# Interface
# --------------------------------------------------------------------------

def extract_decathlon_exact(soup, raw_html, tech_marker, formato="PRECODE", referencia=""):
    """Extrator dedicado ao padrão aprovado da Decathlon.

    Mantém a sequência do conteúdo técnico, elimina duplicatas e bloqueia
    conteúdo de avaliações/clientes sem alterar o texto legítimo do produto.
    """
    about = find_product_description(soup, None, tech_marker, None, raw_html)

    char_marker = best_marker(soup, CHAR_ALIASES)
    characteristics = extract_characteristics(
        soup, char_marker, tech_marker, None
    ) if char_marker else []

    blocks = iter_blocks_after(tech_marker, CHAR_ALIASES | STOP_WORDS)
    technical = group_technical(blocks)

    # Limpeza específica de avaliações:
    # remove marcadores inequívocos e sequências de nomes soltos de clientes
    # que aparecem entre o fim da ficha técnica e "Características".
    review_terms = (
        "avaliação", "avaliações", "avaliacao", "avaliacoes",
        "comentário de cliente", "comentários de clientes",
        "comentario de cliente", "comentarios de clientes",
        "review", "reviews", "customer review", "customer reviews",
        "nota dos clientes", "opinião dos clientes", "opiniao dos clientes",
        "classificação dos clientes", "classificacao dos clientes",
        "pergunta de cliente", "perguntas de clientes",
    )
    standalone_person = re.compile(
        r"^[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý'’.-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý'’.-]*){0,1}$"
    )

    # Na Decathlon, os nomes de avaliadores costumam aparecer depois do último
    # bloco técnico (ex.: "Conselhos de Manutenção") e antes de "Características".
    # Só removemos sequências de pelo menos dois nomes consecutivos nessa região,
    # preservando títulos técnicos de uma palavra como "Armazenamento".
    maintenance_idx = None
    for idx, item in enumerate(technical):
        if norm(item) in {
            "conselhos de manutenção",
            "conselhos de manutenção do produto",
        }:
            maintenance_idx = idx
            break

    review_name_indices = set()
    if maintenance_idx is not None:
        run = []
        for idx in range(maintenance_idx + 1, len(technical)):
            item = technical[idx].strip()
            n = norm(item)
            if not item:
                continue
            if any(term in n for term in review_terms):
                review_name_indices.add(idx)
                run = []
                continue
            if (
                len(item) <= 60
                and len(item.split()) <= 2
                and standalone_person.fullmatch(item)
                and not re.search(r"\d", item)
            ):
                run.append(idx)
                continue

            if len(run) >= 2:
                review_name_indices.update(run)
            run = []

        if len(run) >= 2:
            review_name_indices.update(run)

    clean_tech = []
    seen = set()
    guarantee = []

    i = 0
    while i < len(technical):
        item = technical[i].strip()
        n = norm(item)

        if i in review_name_indices:
            i += 1
            continue

        if not item:
            i += 1
            continue

        if any(term in n for term in review_terms):
            i += 1
            continue

        if re.search(r"\b\d(?:[.,]\d)?\s*(?:/\s*5|de\s*5|estrelas?)\b", n, re.I):
            i += 1
            continue

        if n == "garantia":
            if i + 1 < len(technical):
                garantia_item = technical[i + 1].strip()
                if garantia_item and i + 1 not in review_name_indices:
                    guarantee.append(garantia_item)
                i += 2
            else:
                i += 1
            continue

        k = norm(item)
        if k not in seen:
            clean_tech.append(item)
            seen.add(k)
        i += 1

    # Última barreira contra avaliações: elimina sequências de nomes próprios
    # soltos. Títulos técnicos de uma palavra ficam protegidos.
    protected_tech_titles = {
        "composição", "armazenamento", "restrição de uso",
        "conselhos de manutenção", "conselhos de manutenção do produto",
        "garantia"
    }
    filtered = []
    i = 0
    while i < len(clean_tech):
        item = clean_tech[i].strip()
        ni = norm(item)
        if ni in protected_tech_titles or len(item.split()) > 3 or len(item) > 60 or re.search(r"\d", item):
            filtered.append(item)
            i += 1
            continue
        if re.fullmatch(r"[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý'’.-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý'’.-]*){0,2}", item):
            j = i
            while j < len(clean_tech):
                candidate = clean_tech[j].strip()
                nc = norm(candidate)
                if (
                    nc in protected_tech_titles
                    or len(candidate.split()) > 3
                    or len(candidate) > 60
                    or re.search(r"\d", candidate)
                    or not re.fullmatch(r"[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý'’.-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý'’.-]*){0,2}", candidate)
                ):
                    break
                j += 1
            if j - i >= 2:
                i = j
                continue
        filtered.append(item)
        i += 1
    clean_tech = filtered

    # Fallback da garantia somente quando ela não foi encontrada no bloco técnico.
    if not guarantee:
        gar_marker = best_marker(soup, GAR_ALIASES)
        if gar_marker:
            gb = iter_blocks_after(gar_marker, STOP_WORDS, limit=5)
            for _, txt in gb:
                n = norm(txt)
                if n != "garantia" and not any(term in n for term in review_terms):
                    guarantee.append(clean_text(txt, True))
                    break

    # Características: uma por linha, sem linha em branco entre elas.
    clean_chars = []
    seen_chars = set()
    for item in characteristics:
        item = strip_review_content(item)
        if is_review_only_text(item):
            continue
        item = clean_text(item, True)
        if not item:
            continue
        if ":" in item:
            a, b = item.split(":", 1)
            item = clean_char(a, b)
        elif "," in item:
            a, b = item.split(",", 1)
            item = clean_char(a, b)
        k = norm(item)
        if k not in seen_chars:
            clean_chars.append(item)
            seen_chars.add(k)

    # Saída final no padrão de cadastro (Prompt Master): Título, Descrição
    # Comercial, Características, Dimensões, Garantia, Recomendações de
    # Conservação e Observações (PRECODE), ou o equivalente CASAS BAHIA.
    if not guarantee:
        guarantee = ["Garantia de 24 meses (Somente para defeitos de fabrica)."]
    nome = extrair_nome_produto(soup, referencia)
    return montar_cadastro(formato, nome, dedupe(about), clean_tech, clean_chars, guarantee)


def extract_from_html(html, url, formato="PRECODE"):
    raw=BeautifulSoup(html,"html.parser")
    # Primeiro tenta o bloco corrido antes de remover scripts, pois algumas páginas
    # deixam os dados do produto em HTML simples.
    soup=visible_soup(html)
    sections={s:[] for s in SECTION_ORDER}
    referencia = referencia_da_url(url) if url else ""

    # A Decathlon possui uma estrutura técnica própria. Quando ela está presente,
    # usa o parser dedicado e não o pipeline genérico, evitando duplicações e
    # perdas de conteúdo.
    tech_marker = best_marker(soup, TECH_ALIASES)
    if tech_marker:
        return extract_decathlon_exact(soup, html, tech_marker, formato, referencia)

    # 1) Descrição principal.
    char_marker=best_marker(soup,CHAR_ALIASES)
    tech_marker=best_marker(soup,TECH_ALIASES)
    gar_marker=best_marker(soup,GAR_ALIASES)
    sections["Sobre o produto"].extend(find_product_description(soup,char_marker,tech_marker,gar_marker,html))

    # 2) Para a Decathlon, a seção oficial que alimenta o cadastro é
    # "Informações técnicas". As cards de "Características" do topo são
    # benefícios resumidos e não devem ser misturadas à ficha técnica.

    # 3) Informações técnicas.
    if tech_marker:
        # A página da Decathlon coloca Garantia, Armazenamento, Restrição de Uso
        # e Conselhos de Manutenção dentro do mesmo bloco de informações técnicas.
        # Portanto não paramos em "Garantia" aqui; ela será reposicionada no final
        # somente na etapa de formatação do cadastro.
        blocks=iter_blocks_after(tech_marker, CHAR_ALIASES | STOP_WORDS)
        sections["Informações técnicas"].extend(group_technical(blocks))

    # 4) Garantia: pega texto logo depois do marcador até a próxima área comercial.
    if gar_marker and not tech_marker:
        # Para páginas sem uma ficha técnica estruturada, usa o marcador de
        # garantia como fallback. Quando existe a ficha técnica, a garantia é
        # extraída da própria sequência técnica para não engolir Armazenamento,
        # Restrição de Uso e Conselhos de Manutenção.
        blocks=iter_blocks_after(gar_marker, STOP_WORDS, limit=40)
        for _,txt in blocks:
            n=norm(txt)
            if n=="garantia": continue
            sections["Garantia"].append(clean_text(txt,True))
            if len(sections["Garantia"])>=3: break

    # 5) Fallback para páginas em formato de campos corridos.
    fields=extract_inline_blob(soup)
    if fields and not tech_marker:
        add_inline(sections,fields)

    # 5.5) Se a página não informar nenhuma garantia, usar a garantia padrão aprovada.
    # A garantia padrão é adicionada somente quando não existe garantia oficial capturada.
    if not sections["Garantia"]:
        sections["Garantia"].append("Garantia de 24 meses (Somente para defeitos de fabrica).")

    # 6) Fallback para descrição meta/OG quando não achou o texto principal.
    if not sections["Sobre o produto"]:
        for attrs in [{"name":"description"},{"property":"og:description"}]:
            m=soup.find("meta",attrs=attrs)
            if m and m.get("content"):
                sections["Sobre o produto"].append(clean_text(m["content"],True)); break

    # 7) Algumas páginas antigas usam "Descrição" como título explícito.
    if not sections["Sobre o produto"]:
        desc=best_marker(soup,{"descrição","descricao","sobre o produto"})
        if desc:
            blocks=iter_blocks_after(desc,CHAR_ALIASES|TECH_ALIASES|GAR_ALIASES|STOP_WORDS,limit=30)
            sections["Sobre o produto"].extend(clean_text(t,True) for _,t in blocks if not is_commercial_text(t) and len(t.strip()) >= 25)

    for s in SECTION_ORDER:
        sections[s]=[strip_review_content(x) for x in sections[s]]
        sections[s]=[strip_style_review_noise(x) for x in sections[s]]
        sections[s]=[strip_style_suggestion(x) for x in sections[s]]
        sections[s]=[x for x in sections[s] if not is_commercial_text(x)]
        sections[s]=[x for x in sections[s] if not is_review_only_text(x)]
        sections[s]=[x for x in sections[s] if x.strip()]
        sections[s]=dedupe(sections[s])

    # Remove também duplicatas que foram capturadas por caminhos diferentes
    # da página, como o bloco técnico e o fallback de campos corridos.
    sections = dedupe_sections(sections)

    # Remove nomes soltos que pertencem a sugestões de outros produtos.
    sections = remove_standalone_suggestion_names(sections)

    # Segurança final: alguns nomes de modelos sugeridos chegam em um único
    # bloco separado por linhas. Limpa novamente somente linhas isoladas.
    protected_titles = {
        "composição", "armazenamento", "restrição de uso", "conselhos de manutenção",
        "conselhos de manutenção do produto", "garantia", "teste de qualidade"
    }
    for s in ("Sobre o produto", "Informações técnicas"):
        cleaned_items = []
        for x in sections[s]:
            lines = []
            for line in x.splitlines():
                if norm(line) in protected_titles:
                    lines.append(line)
                    continue
                if re.fullmatch(r"[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý'’.-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý'’.-]*){0,2}", line.strip()):
                    continue
                lines.append(line)
            x = "\n".join(lines).strip()
            if x:
                cleaned_items.append(x)
        sections[s] = cleaned_items

    # Remove títulos capturados como conteúdo.
    for s,aliases in [("Características",CHAR_ALIASES),("Informações técnicas",TECH_ALIASES),("Garantia",GAR_ALIASES)]:
        if s == "Informações técnicas":
            sections[s] = [x for x in sections[s] if norm(x) not in TECH_ALIASES]
        else:
            sections[s]=[x for x in sections[s] if norm(x) not in aliases]

    # A Decathlon pode entregar "Garantia" no meio do bloco técnico. Retira
    # somente o título e o valor da garantia do bloco técnico para que o cadastro
    # mantenha Garantia no final, sem perder o conteúdo que vem depois dela.
    tech_clean=[]
    guarantee_found=[]
    if tech_marker:
        sections["Garantia"] = []
    i=0
    tech_items=sections.get("Informações técnicas", [])
    while i < len(tech_items):
        item=tech_items[i]
        if norm(item) == "garantia":
            if i + 1 < len(tech_items):
                guarantee_found.append(tech_items[i+1])
                i += 2
            else:
                i += 1
            continue
        tech_clean.append(item)
        i += 1
    sections["Informações técnicas"] = tech_clean
    if guarantee_found:
        sections["Garantia"] = guarantee_found

    if not any(sections.values()):
        raise RuntimeError("Não foi possível localizar o conteúdo do produto nesta página.")

    # Saída final no padrão de cadastro (Prompt Master).
    chars=[]
    for x in sections["Características"]:
        if ":" in x:
            a,b=x.split(":",1); x=clean_char(a,b)
        elif "," in x:
            a,b=x.split(",",1); x=clean_char(a,b)
        else:
            x=clean_text(x,True)
        chars.append(x)
    chars = dedupe(chars)

    garantia_itens = sections["Garantia"] if sections["Garantia"] else ["Garantia de 24 meses (Somente para defeitos de fabrica)."]
    nome = extrair_nome_produto(soup, referencia)
    return montar_cadastro(
        formato, nome,
        sections["Sobre o produto"],
        sections["Informações técnicas"],
        chars,
        garantia_itens,
    )




def extract(url):
    """Compatibilidade com a versão original do gerador de descrição."""
    return extract_from_html(get_page(url), url)




# ============================================================
# IA PARA APOIO AO CADASTRO
# ============================================================

IA_CONFIG_PATH = Path.home() / ".extrator_decathlon_ia.json"
IA_DEFAULT_ENDPOINT = "https://api.openai.com/v1/responses"
IA_DEFAULT_MODEL = "gpt-5.6-luna"

PROMPT_DESCRICAO_CURTA_LIVELO = """Você é responsável por criar a descrição curta de um produto para cadastro na Livelo.

Receba uma DESCRIÇÃO COMPLETA que já foi coletada e revisada. Crie uma versão resumida com NO MÁXIMO 2500 CARACTERES, contando espaços e quebras de linha.

REGRAS OBRIGATÓRIAS:
1. Use exclusivamente informações presentes na descrição completa. Nunca invente, complete ou suponha informações.
2. Preserve as informações mais importantes para o cliente: finalidade e uso do produto, principais benefícios comprovados, tecnologias, materiais, características e especificações relevantes.
3. Remova repetições, introduções excessivas, frases comerciais secundárias e detalhes menos importantes quando necessário para caber no limite.
4. Não altere números, medidas, quantidades, nomes de tecnologias, materiais, modelos ou outras especificações técnicas.
5. Não crie informações novas.
6. Mantenha o texto claro, objetivo e natural em português do Brasil.
7. Não use marcadores, numeração, Markdown ou comentários sobre o resumo.
8. Retorne somente a descrição curta final.
9. O resultado DEVE ter no máximo 2500 caracteres.
10. Se necessário, reduza ainda mais o texto para garantir que o limite de 2500 caracteres seja respeitado.
"""

IA_PRESETS = {
    "Template Decathlon - Estrutura Automática": """INSTRUÇÃO PERMANENTE

Sempre que eu enviar um conteúdo de produto, você deverá interpretar automaticamente os blocos fornecidos e reorganizar em formato final de descrição, seguindo exatamente a estrutura abaixo, sem adicionar ou remover seções.

REGRAS OBRIGATÓRIAS

Não inventar informações que não estejam presentes no texto enviado.
Corrigir ortografia e melhorar a redação mantendo o significado original.
Organizar o conteúdo exatamente na ordem definida neste template.
Remover repetições e informações redundantes.
Manter nomes de tecnologias, materiais e funcionalidades.
Garantir que "Características do Produto" sempre venha antes de "Garantia do Fornecedor".
Preserve a garantia específica informada na fonte. Se não houver garantia específica, use exatamente: Garantia de 24 meses (Somente para defeitos de fabrica
Remover automaticamente caracteres especiais de formatação, como: •, -, *, bullets, símbolos e marcadores de lista, mantendo apenas o texto puro estruturado.
Garantir que listas sejam retornadas somente com quebra de linha simples, sem qualquer tipo de marcador visual ou numeração.
Retornar somente o conteúdo estruturado final.

ORDEM OBRIGATÓRIA (DECATHLON)

1. Sobre o Produto
2. Informações Técnicas
3. Características do Produto
4. Garantia do Fornecedor

SOBRE O PRODUTO

Criar um texto comercial unificado com base nos parágrafos iniciais enviados, destacando benefícios, uso, conforto, tecnologia e diferenciais do produto.

INFORMAÇÕES TÉCNICAS

Organizar todas as informações técnicas presentes no texto (materiais, tecnologia, composição, design, desempenho e construção).

Não adicionar nenhuma informação que não esteja explícita no conteúdo enviado.

CARACTERÍSTICAS DO PRODUTO

Listar todas as características funcionais extraídas do conteúdo, uma por linha, SEM marcadores, SEM símbolos e SEM numeração.

Exemplo de formato correto:

Respirabilidade
Leveza
Conforto
Liberdade de Movimentos
Evacuação de Umidade

GARANTIA DO FORNECEDOR

Garantia de 24 meses (Somente para defeitos de fabrica

ESTRUTURA FINAL OBRIGATÓRIA

Sobre o Produto

[Texto gerado a partir do conteúdo inicial]

Informações Técnicas

Informação 1
Informação 2
Informação 3

Características do Produto

Característica 1
Característica 2
Característica 3

Garantia do Fornecedor

24 Meses

REGRA FINAL

Sempre que um conteúdo for colado, independentemente da ordem em que os blocos forem enviados, a IA deverá reorganizar automaticamente na ordem: Sobre o Produto → Informações Técnicas → Características do Produto → Garantia do Fornecedor, removendo qualquer marcador, símbolo ou formatação especial das listas.

REGRA DE CLASSIFICAÇÃO ENTRE INFORMAÇÕES TÉCNICAS E CARACTERÍSTICAS DO PRODUTO

Na página de origem, tudo costuma vir junto sob um único título "Características", misturando dois tipos de conteúdo diferentes. Você deve separar esse conteúdo assim:

Vai para Informações Técnicas: qualquer parágrafo explicativo mais longo, incluindo blocos com subtítulo próprio (como "Composição", perguntas do tipo "Por que...", "O que...", "Como...", "Quais são...", depoimentos de gerente de produto, guia de escolha de tamanho). Preserve o subtítulo de cada bloco como uma linha antes do parágrafo correspondente.

Vai para Características do Produto: somente a lista curta final, no formato Nome do item: descrição breve em uma frase, uma por linha (o tipo de lista que normalmente aparece por último, logo antes da garantia).

Ignore textos soltos sem relação com o produto que não se encaixem em nenhuma seção (ex.: nomes de pessoas isolados, fragmentos de comentário).

EXEMPLO COMPLETO

Conteúdo de origem (bruto, como vem do site):

Decathlon | Kimono Adulto de Judô 100 Outshock Branco

Especialmente projetado para sparring, é a sua chance de descobrir o judô, aprender sequências de postura, quedas e arremessos. Este kimono leve e resistente para adultos o manterá em movimento. O cinto é vendido separadamente.

Trocas e devoluções grátis em até 45 dias

Características

Composição
Tecido principal: 35 por cento Algodão65 por cento Polietileno Tereftalato (PET).
Por que esse kimono é resistente
A gramatura de um tecido é sua espessura expressa em gramas por metro quadrado. Quando se trata de judô, é melhor escolher um kimono com um tecido resistente, para que ele permaneça no lugar durante o treinamento e depois de lavado. Escolhemos um tecido feito com 65 por cento de poliéster e 35 por cento de algodão com uma gramatura de 350 g e m.
Resistência: Com um peso de 350 g e m, a jaqueta e a calça são resistentes à impressão.
Liberdade de movimentos: Em pé ou no chão, você pode se movimentar livremente.
Aderência: Um kimono fácil de segurar para uma série de fixações de judô.

Garantia
24 Meses contra defeitos de fabricação.

Resultado esperado (formatado):

Sobre o Produto:
Decathlon | Kimono Adulto de Judô 100 Outshock Branco

Especialmente projetado para sparring, é a sua chance de descobrir o judô, aprender sequências de postura, quedas e arremessos. Este kimono leve e resistente para adultos o manterá em movimento. O cinto é vendido separadamente.

Trocas e devoluções grátis em até 45 dias

Informações Técnicas:
Composição

Tecido principal: 35 por cento Algodão65 por cento Polietileno Tereftalato (PET).

Por que esse kimono é resistente

A gramatura de um tecido é sua espessura expressa em gramas por metro quadrado. Quando se trata de judô, é melhor escolher um kimono com um tecido resistente, para que ele permaneça no lugar durante o treinamento e depois de lavado. Escolhemos um tecido feito com 65 por cento de poliéster e 35 por cento de algodão com uma gramatura de 350 g e m.

Características do Produto:
Resistência: Com um peso de 350 g e m, a jaqueta e a calça são resistentes à impressão.
Liberdade de movimentos: Em pé ou no chão, você pode se movimentar livremente.
Aderência: Um kimono fácil de segurar para uma série de fixações de judô.

Garantia do Fornecedor:
24 Meses""",
}


# Nome amigável exibido no seletor.
if "Formatar cadastro Decathlon" in IA_PRESETS:
    IA_PRESETS["Padrão Decathlon"] = IA_PRESETS["Formatar cadastro Decathlon"]

PROMPT_CORRECAO_ERROS = """Revise a descrição de produto fornecida abaixo como um segundo filtro de qualidade.

Corrija somente erros de ortografia, gramática, concordância, acentuação, pontuação, repetição desnecessária, formatação e organização que estejam em desacordo com o padrão Decathlon.

Não invente informações. Não acrescente benefícios, características, materiais, medidas, tecnologias, códigos, garantia ou qualquer outro dado que não esteja na descrição recebida.

Preserve integralmente números, medidas, quantidades, códigos, modelos, materiais, tecnologias e demais dados técnicos.

Mantenha exatamente as quatro seções e a ordem:
Sobre o Produto:
Informações Técnicas:
Características do Produto:
Garantia do Fornecedor:

Em Informações Técnicas, mantenha uma especificação independente por parágrafo, com exatamente uma linha em branco entre elas.
Em Características do Produto, mantenha uma característica por linha, sem linha em branco entre elas e sem marcadores ou numeração.

Não transforme uma informação existente em outra informação. Não complete lacunas com conhecimento externo.

Retorne somente a descrição corrigida."""

IA_SYSTEM = """Você é um assistente de cadastro de produtos integrado a um extrator de e-commerce.
Sua prioridade é fidelidade aos dados fornecidos.
REGRAS OBRIGATÓRIAS:
1. Nunca invente informações.
2. Nunca complete lacunas com conhecimento externo.
3. Não transforme suposições em fatos.
4. Preserve números, medidas, unidades, códigos, modelos, materiais, tecnologias e garantia.
5. Remova nomes aleatórios, textos de navegação, avaliações, comentários e conteúdo que não pertença ao produto.
6. Escreva em português do Brasil.
7. Quando um dado não estiver na fonte, simplesmente não o inclua.
8. Siga o prompt específico da tarefa abaixo.
"""

def carregar_config_ia():
    try:
        if IA_CONFIG_PATH.exists():
            data = json.loads(IA_CONFIG_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}

def salvar_config_ia(config):
    try:
        IA_CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def _extrair_texto_responses_api(data):
    if isinstance(data, dict) and isinstance(data.get("output_text"), str):
        return data["output_text"].strip()
    partes = []
    for item in (data.get("output") or []):
        for content in (item.get("content") or []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                partes.append(content["text"])
    if partes:
        return "\n".join(partes).strip()
    return ""

def chamar_ia(prompt_usuario, api_key, model, endpoint=IA_DEFAULT_ENDPOINT, log=None):
    if not api_key.strip():
        raise RuntimeError("Informe a chave da API na área de IA.")
    if not endpoint.strip():
        endpoint = IA_DEFAULT_ENDPOINT
    payload = {
        "model": model.strip() or IA_DEFAULT_MODEL,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": IA_SYSTEM}]},
            {"role": "user", "content": [{"type": "input_text", "text": prompt_usuario}]}
        ]
    }
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json"
    }
    if log:
        log(f"IA: enviando solicitação para {endpoint} usando {payload['model']}...")
    resposta = requests.post(endpoint, headers=headers, json=payload, timeout=180)
    if resposta.status_code >= 400:
        try:
            detalhe = resposta.json()
        except Exception:
            detalhe = resposta.text[:1000]
        raise RuntimeError(f"API retornou HTTP {resposta.status_code}: {detalhe}")
    texto = _extrair_texto_responses_api(resposta.json())
    if not texto:
        raise RuntimeError("A API respondeu, mas não foi encontrado texto no resultado.")
    return texto


# --------------------------------------------------------------------------
# TRADUÇÃO AUTOMÁTICA DA DESCRIÇÃO (quando o site traz o texto em outro idioma)
# --------------------------------------------------------------------------

# Amostra pequena de palavras comuns, usada só para decidir, sem gastar uma
# chamada de IA, se o texto já parece estar em português. Não é uma
# detecção de idioma "de verdade" — é apenas um atalho: quando o sinal é
# fraco ou ambíguo, a decisão final fica por conta da IA (o prompt de
# tradução já devolve o texto sem alterações se ele já estiver em
# português).
_PALAVRAS_PT_COMUNS = {
    "de", "da", "do", "das", "dos", "para", "com", "não", "que", "uma", "um",
    "os", "as", "em", "por", "sua", "seu", "mais", "produto", "é", "e",
    "esta", "este", "sem", "muito", "também", "você",
}
_PALAVRAS_NAO_PT_COMUNS = {
    # francês
    "le", "la", "les", "des", "avec", "pour", "vous", "produit", "est", "un", "une",
    # inglês
    "the", "and", "with", "product", "for", "this", "your", "is", "are",
    # espanhol
    "el", "los", "las", "con", "para", "producto", "es", "una",
    # amostra pequena de italiano/alemão/holandês, só para reduzir falso-negativo
    "il", "und", "der", "die", "das", "een", "van", "het",
}


def _parece_portugues(texto: str) -> bool:
    """Heurística rápida e sem custo: só serve para decidir se vale a pena
    chamar a IA para traduzir. Em caso de dúvida, prefere chamar a IA
    (retorna False) a arriscar deixar uma descrição em outro idioma."""
    if not texto or not texto.strip():
        return True
    palavras = re.findall(r"[a-zà-ÿ]+", texto.lower())[:600]
    if not palavras:
        return True
    pt = sum(1 for p in palavras if p in _PALAVRAS_PT_COMUNS)
    outros = sum(1 for p in palavras if p in _PALAVRAS_NAO_PT_COMUNS)
    if pt == 0 and outros == 0:
        return True
    return pt >= outros


PROMPT_TRADUCAO_DESCRICAO = """Você é um tradutor técnico especializado em descrições de produtos de e-commerce.

Verifique o idioma do TEXTO abaixo.
- Se já estiver em português (do Brasil ou de Portugal), devolva o texto EXATAMENTE como está, sem nenhuma alteração — nem de conteúdo, nem de formatação, nem de pontuação.
- Se estiver em qualquer outro idioma, traduza integralmente para português do Brasil.

Regras para quando houver tradução:
- Preserve a estrutura original: títulos de seção, quebras de linha, marcadores e parágrafos continuam no mesmo lugar.
- Preserve números, medidas, unidades, códigos de modelo, siglas técnicas e nomes de marca sem alterar seu valor.
- Use um português natural e comercial, sem inventar informação que não exista no texto original.
- Não adicione comentários, explicações, aspas ou notas sobre a tradução.
- Retorne SOMENTE o texto final (traduzido ou original, conforme o caso), nada mais.

TEXTO:
{texto}
"""


def traduzir_para_portugues(texto: str, api_key: str, model: str, endpoint: str, log=None) -> str:
    """Detecta (de forma barata) se o texto não está em português e, se a
    chave de IA estiver configurada, traduz para português do Brasil usando
    a mesma IA já usada no resto do programa. Sem chave de IA, o texto é
    devolvido sem alteração (não há como traduzir aqui sem uma IA)."""
    if not texto or not texto.strip():
        return texto

    if _parece_portugues(texto):
        return texto

    if not (api_key or "").strip():
        if log:
            log("TRADUÇÃO: o texto parece estar em outro idioma, mas nenhuma chave de IA "
                "está configurada; a descrição será mantida no idioma original.")
        return texto

    if log:
        log("TRADUÇÃO: o texto não parece estar em português; traduzindo com a IA...")

    try:
        resultado = chamar_ia(
            PROMPT_TRADUCAO_DESCRICAO.format(texto=texto), api_key, model, endpoint, log
        ).strip()
    except Exception as erro:
        if log:
            log(f"TRADUÇÃO: erro ao traduzir (mantendo texto original) — {erro}")
        return texto

    if not resultado:
        if log:
            log("TRADUÇÃO: a IA retornou vazio; mantendo o texto original.")
        return texto

    if log:
        log("TRADUÇÃO: concluída.")
    return resultado


PROMPT_AUDITOR_DESCRICAO = """Você é a última IA auditora de uma descrição de produto da Decathlon.

Você receberá:
1. A FONTE ORIGINAL extraída do site da Decathlon.
2. A DESCRIÇÃO CANDIDATA produzida pela primeira IA.

Sua tarefa é comparar as duas e devolver uma versão corrigida da DESCRIÇÃO CANDIDATA.

REGRAS ABSOLUTAS
- Use somente informações que tenham suporte na FONTE ORIGINAL.
- Nunca invente, complete, suponha ou deduza características.
- Se a descrição candidata afirmar algo que não esteja suportado pela fonte, remova ou corrija a afirmação.
- Preserve números, medidas, quantidades, códigos, modelos, materiais e tecnologias presentes na fonte.
- Não altere valores técnicos para deixar o texto mais bonito.
- Corrija ortografia, gramática, concordância, acentuação, pontuação e redação.
- Remova repetições e textos de navegação, avaliações ou comentários que tenham escapado para a descrição.
- Mantenha exatamente estas quatro seções e nesta ordem:
  Sobre o Produto:
  Informações Técnicas:
  Características do Produto:
  Garantia do Fornecedor:
- Em Informações Técnicas, cada especificação independente deve ficar em um bloco separado por uma única linha em branco.
- Em Características do Produto, use uma característica por linha, sem linhas em branco, marcadores ou numeração.
- A garantia deve permanecer no final. Se a fonte não trouxer garantia específica, use exatamente:
  Garantia de 24 meses (Somente para defeitos de fabrica
- Não faça comentários sobre a auditoria.
- Retorne SOMENTE a descrição final corrigida.
"""

LANGUAGETOOL_DEFAULT_ENDPOINT = "http://localhost:8081/v2/check"


def auditar_descricao_com_ia(fonte_original, descricao_candidata, prompt_original,
                             api_key, model, endpoint, log=None):
    """Terceiro filtro semântico: compara a saída da primeira IA com a fonte."""
    contexto = (
        "AÇÃO: Auditoria final da descrição Decathlon\n\n"
        f"REGRAS DA TAREFA ORIGINAL:\n{prompt_original}\n\n"
        f"{PROMPT_AUDITOR_DESCRICAO}\n\n"
        f"FONTE ORIGINAL DO PRODUTO:\n{fonte_original}\n\n"
        f"DESCRIÇÃO CANDIDATA:\n{descricao_candidata}\n\n"
        "Compare cuidadosamente a candidata com a fonte e devolva somente a versão final corrigida."
    )
    resultado = chamar_ia(contexto, api_key, model, endpoint, log).strip()
    if not resultado:
        raise RuntimeError("A IA auditora retornou uma descrição vazia.")
    return resultado


def _tokens_numericos(texto):
    return re.findall(r'\d+(?:[.,]\d+)?', texto or "")


def corrigir_com_languagetool(texto, endpoint, api_key="", username="", log=None):
    """Corrige português via LanguageTool de forma conservadora.

    O endpoint padrão é local para não transformar o programa em um cliente
    automatizado do servidor público gratuito. O usuário pode informar um
    servidor próprio ou um endpoint de API contratado.
    """
    endpoint = (endpoint or "").strip()
    if not endpoint or not texto.strip():
        return texto, 0

    payload = {
        "language": "pt-BR",
        "text": texto,
        "level": "default",
    }
    if username.strip():
        payload["username"] = username.strip()
    if api_key.strip():
        payload["apiKey"] = api_key.strip()

    if log:
        log(f"LanguageTool: revisando português ({len(texto)} caracteres)...")

    resposta = requests.post(endpoint, data=payload, timeout=60)
    if resposta.status_code >= 400:
        raise RuntimeError(f"LanguageTool HTTP {resposta.status_code}: {resposta.text[:500]}")

    data = resposta.json()
    matches = data.get("matches") or []
    if not matches:
        if log:
            log("LanguageTool: nenhum ajuste necessário.")
        return texto, 0

    # Aplicar do fim para o começo mantém os offsets originais válidos.
    corrigido = texto
    aplicadas = 0
    aceitas = []
    for match in sorted(matches, key=lambda m: int(m.get("offset", 0)), reverse=True):
        offset = int(match.get("offset", 0))
        length = int(match.get("length", 0))
        replacements = match.get("replacements") or []
        original = corrigido[offset:offset + length]
        if not original or not replacements:
            continue

        issue_type = str(match.get("rule", {}).get("issueType", "")).lower()
        # O LanguageTool também pode sugerir estilo. Neste pipeline queremos
        # correção objetiva de português, não reescrita estilística agressiva.
        if issue_type not in {"misspelling", "grammar", "typographical", "duplication", "other"}:
            continue

        substituto = str(replacements[0].get("value", ""))
        if not substituto or substituto == original:
            continue

        # Nunca aceitar uma sugestão que altere números, códigos ou medidas.
        if _tokens_numericos(original) != _tokens_numericos(substituto):
            continue
        if re.search(r'[A-Za-zÀ-ÿ]*\d[A-Za-zÀ-ÿ]*', original) and original.casefold() != substituto.casefold():
            continue

        corrigido = corrigido[:offset] + substituto + corrigido[offset + length:]
        aceitas.append((original, substituto))
        aplicadas += 1

    if log:
        log(f"LanguageTool: {aplicadas} correção(ões) objetiva(s) aplicada(s).")
    return corrigido, aplicadas


class NotebookAdapter:
    def __init__(self, select_callback):
        self.select_callback = select_callback
        self._current_index = 0

    def select(self, index=None):
        if index is None:
            return self._current_index
        if isinstance(index, int):
            self._current_index = index
            self.select_callback(index)
        return self._current_index

    def index(self, tab=None):
        return self._current_index




def get_resource_path(relative_path):
    import sys, os
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return Path(base_path) / relative_path

def carregar_icone_ui(nome, tamanho=(16, 16)):
    """Carrega ícones para botões neutros/transparentes (adaptam escuro/claro)."""
    base_dir = get_resource_path("assets/icons")
    p_light = base_dir / f"{nome}_light.png"
    p_dark = base_dir / f"{nome}_dark.png"
    if p_light.exists() and p_dark.exists() and PILLOW:
        try:
            img_light = Image.open(p_light)
            img_dark = Image.open(p_dark)
            return ctk.CTkImage(light_image=img_light, dark_image=img_dark, size=tamanho)
        except Exception:
            return None
    return None

def carregar_icone_branco(nome, tamanho=(16, 16)):
    """Carrega ícones brancos para botões primários azuis e abas selecionadas."""
    base_dir = get_resource_path("assets/icons")
    p_white = base_dir / f"{nome}_white.png"
    p_dark = base_dir / f"{nome}_dark.png"
    p = p_white if p_white.exists() else p_dark
    if p.exists() and PILLOW:
        try:
            img_w = Image.open(p)
            return ctk.CTkImage(light_image=img_w, dark_image=img_w, size=tamanho)
        except Exception:
            return None
    return None


class App(ctk.CTk):
    BG = "#12161C"
    PANEL = "#1A2129"
    PANEL2 = "#151B23"
    FIELD = "#0D1218"
    BORDER = "#2A3441"
    TEXT = "#E6EDF3"
    MUTED = "#93A3B6"
    ACCENT = "#3B8EEA"
    ACCENT_HOVER = "#57A0F0"
    OK = "#3FB950"
    SELECT = "#2C4A6E"

    DARK_THEME = {
        "BG": "#12161C", "PANEL": "#1A2129", "PANEL2": "#151B23",
        "FIELD": "#0D1218", "BORDER": "#2A3441", "TEXT": "#E6EDF3",
        "MUTED": "#93A3B6", "ACCENT": "#3B8EEA", "ACCENT_HOVER": "#57A0F0",
        "SELECT": "#2C4A6E",
    }
    LIGHT_THEME = {
        "BG": "#F4F6F8", "PANEL": "#FFFFFF", "PANEL2": "#E9EEF3",
        "FIELD": "#FFFFFF", "BORDER": "#C9D3DE", "TEXT": "#1B2733",
        "MUTED": "#5D6B78", "ACCENT": "#1769AA", "ACCENT_HOVER": "#2B7FBD",
        "SELECT": "#B8D7EF",
    }

    def __init__(self):
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        super().__init__()

        self.title("DataHub - Automatizando Cadastros")
        self.geometry("1280x860")
        self.minsize(900, 620)
        try:
            self.iconbitmap(str(get_resource_path("icone_app.ico")))
        except Exception:
            pass
        self.withdraw()

        self.pasta_base = Path.home() / "Imagens" / "download" / "imagens"
        self.ultima_pasta = None
        self.referencia_atual = ""
        self.thumb_images = []
        self.galeria_arquivos = []
        self._galeria_cols = 0
        self.modo_escuro = True
        self.ia_config = carregar_config_ia()
        self.ia_presets = dict(IA_PRESETS)
        self.ia_presets.update(self.ia_config.get("prompts", {}) if isinstance(self.ia_config.get("prompts", {}), dict) else {})

        self.status = tk.StringVar(value="Pronto.")
        self.notebook = NotebookAdapter(self._selecionar_view_por_indice)

        self.views = []
        self.nav_buttons = []
        self.current_view_index = 0

        self._montar_layout()

        if not PILLOW:
            self.log("Pillow não instalado — o programa precisa dele para garantir JPG.")
            
        self.after(100, self._mostrar_splash_screen)

    def _mostrar_splash_screen(self):
        video_path = str(get_resource_path("intro.mp4"))
        import os
        import time
        if not os.path.exists(video_path):
            self.deiconify()
            return
            
        try:
            import cv2
            from PIL import Image, ImageTk, ImageDraw
        except ImportError:
            self.deiconify()
            return

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            self.deiconify()
            return

        splash = tk.Toplevel(self)
        splash.overrideredirect(True)
        splash.attributes("-topmost", True)
        
        orig_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # Janela menor: max 640px de largura mantendo a proporção
        max_w = 640
        if orig_width > max_w:
            ratio = max_w / orig_width
            vid_width = int(orig_width * ratio)
            vid_height = int(orig_height * ratio)
        else:
            vid_width = orig_width
            vid_height = orig_height
        
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - vid_width) // 2
        y = (screen_height - vid_height) // 2
        splash.geometry(f"{vid_width}x{vid_height}+{x}+{y}")
        
        trans_color = "#000001"
        splash.config(bg=trans_color)
        splash.attributes("-transparentcolor", trans_color)
        
        lbl = tk.Label(splash, bg=trans_color, bd=0, highlightthickness=0)
        lbl.pack(fill="both", expand=True)
        
        radius = 40
        mask = Image.new("L", (vid_width, vid_height), 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle((0, 0, vid_width, vid_height), radius, fill=255)
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        # O tkinter adiciona muito atraso por conta do mainloop.
        # Definir delay em 10ms força o loop a rodar o mais rápido possível
        # para compensar o gargalo do Python/Tkinter e manter o vídeo suave.
        delay = 8
        
        def _play_frame():
            ret, frame = cap.read()
                
            if not ret or frame is None:
                cap.release()
                splash.destroy()
                self.deiconify()
                return
                
            if vid_width != orig_width:
                frame = cv2.resize(frame, (vid_width, vid_height), interpolation=cv2.INTER_NEAREST)
                
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame).convert("RGBA")
            img.putalpha(mask)
            imgtk = ImageTk.PhotoImage(image=img)
            lbl.imgtk = imgtk
            lbl.configure(image=imgtk)
            
            splash.after(delay, _play_frame)
            
        splash.after(250, _play_frame)

    def _alterar_modo_aparencia(self, novo_modo):
        pass

    def _selecionar_view(self, index):
        self.current_view_index = index
        self.notebook._current_index = index
        for i, view in enumerate(self.views):
            if i == index:
                view.grid(row=0, column=0, sticky="nsew")
            else:
                view.grid_forget()

        for i, btn in enumerate(self.nav_buttons):
            if hasattr(self, 'nav_items_data'):
                view_idx = self.nav_items_data[i][1]
                icon_name = self.nav_items_data[i][2]
            else:
                view_idx = i
                icon_name = None
                
            if view_idx == index:
                icon_w = carregar_icone_branco(icon_name, (18, 18)) if icon_name else None
                btn.configure(fg_color=("#3B8EEA", "#3B8EEA"), text_color="#FFFFFF", image=icon_w)
            else:
                icon_n = carregar_icone_ui(icon_name, (18, 18)) if icon_name else None
                btn.configure(fg_color="transparent", text_color=("gray15", "gray90"), image=icon_n)

        if hasattr(self, 'header_card'):
            if index in [0, 2]:
                self.header_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
            else:
                self.header_card.grid_forget()

    def _selecionar_view_por_indice(self, index):
        self._selecionar_view(index)

    def _montar_layout(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # SIDEBAR
        self.sidebar = ctk.CTkFrame(self, width=240, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        logo_label = ctk.CTkLabel(
            self.sidebar, text="DataHub", font=("Segoe UI", 24, "bold"),
            text_color=("#1f538d", "#3B8EEA")
        )
        logo_label.grid(row=0, column=0, padx=20, pady=(20, 2), sticky="w")
        sub_logo = ctk.CTkLabel(
            self.sidebar, text="AUTOMATIZAÇÃO & IA", font=("Segoe UI", 10, "bold"),
            text_color=("gray35", "gray65")
        )
        sub_logo.grid(row=1, column=0, padx=20, pady=(0, 16), sticky="w")

        def _carregar_icone(nome):
            base_dir = ASSETS_DIR / "icons"
            p_light = base_dir / f"{nome}_light.png"
            p_dark = base_dir / f"{nome}_dark.png"
            if p_light.exists() and p_dark.exists() and PILLOW:
                try:
                    img_light = Image.open(p_light)
                    img_dark = Image.open(p_dark)
                    return ctk.CTkImage(light_image=img_light, dark_image=img_dark, size=(18, 18))
                except Exception:
                    return None
            return None

        self.nav_items_data = [
            ("Fotos por URL", 0, "coleta"),
            ("Fotos por Planilha", 1, "pasta"),
            ("Gerar Descrição", 2, "descricao"),
            ("Informações de Anatel", 4, "anatel"),
            ("HTML & Logs", 5, "html_logs"),
            ("Buscar URL por REF", 6, "buscar_ref"),
            ("Configurações da IA", 3, "ia"),
            ("Configurações do Sistema", 7, "config"),
            ("Sobre", 8, "info"),
        ]

        self.nav_buttons = []
        for i, (text, idx, icon_name) in enumerate(self.nav_items_data):
            icon = carregar_icone_ui(icon_name, (18, 18))
            kwargs = {
                "text": f"  {text}",
                "font": ("Segoe UI", 11, "bold"),
                "anchor": "w",
                "fg_color": "transparent",
                "text_color": ("gray15", "gray90"),
                "height": 38,
                "corner_radius": 8,
                "command": lambda v=idx: self._selecionar_view(v),
            }
            if icon:
                kwargs["image"] = icon
                kwargs["compound"] = "left"
            btn = ctk.CTkButton(self.sidebar, **kwargs)
            btn.grid(row=2 + i, column=0, padx=12, pady=4, sticky="ew")
            self.nav_buttons.append(btn)
            
        spacer = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        spacer.grid(row=99, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(99, weight=1)

        # Sem seletor de tema — modo Dark fixo

        # ── Checklist na sidebar (auto-preenchido) ──────────────────────────
        self.checklist_vars = {}
        checklist_itens = [
            ("busca",       "Busca na fonte"),
            ("extracao",    "Extração"),
            ("formatacao",  "Formatação"),
            ("ia",          "IA principal"),
            ("auditoria",   "IA auditora"),
            ("languagetool","LanguageTool"),
            ("validador",   "Validador"),
            ("validacao",   "Validação"),
            ("final",       "Concluído"),
        ]

        # ── Checklist na sidebar removido da UI a pedido do usuário ─────
        for chave, rotulo in checklist_itens:
            self.checklist_vars[chave] = tk.BooleanVar(value=False)

        # Vars de modo coleta — controladas programaticamente
        self.var_fotos = tk.BooleanVar(value=True)
        self.var_descricao = tk.BooleanVar(value=True)

        # MAIN CONTAINER
        self.main_container = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_container.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)
        self.main_container.grid_rowconfigure(1, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)

        # HEADER BAR
        self.header_card = ctk.CTkFrame(self.main_container, corner_radius=12)
        self.header_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        url_frame = ctk.CTkFrame(self.header_card, fg_color="transparent")
        url_frame.pack(fill="x", padx=16, pady=14)
        url_frame.grid_columnconfigure(0, weight=1)

        self.entrada_url = ctk.CTkEntry(
            url_frame, placeholder_text="Cole a URL do produto Decathlon...",
            font=("Segoe UI", 12, "bold"), height=40, corner_radius=8
        )
        self.entrada_url.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.entrada_url.bind("<Return>", lambda e: self.iniciar())

        self.botao_limpar = ctk.CTkButton(
            url_frame, text=" LIMPAR TUDO", image=carregar_icone_ui("limpar", (16, 16)), compound="left", font=("Segoe UI", 10, "bold"),
            fg_color="transparent", border_width=1, height=40, corner_radius=8,
            command=self.limpar_tudo
        )
        self.botao_limpar.grid(row=0, column=1, padx=(0, 6))

        self.botao_pasta = ctk.CTkButton(
            url_frame, text=" ABRIR PASTA", image=carregar_icone_ui("pasta", (16, 16)), compound="left", font=("Segoe UI", 10, "bold"),
            fg_color="transparent", border_width=1, height=40, corner_radius=8,
            command=self.abrir, state="disabled"
        )
        # self.botao_pasta.grid(row=0, column=3)  # Ocultado a pedido do usuário

        # VIEWS HOLDER
        self.views_holder = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.views_holder.grid(row=1, column=0, sticky="nsew")
        self.views_holder.grid_rowconfigure(0, weight=1)
        self.views_holder.grid_columnconfigure(0, weight=1)

        self.views = []
        for i in range(len(self.nav_items_data)):
            v = ctk.CTkFrame(self.views_holder, fg_color="transparent")
            v.grid_rowconfigure(0, weight=1)
            v.grid_columnconfigure(0, weight=1)
            self.views.append(v)

        self._montar_view_coleta(self.views[0])
        self._montar_view_planilha(self.views[1])
        self._montar_view_desc(self.views[2])
        self._montar_view_ia(self.views[3])
        self._montar_view_anatel(self.views[4])
        self._montar_view_html(self.views[5])
        self._montar_view_ref(self.views[6])
        self._montar_view_config(self.views[7])
        self._montar_view_sobre(self.views[8])

        # STATUS BAR FOOTER
        status_card = ctk.CTkFrame(self.main_container, corner_radius=8, height=32)
        status_card.grid(row=2, column=0, sticky="ew", pady=(10, 0))

        self.status_label = ctk.CTkLabel(
            status_card, textvariable=self.status, font=("Segoe UI", 11, "bold"),
            anchor="w"
        )
        self.status_label.pack(side="left", padx=12, pady=6)

        self._selecionar_view(0)

    def _montar_view_coleta(self, parent):
        parent.grid_rowconfigure(0, weight=0)
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        # Header com botão de ação
        hdr = ctk.CTkFrame(parent, corner_radius=12)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        ctk.CTkLabel(hdr, text="Coleta de Imagens", font=("Segoe UI", 15, "bold")).pack(
            side="left", padx=16, pady=0
        )
        ctk.CTkButton(
            hdr, text=" Coletar Fotos",
            image=carregar_icone_branco("coleta", (16, 16)), compound="left",
            fg_color="#3B8EEA", hover_color="#57A0F0",
            font=("Segoe UI", 11, "bold"), height=36,
            command=self._iniciar_fotos
        ).pack(side="right", padx=13, pady=10)

        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        scroll.grid_columnconfigure(1, weight=1)

        c2 = ctk.CTkFrame(scroll, corner_radius=12)
        c2.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 12), padx=4)
        c2.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(c2, text="Informações do Produto Coletado", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 8)
        )

        self.info_ref = ctk.CTkLabel(c2, text="—", font=("Segoe UI", 12, "bold"))
        self.info_nome = ctk.CTkLabel(c2, text="—", font=("Segoe UI", 12, "bold"), justify="left", wraplength=280)
        self.info_marca = ctk.CTkLabel(c2, text="—", font=("Segoe UI", 12, "bold"))
        self.info_categoria = ctk.CTkLabel(c2, text="—", font=("Segoe UI", 12, "bold"), justify="left", wraplength=280)

        info_rows = [
            ("Referência:", self.info_ref),
            ("Produto:", self.info_nome),
            ("Marca:", self.info_marca),
            ("Categoria:", self.info_categoria),
        ]
        for idx, (label_text, widget) in enumerate(info_rows):
            ctk.CTkLabel(c2, text=label_text, font=("Segoe UI", 11, "bold"), text_color=("gray35", "gray65")).grid(
                row=idx+1, column=0, sticky="nw", padx=(16, 10), pady=6
            )
            widget.grid(row=idx+1, column=1, sticky="w", padx=(0, 16), pady=6)


        c3_fotos = ctk.CTkFrame(scroll, corner_radius=12)
        c3_fotos.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(0, 12), padx=4)
        c3_fotos.grid_columnconfigure(0, weight=1)
        c3_fotos.grid_rowconfigure(1, weight=1)
        self._montar_view_fotos(c3_fotos)

        c4 = ctk.CTkFrame(scroll, corner_radius=12)
        c4.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(0, 4), padx=4)
        c4.grid_columnconfigure(0, weight=1)
        c4.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(c4, text="Log de Atividades", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 8)
        )
        self.saida = ctk.CTkTextbox(c4, font=("Consolas", 11, "bold"), height=140)
        self.saida.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))

    def _montar_view_fotos(self, parent):
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(parent, corner_radius=12)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        ctk.CTkLabel(header, text="Galeria de Fotos do Produto", font=("Segoe UI", 16, "bold")).pack(
            side="left", padx=16, pady=12
        )
        btn_abrir = ctk.CTkButton(header, text=" Abrir Pasta no Explorer", image=carregar_icone_ui("pasta", (16, 16)), compound="left", command=self.abrir)
        btn_abrir.pack(side="right", padx=13, pady=12)

        self.galeria_canvas = tk.Canvas(parent, highlightthickness=0, background="#2B2B2B", bd=0)
        self.galeria_scroll = ctk.CTkScrollbar(parent, orientation="vertical", command=self.galeria_canvas.yview)
        self.galeria_canvas.configure(yscrollcommand=self.galeria_scroll.set)

        self.galeria_canvas.grid(row=1, column=0, sticky="nsew")
        self.galeria_scroll.grid(row=1, column=1, sticky="ns")

        self.galeria_frame = tk.Frame(self.galeria_canvas, background="#2B2B2B")
        self.galeria_window = self.galeria_canvas.create_window((0, 0), window=self.galeria_frame, anchor="nw")

        self.galeria_frame.bind(
            "<Configure>",
            lambda e: self.galeria_canvas.configure(scrollregion=self.galeria_canvas.bbox("all"))
        )
        self.galeria_canvas.bind("<Configure>", self._galeria_redimensionada)
        self.galeria_canvas.bind_all("<MouseWheel>", self._rolar_galeria)

        self._render_galeria()

    def _montar_view_desc(self, parent):
        parent.grid_rowconfigure(0, weight=0)
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_rowconfigure(2, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        # Header com botão de ação
        hdr = ctk.CTkFrame(parent, corner_radius=12)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(hdr, text="Geração de Descrição", font=("Segoe UI", 15, "bold")).pack(
            side="left", padx=16, pady=12
        )
        ctk.CTkButton(
            hdr, text=" Gerar Descrição",
            image=carregar_icone_branco("coleta", (16, 16)), compound="left",
            fg_color="#3B8EEA", hover_color="#57A0F0",
            font=("Segoe UI", 11, "bold"), height=36,
            command=self._iniciar_descricao
        ).pack(side="right", padx=13, pady=10)

        c1 = ctk.CTkFrame(parent, corner_radius=12)
        c1.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        c1.grid_rowconfigure(1, weight=1)
        c1.grid_columnconfigure(0, weight=1)

        top1 = ctk.CTkFrame(c1, fg_color="transparent")
        top1.grid(row=0, column=0, sticky="ew", padx=16, pady=10)

        ctk.CTkLabel(top1, text="Descrição Estruturada Completa", font=("Segoe UI", 14, "bold")).pack(side="left")
        btn_recopiar = ctk.CTkButton(top1, text=" Copiar", image=carregar_icone_ui("copiar", (16, 16)), compound="left", width=90, command=self.copiar_descricao)
        btn_recopiar.pack(side="right", padx=(8, 0))

        btn_refetch = ctk.CTkButton(top1, text=" Buscar novamente", image=carregar_icone_ui("atualizar", (16, 16)), compound="left", command=self.buscar_descricao_novamente)
        btn_refetch.pack(side="right")

        self.output = ctk.CTkTextbox(c1, font=("Segoe UI", 12, "bold"), wrap="word")
        self.output.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))

        c2 = ctk.CTkFrame(parent, corner_radius=12)
        c2.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        c2.grid_rowconfigure(1, weight=1)
        c2.grid_columnconfigure(0, weight=1)

        top2 = ctk.CTkFrame(c2, fg_color="transparent")
        top2.grid(row=0, column=0, sticky="ew", padx=16, pady=10)

        ctk.CTkLabel(top2, text="Descrição Curta — Livelo (Máx. 2500 caracteres)", font=("Segoe UI", 14, "bold")).pack(side="left")

        btn_copy_curta = ctk.CTkButton(top2, text=" Copiar Curta", image=carregar_icone_ui("copiar", (16, 16)), compound="left", command=self.copiar_descricao_curta)
        btn_copy_curta.pack(side="right", padx=(8, 0))

        btn_gen_curta = ctk.CTkButton(top2, text=" Gerar Curta", image=carregar_icone_ui("executar", (16, 16)), compound="left", command=self.gerar_descricao_curta)
        btn_gen_curta.pack(side="right")

        self.descricao_curta = ctk.CTkTextbox(c2, font=("Segoe UI", 12, "bold"), wrap="word")
        self.descricao_curta.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))
        self.descricao_curta.bind("<KeyRelease>", self._atualizar_contador_descricao_curta)

        bot2 = ctk.CTkFrame(c2, fg_color="transparent")
        bot2.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))

        self.descricao_curta_status = ctk.CTkLabel(bot2, text="Aguardando geração...", font=("Segoe UI", 11, "bold"), text_color=("gray35", "gray65"))
        self.descricao_curta_status.pack(side="left")

        self.descricao_curta_contador = ctk.CTkLabel(bot2, text="0 / 2500 caracteres", font=("Segoe UI", 11, "bold"))
        self.descricao_curta_contador.pack(side="right")

    def _montar_view_ia(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        c1 = ctk.CTkFrame(scroll, corner_radius=12)
        c1.grid(row=0, column=0, sticky="ew", pady=(0, 12), padx=4)
        c1.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(c1, text="Assistente de Cadastro & Qualidade (IA)", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 8)
        )

        ia_fields = [
            ("Modelo:", "ia_modelo", self.ia_config.get("model", IA_DEFAULT_MODEL), False),
            ("API Key:", "ia_api_key", self.ia_config.get("api_key", ""), True),
            ("Endpoint:", "ia_endpoint", self.ia_config.get("endpoint", IA_DEFAULT_ENDPOINT), False),
            ("Drive API:", "drive_api_key", self.ia_config.get("google_drive_api_key", ""), True),
        ]
        _r = 1
        for label_text, attr_name, val, is_show in ia_fields[:4]:
            ctk.CTkLabel(c1, text=label_text, font=("Segoe UI", 11, "bold")).grid(row=_r, column=0, sticky="w", padx=16, pady=4)
            entry = ctk.CTkEntry(c1, show="•" if is_show else "")
            entry.insert(0, val)
            entry.grid(row=_r, column=1, sticky="ew", padx=16, pady=4)
            setattr(self, attr_name, entry)
            _r += 1
        self.lt_ativado = tk.BooleanVar(value=bool(self.ia_config.get("languagetool_enabled", False)))
        ctk.CTkCheckBox(c1, text="Ativar revisão automática de português (LanguageTool)", variable=self.lt_ativado).grid(
            row=_r, column=0, columnspan=2, sticky="w", padx=16, pady=6
        )
        _r += 1
        # Campos do LT removidos a pedido do usuário
        ctk.CTkButton(c1, text=" Salvar Configurações", image=carregar_icone_ui("salvar", (16, 16)), compound="left",
                      fg_color="#3B8EEA", hover_color="#57A0F0",
                      command=self.salvar_configuracao_ia).grid(
            row=_r, column=0, columnspan=2, sticky="e", padx=16, pady=(8, 14)
        )

        c2 = ctk.CTkFrame(scroll, corner_radius=12)
        c2.grid(row=1, column=0, sticky="ew", pady=(0, 12), padx=4)
        c2.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(c2, text="Ação e Prompts", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 8)
        )

        ctk.CTkLabel(c2, text="Ação / Template:", font=("Segoe UI", 11, "bold")).grid(row=1, column=0, sticky="w", padx=16, pady=4)
        self.ia_acao = ctk.CTkOptionMenu(c2, values=list(self.ia_presets.keys()))
        self.ia_acao.set("Template Decathlon - Estrutura Automática")
        self.ia_acao.grid(row=1, column=1, sticky="ew", padx=16, pady=4)

        c3 = ctk.CTkFrame(scroll, corner_radius=12)
        c3.grid(row=2, column=0, sticky="ew", pady=(0, 12), padx=4)
        c3.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(c3, text="Editor de Prompt", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=16, pady=(14, 4))
        self.ia_prompt = ctk.CTkTextbox(c3, font=("Consolas", 11, "bold"), height=120)
        self.ia_prompt.pack(fill="x", padx=16, pady=4)
        self.ia_prompt.insert("1.0", self.ia_presets.get("Template Decathlon - Estrutura Automática", ""))

        prompt_action_frame = ctk.CTkFrame(c3, fg_color="transparent")
        prompt_action_frame.pack(fill="x", padx=16, pady=4)
        ctk.CTkButton(prompt_action_frame, text=" Salvar Prompt Criado", image=carregar_icone_ui("salvar", (16, 16)), compound="left", command=self.ia_salvar_prompt_como).pack(side="left", padx=(0, 6))
        ctk.CTkButton(prompt_action_frame, text=" Excluir Selecionado", image=carregar_icone_ui("limpar", (16, 16)), compound="left", fg_color="#D9534F", hover_color="#C9302C", command=self.ia_excluir_prompt).pack(side="left", padx=(0, 6))

        # Hidden IA resultado widget so we don't break logic calling it
        self.ia_resultado = ctk.CTkTextbox(c3, font=("Segoe UI", 12, "bold"), height=160)


    def _montar_view_anatel(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        c1 = ctk.CTkFrame(scroll, corner_radius=12)
        c1.grid(row=0, column=0, sticky="ew", pady=(0, 12), padx=4)
        c1.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(c1, text="Consulta de Homologação ANATEL", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=16, pady=(14, 8))

        row1 = ctk.CTkFrame(c1, fg_color="transparent")
        row1.pack(fill="x", padx=16, pady=4)
        row1.grid_columnconfigure(0, weight=1)

        self.entrada_anatel = ctk.CTkEntry(row1, placeholder_text="Número de homologação...", font=("Segoe UI", 12, "bold"), height=38)
        self.entrada_anatel.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.entrada_anatel.bind("<Return>", lambda e: self.iniciar_anatel())

        btn_colar = ctk.CTkButton(row1, text=" Colar", image=carregar_icone_ui("copiar", (16, 16)), compound="left", width=90, height=38, command=self.colar_anatel)
        btn_colar.grid(row=0, column=1, padx=(0, 8))

        self.botao_anatel = ctk.CTkButton(row1, text="Consultar e confirmar", height=38, fg_color="#3B8EEA", command=self.iniciar_anatel)
        self.botao_anatel.grid(row=0, column=2)

        self.anatel_status = tk.StringVar(value="Aguardando número de homologação.")
        ctk.CTkLabel(c1, textvariable=self.anatel_status, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(8, 14))


        # Gerenciador da Base ANATEL movido para view Configurações

        c3 = ctk.CTkFrame(scroll, corner_radius=12)
        c3.grid(row=1, column=0, sticky="ew", pady=(0, 4), padx=4)
        c3.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(c3, text="Detalhes da Consulta", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=16, pady=(14, 8))
        self.anatel_container = ctk.CTkScrollableFrame(c3, height=200, fg_color="transparent")
        self.anatel_container.pack(fill="x", padx=16, pady=(0, 16))


    def _montar_view_sobre(self, parent):
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        
        c = ctk.CTkFrame(parent, corner_radius=12)
        c.grid(row=0, column=0, sticky="nsew", padx=40, pady=40)
        
        # Centralizando os elementos internamente
        c.grid_columnconfigure(0, weight=1)
        
        lbl_title = ctk.CTkLabel(c, text="DataHub", font=("Segoe UI", 32, "bold"))
        lbl_title.grid(row=0, column=0, pady=(60, 5))
        
        lbl_version = ctk.CTkLabel(c, text="Versão: v1.5", font=("Segoe UI", 16), text_color="gray60")
        lbl_version.grid(row=1, column=0, pady=(0, 30))
        
        lbl_devs = ctk.CTkLabel(c, text="Desenvolvedores:\nEduardo Stocki, Felps, Thiago Cezario", font=("Segoe UI", 15), justify="center")
        lbl_devs.grid(row=2, column=0, pady=15)
        
        lbl_helpers = ctk.CTkLabel(c, text="Com a ajuda de:\nGuilherme Henrique e Felipe Lukasievcz", font=("Segoe UI", 15), justify="center")
        lbl_helpers.grid(row=3, column=0, pady=15)

    def _montar_view_config(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        scroll.grid_columnconfigure(1, weight=1)

        # Initialize var_formato to avoid errors in logic using it
        self.var_formato = tk.StringVar(value=FORMATOS_CADASTRO[0])

        # ── Seção 2: Tamanho das Imagens ────────────────────────────────────
        s2 = ctk.CTkFrame(scroll, corner_radius=12)
        s2.grid(row=0, column=0, sticky="ew", pady=(0, 12), padx=(4, 6))
        s2.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(s2, text="Tamanho das Imagens", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 8)
        )

        ctk.CTkLabel(s2, text="Predefinição:", font=("Segoe UI", 11, "bold")).grid(
            row=1, column=0, sticky="w", padx=16, pady=4
        )
        self.combo_tamanho = ctk.CTkOptionMenu(
            s2, values=TAMANHOS_PRESET, command=self._alternar_personalizado
        )
        self.combo_tamanho.set("1000x1000")
        self.combo_tamanho.grid(row=1, column=1, sticky="ew", padx=16, pady=4)

        self.frame_personalizado = ctk.CTkFrame(s2, fg_color="transparent")
        self.frame_personalizado.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(4, 14))

        ctk.CTkLabel(self.frame_personalizado, text="Largura:").pack(side="left", padx=(0, 6))
        self.campo_largura = ctk.CTkEntry(self.frame_personalizado, width=80)
        self.campo_largura.insert(0, "1000")
        self.campo_largura.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(self.frame_personalizado, text="Altura:").pack(side="left", padx=(0, 6))
        self.campo_altura = ctk.CTkEntry(self.frame_personalizado, width=80)
        self.campo_altura.insert(0, "1000")
        self.campo_altura.pack(side="left")

        self.frame_personalizado.grid_remove()

        ctk.CTkLabel(s2, text="Formato:", font=("Segoe UI", 11, "bold")).grid(
            row=3, column=0, sticky="w", padx=16, pady=4
        )
        self.var_formato_img = tk.StringVar(value="JPG")
        self.combo_formato_img = ctk.CTkOptionMenu(
            s2, variable=self.var_formato_img, values=["JPG", "PNG"]
        )
        self.combo_formato_img.grid(row=3, column=1, sticky="ew", padx=16, pady=4)

        # ── Seção 3: Pasta de Destino ────────────────────────────────────────
        s3 = ctk.CTkFrame(scroll, corner_radius=12)
        s3.grid(row=0, column=1, sticky="ew", pady=(0, 12), padx=(6, 4))
        s3.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(s3, text="Pasta de Destino", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=16, pady=(14, 8)
        )
        self.rotulo_pasta = ctk.CTkLabel(
            s3, text=str(self.pasta_base), font=("Segoe UI", 11, "bold"),
            text_color=("gray35", "gray65"), justify="left", wraplength=300, anchor="w"
        )
        self.rotulo_pasta.pack(fill="x", padx=16, pady=(0, 10))

        ctk.CTkButton(
            s3, text=" Escolher Pasta", image=carregar_icone_ui("pasta", (16, 16)),
            compound="left", command=self.escolher_pasta
        ).pack(fill="x", padx=16, pady=4)
        
        self.var_abrir_pasta = tk.BooleanVar(value=True)
        ctk.CTkSwitch(
            s3, text="Abrir pasta após baixar fotos (Drive/Planilha)", variable=self.var_abrir_pasta
        ).pack(anchor="w", padx=16, pady=(4, 14))

        # Botão Copiar Descrição removido a pedido do usuário

        # ── Seção 4 (ex-5): Base ANATEL ─────────────────────────────────────
        s5 = ctk.CTkFrame(scroll, corner_radius=12)
        s5.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 4), padx=4)
        s5.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(s5, text="Gerenciador da Base ANATEL", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=16, pady=(14, 8)
        )

        self.anatel_base_status = tk.StringVar(value=self._descricao_base_anatel())
        ctk.CTkLabel(
            s5, textvariable=self.anatel_base_status, font=("Segoe UI", 11, "bold"),
            text_color=("gray35", "gray65")
        ).pack(anchor="w", padx=16, pady=(0, 8))

        anatel_btns = ctk.CTkFrame(s5, fg_color="transparent")
        anatel_btns.pack(fill="x", padx=16, pady=(0, 14))

        self.botao_anatel_selecionar = ctk.CTkButton(
            anatel_btns, text=" Selecionar base...",
            image=carregar_icone_ui("pasta", (16, 16)), compound="left",
            command=self.selecionar_base_anatel
        )
        self.botao_anatel_selecionar.pack(side="left", padx=(0, 10))

        self.botao_anatel_atualizar = ctk.CTkButton(
            anatel_btns, text=" Atualizar base oficial",
            image=carregar_icone_ui("atualizar", (16, 16)), compound="left",
            command=self.atualizar_base_anatel_botao
        )
        self.botao_anatel_atualizar.pack(side="left")

    def _montar_view_html(self, parent):
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        c1 = ctk.CTkFrame(parent, corner_radius=12)
        c1.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        c1.grid_rowconfigure(1, weight=1)
        c1.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(c1, text="Código-fonte HTML (Contingência Manual)", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 8)
        )
        self.texto_html = ctk.CTkTextbox(c1, font=("Consolas", 11, "bold"))
        self.texto_html.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))

        c2 = ctk.CTkFrame(parent, corner_radius=12)
        c2.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        c2.grid_rowconfigure(1, weight=1)
        c2.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(c2, text="Terminal Completo de Logs", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 8)
        )
        self.saida_full = ctk.CTkTextbox(c2, font=("Consolas", 11, "bold"))
        self.saida_full.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))

    def _montar_view_ref(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        # Card 1: Busca Individual por REF
        c1 = ctk.CTkFrame(scroll, corner_radius=12)
        c1.grid(row=0, column=0, sticky="ew", pady=(0, 12), padx=4)
        c1.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(c1, text="Buscar produto por REF (Decathlon)", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=16, pady=(14, 8)
        )

        row_input = ctk.CTkFrame(c1, fg_color="transparent")
        row_input.pack(fill="x", padx=16, pady=4)
        row_input.grid_columnconfigure(0, weight=1)

        self.ref_busca_entry = ctk.CTkEntry(
            row_input, placeholder_text="Informe a REF do produto (ex: 8767072)...",
            font=("Segoe UI", 12, "bold"), height=38
        )
        self.ref_busca_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.ref_busca_entry.bind("<Return>", lambda e: self.iniciar_busca_ref())

        self.ref_busca_btn = ctk.CTkButton(
            row_input, text=" Buscar Produto", image=carregar_icone_ui("buscar_ref", (16, 16)), compound="left", font=("Segoe UI", 12, "bold"),
            fg_color="#3B8EEA", hover_color="#57A0F0", height=38,
            command=self.iniciar_busca_ref
        )
        self.ref_busca_btn.grid(row=0, column=1)

        res_box = ctk.CTkFrame(c1, fg_color="transparent")
        res_box.pack(fill="x", padx=16, pady=(8, 14))

        self.ref_result_status = ctk.CTkLabel(res_box, text="Aguardando consulta...", font=("Segoe UI", 12, "bold"), text_color=("gray35", "gray65"))
        self.ref_result_status.pack(anchor="w", pady=(0, 6))

        info_grid = ctk.CTkFrame(res_box, fg_color="transparent")
        info_grid.pack(fill="x", pady=4)
        info_grid.grid_columnconfigure(1, weight=1)

        self.ref_result_nome = ctk.CTkLabel(info_grid, text="—", font=("Segoe UI", 12, "bold"), anchor="w", justify="left")
        self.ref_result_ref = ctk.CTkLabel(info_grid, text="—", font=("Segoe UI", 12, "bold"), anchor="w")
        self.ref_result_url = ctk.CTkLabel(info_grid, text="—", font=("Segoe UI", 11, "bold"), text_color="#3B8EEA", anchor="w", justify="left", wraplength=550)

        ctk.CTkLabel(info_grid, text="Produto:", font=("Segoe UI", 11, "bold"), text_color=("gray35", "gray65")).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=3)
        self.ref_result_nome.grid(row=0, column=1, sticky="w", pady=3)

        ctk.CTkLabel(info_grid, text="REF:", font=("Segoe UI", 11, "bold"), text_color=("gray35", "gray65")).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=3)
        self.ref_result_ref.grid(row=1, column=1, sticky="w", pady=3)

        ctk.CTkLabel(info_grid, text="URL:", font=("Segoe UI", 11, "bold"), text_color=("gray35", "gray65")).grid(row=2, column=0, sticky="nw", padx=(0, 10), pady=3)
        self.ref_result_url.grid(row=2, column=1, sticky="w", pady=3)

        btn_row = ctk.CTkFrame(res_box, fg_color="transparent")
        btn_row.pack(fill="x", pady=(10, 0))

        self.ref_btn_copiar = ctk.CTkButton(
            btn_row, text=" Copiar URL", image=carregar_icone_ui("copiar", (16, 16)), compound="left", state="disabled", command=self.copiar_url_ref
        )
        self.ref_btn_copiar.pack(side="left", padx=(0, 10))

        self.ref_btn_abrir = ctk.CTkButton(
            btn_row, text=" Abrir produto", image=carregar_icone_ui("abrir_link", (16, 16)), compound="left", state="disabled", fg_color="transparent", border_width=1,
            command=self.abrir_url_ref
        )
        self.ref_btn_abrir.pack(side="left")

        # Card 2: Busca de REFs em Lote
        c2 = ctk.CTkFrame(scroll, corner_radius=12)
        c2.grid(row=1, column=0, sticky="ew", pady=(0, 4), padx=4)
        c2.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(c2, text="Buscar várias REFs em Lote", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=16, pady=(14, 8)
        )
        ctk.CTkLabel(
            c2, text="Digite ou cole as REFs (uma por linha ou separadas por espaço):",
            font=("Segoe UI", 11, "bold"), text_color=("gray35", "gray65")
        ).pack(anchor="w", padx=16, pady=(0, 6))

        self.ref_lote_textbox = ctk.CTkTextbox(c2, font=("Consolas", 11, "bold"), height=100)
        self.ref_lote_textbox.pack(fill="x", padx=16, pady=4)

        lote_btns = ctk.CTkFrame(c2, fg_color="transparent")
        lote_btns.pack(fill="x", padx=16, pady=8)

        self.ref_lote_btn_buscar = ctk.CTkButton(
            lote_btns, text=" Buscar Todas", image=carregar_icone_branco("buscar_ref", (16, 16)), compound="left", fg_color="#3B8EEA", text_color="#FFFFFF", hover_color="#57A0F0",
            command=self.iniciar_busca_lote_ref
        )
        self.ref_lote_btn_buscar.pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            lote_btns, text=" Limpar Lote", image=carregar_icone_ui("limpar", (16, 16)), compound="left", fg_color="transparent", border_width=1,
            command=self.limpar_lote_ref
        ).pack(side="left")

        self.ref_lote_status_label = ctk.CTkLabel(
            c2, text="Aguardando início do lote...", font=("Segoe UI", 11, "bold"), text_color=("gray35", "gray65")
        )
        self.ref_lote_status_label.pack(anchor="w", padx=16, pady=(4, 2))

        self.ref_lote_progressbar = ctk.CTkProgressBar(c2)
        self.ref_lote_progressbar.set(0)
        self.ref_lote_progressbar.pack(fill="x", padx=16, pady=(0, 10))

        tree_frame = ctk.CTkFrame(c2, fg_color="transparent")
        tree_frame.pack(fill="x", padx=16, pady=4)

        columns = ("ref", "nome", "url", "status")
        self.ref_lote_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=7)

        self.ref_lote_tree.heading("ref", text="REF")
        self.ref_lote_tree.heading("nome", text="Produto")
        self.ref_lote_tree.heading("url", text="URL Canônica")
        self.ref_lote_tree.heading("status", text="Status")

        self.ref_lote_tree.column("ref", width=90, anchor="center")
        self.ref_lote_tree.column("nome", width=220, anchor="w")
        self.ref_lote_tree.column("url", width=340, anchor="w")
        self.ref_lote_tree.column("status", width=140, anchor="center")

        tree_scroll = ctk.CTkScrollbar(tree_frame, orientation="vertical", command=self.ref_lote_tree.yview)
        self.ref_lote_tree.configure(yscrollcommand=tree_scroll.set)

        self.ref_lote_tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        bot_lote = ctk.CTkFrame(c2, fg_color="transparent")
        bot_lote.pack(fill="x", padx=16, pady=(10, 16))

        self.ref_lote_btn_copiar = ctk.CTkButton(
            bot_lote, text=" Copiar Todas as URLs Encontradas", image=carregar_icone_ui("copiar", (16, 16)), compound="left", state="disabled",
            command=self.copiar_urls_lote
        )
        self.ref_lote_btn_copiar.pack(side="left")

    def iniciar_busca_ref(self):
        raw_ref = self.ref_busca_entry.get()
        ref = normalizar_ref(raw_ref)
        if not ref:
            messagebox.showwarning("Buscar por REF", "Informe o número de referência (REF) do produto.")
            return

        self.ref_busca_btn.configure(state="disabled")
        self.ref_btn_copiar.configure(state="disabled")
        self.ref_btn_abrir.configure(state="disabled")
        self.ref_result_status.configure(text=f"Buscando produto para a REF {ref}...", text_color=("gray35", "gray65"))
        self.ref_result_nome.configure(text="Consultando...")
        self.ref_result_ref.configure(text=ref)
        self.ref_result_url.configure(text="Consultando...")

        threading.Thread(target=self._busca_ref_thread, args=(ref,), daemon=True).start()

    def _busca_ref_thread(self, ref):
        res = buscar_produto_por_ref(ref, cache=True, log=self.log)

        def _update():
            self.ref_busca_btn.configure(state="normal")
            if res.get("sucesso"):
                self.ref_result_status.configure(text=res["status_texto"], text_color="#3FB950")
                self.ref_result_nome.configure(text=res["nome"])
                self.ref_result_ref.configure(text=res["ref_encontrada"] or res["ref"])
                self.ref_result_url.configure(text=res["url"])
                self.ref_btn_copiar.configure(state="normal")
                self.ref_btn_abrir.configure(state="normal")
                self.status.set(f"REF {ref}: produto encontrado.")
            else:
                self.ref_result_status.configure(text=res["status_texto"], text_color="#E53935")
                self.ref_result_nome.configure(text="—")
                self.ref_result_ref.configure(text=res["ref"])
                self.ref_result_url.configure(text="—")
                self.ref_btn_copiar.configure(state="disabled")
                self.ref_btn_abrir.configure(state="disabled")
                self.status.set(f"REF {ref}: busca concluída.")

        try:
            self.after(0, _update)
        except tk.TclError:
            pass

    def copiar_url_ref(self):
        url = self.ref_result_url.cget("text")
        if not url or url == "—":
            messagebox.showwarning("Copiar URL", "Nenhuma URL válida para copiar.")
            return
        self.clipboard_clear()
        self.clipboard_append(url)
        self.update()
        self.status.set("URL copiada para a área de transferência.")

    def abrir_url_ref(self):
        url = self.ref_result_url.cget("text")
        if not url or url == "—":
            messagebox.showwarning("Abrir Produto", "Nenhuma URL disponível.")
            return
        try:
            webbrowser.open(url)
            self.status.set("Produto aberto no navegador.")
        except Exception as erro:
            messagebox.showerror("Abrir Produto", f"Não foi possível abrir a URL:\n{erro}")

    def iniciar_busca_lote_ref(self):
        texto = self.ref_lote_textbox.get("1.0", tk.END).strip()
        if not texto:
            messagebox.showwarning("Busca em Lote", "Cole pelo menos uma REF na caixa de texto.")
            return

        tokens = re.split(r"[\s,;]+", texto)
        refs_unicas = []
        vistos = set()
        for tok in tokens:
            r = normalizar_ref(tok)
            if r and r not in vistos:
                vistos.add(r)
                refs_unicas.append(r)

        if not refs_unicas:
            messagebox.showwarning("Busca em Lote", "Nenhuma REF válida encontrada na entrada.")
            return

        for item in self.ref_lote_tree.get_children():
            self.ref_lote_tree.delete(item)

        self.ref_lote_btn_buscar.configure(state="disabled")
        self.ref_lote_btn_copiar.configure(state="disabled")
        self.ref_lote_progressbar.set(0)
        self.ref_lote_status_label.configure(text=f"Iniciando busca de 0 de {len(refs_unicas)}...")

        threading.Thread(target=self._busca_lote_thread, args=(refs_unicas,), daemon=True).start()

    def _busca_lote_thread(self, refs_unicas):
        total = len(refs_unicas)
        encontrados = 0

        for idx, ref in enumerate(refs_unicas, start=1):
            def _prog(i=idx, r=ref):
                self.ref_lote_progressbar.set(i / total)
                self.ref_lote_status_label.configure(text=f"Pesquisando {i} de {total} (REF: {r})...")
            try:
                self.after(0, _prog)
            except tk.TclError:
                pass

            res = buscar_produto_por_ref(ref, cache=True, log=self.log)

            def _add_row(item_res=res):
                if item_res.get("sucesso"):
                    nonlocal encontrados
                    encontrados += 1
                self.ref_lote_tree.insert(
                    "", tk.END,
                    values=(
                        item_res["ref"],
                        item_res["nome"],
                        item_res["url"],
                        item_res["status_texto"]
                    )
                )

            try:
                self.after(0, _add_row)
            except tk.TclError:
                pass

            time.sleep(0.3)

        def _finalizar():
            self.ref_lote_btn_buscar.configure(state="normal")
            self.ref_lote_progressbar.set(1.0)
            self.ref_lote_status_label.configure(
                text=f"Processamento concluído: {encontrados} de {total} produto(s) encontrado(s)."
            )
            if encontrados > 0:
                self.ref_lote_btn_copiar.configure(state="normal")
            self.status.set(f"Busca em lote concluída ({encontrados}/{total} encontrados).")

        try:
            self.after(0, _finalizar)
        except tk.TclError:
            pass

    def limpar_lote_ref(self):
        self.ref_lote_textbox.delete("1.0", tk.END)
        for item in self.ref_lote_tree.get_children():
            self.ref_lote_tree.delete(item)
        self.ref_lote_progressbar.set(0)
        self.ref_lote_status_label.configure(text="Aguardando início do lote...")
        self.ref_lote_btn_copiar.configure(state="disabled")

    def copiar_urls_lote(self):
        urls = []
        for item in self.ref_lote_tree.get_children():
            vals = self.ref_lote_tree.item(item, "values")
            if vals and len(vals) >= 3:
                url = vals[2]
                if url and url.startswith("http"):
                    urls.append(url)

        if not urls:
            messagebox.showwarning("Copiar URLs", "Nenhuma URL válida encontrada na tabela.")
            return

        texto_final = "\n".join(urls)
        self.clipboard_clear()
        self.clipboard_append(texto_final)
        self.update()
        self.status.set(f"{len(urls)} URL(s) copiada(s) para a área de transferência.")

    def _ajustar_quebras(self, evento=None):
        pass

    def _rolar_galeria(self, evento):
        try:
            if self.current_view_index != 1:
                return
            self.galeria_canvas.yview_scroll(int(-evento.delta / 120), "units")
        except Exception:
            pass

    def _galeria_redimensionada(self, evento):
        self.galeria_canvas.itemconfigure(self.galeria_window, width=evento.width)
        colunas = max(1, min(6, evento.width // 200))
        if colunas != self._galeria_cols:
            self._galeria_cols = colunas
            self._render_galeria()

    def _render_galeria(self):
        for child in self.galeria_frame.winfo_children():
            child.destroy()
        self.thumb_images.clear()

        if not self.galeria_arquivos:
            tk.Label(self.galeria_frame,
                     text="Nenhuma foto carregada ainda.\nColete um produto para ver a galeria aqui.",
                     justify="center", background="#2B2B2B", foreground="#CCCCCC",
                     font=("Segoe UI", 10)).grid(row=0, column=0, padx=24, pady=28, sticky="w")
            return

        cols = max(1, self._galeria_cols or 3)
        for c in range(cols):
            self.galeria_frame.columnconfigure(c, weight=1)

        for i, arq in enumerate(self.galeria_arquivos):
            card = tk.Frame(self.galeria_frame, background="#2B2B2B", padx=8, pady=8)
            card.grid(row=i // cols, column=i % cols, padx=6, pady=6, sticky="nsew")
            try:
                img = Image.open(arq).convert("RGB")
                img.thumbnail((170, 170))
                photo = ImageTk.PhotoImage(img)
                self.thumb_images.append(photo)
                tk.Label(card, image=photo, background="#2B2B2B").pack()
            except Exception:
                tk.Label(card, text="[imagem]", background="#2B2B2B", foreground="#CCCCCC").pack(padx=45, pady=60)
            tk.Label(card, text=arq.stem.split("_")[-1], anchor="center",
                     background="#2B2B2B", foreground="#CCCCCC",
                     font=("Segoe UI", 9)).pack(fill="x", pady=(6, 0))

    def _atualizar_contador_descricao_curta(self, evento=None):
        try:
            texto = self.descricao_curta.get("1.0", tk.END).rstrip("\n")
            total = len(texto)
            self.descricao_curta_contador.configure(text=f"{total} / 2500 caracteres")
            if total > 2500:
                self.descricao_curta_status.configure(
                    text="⚠ Acima do limite da Livelo."
                )
            elif total:
                self.descricao_curta_status.configure(
                    text="✓ Dentro do limite da Livelo."
                )
        except Exception:
            pass

    def copiar_descricao_curta(self):
        texto = self.descricao_curta.get("1.0", tk.END).strip()
        if not texto:
            messagebox.showwarning("Descrição Curta", "Gere a descrição curta primeiro.")
            return
        self.clipboard_clear()
        self.clipboard_append(texto)
        self.update()
        self.status.set("Descrição curta copiada para a área de transferência.")

    def _descricao_base_anatel(self):
        caminho = localizar_base_anatel()
        if not caminho:
            return "Nenhuma base local encontrada. Será baixada automaticamente na primeira consulta."
        idade = idade_dias_arquivo(caminho)
        texto = f"Base atual: {Path(caminho).name}"
        if idade >= 0:
            texto += f" ({int(idade)} dia(s) atrás)"
        return texto

    def selecionar_base_anatel(self):
        caminho = filedialog.askopenfilename(
            title="Selecione a base local da ANATEL",
            filetypes=[
                ("Base ANATEL", "*.csv *.txt *.xlsx *.xls *.zip"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if not caminho:
            return
        salvar_caminho_base_anatel(caminho)
        try:
            carregar_base_anatel(caminho, forcar=True)
            self.anatel_base_status.set(self._descricao_base_anatel())
            self.anatel_status.set("Base carregada. Informe o número de homologação.")
            self.log(f"ANATEL: base local definida em {caminho}")
        except Exception as erro:
            self.anatel_base_status.set("Erro ao carregar a base selecionada.")
            messagebox.showerror("Base ANATEL", str(erro))

    def atualizar_base_anatel_botao(self):
        if not messagebox.askyesno(
            "Atualizar base ANATEL",
            "Isso vai baixar a base oficial mais recente do site da ANATEL "
            "(pode levar alguns minutos). Deseja continuar?",
        ):
            return
        self.botao_anatel_atualizar.configure(state="disabled")
        self.botao_anatel_selecionar.configure(state="disabled")
        self.botao_anatel.configure(state="disabled")
        self.anatel_base_status.set("Baixando base oficial da ANATEL...")
        threading.Thread(target=self._atualizar_base_anatel_thread, daemon=True).start()

    def _atualizar_base_anatel_thread(self):
        try:
            atualizar_base_anatel_oficial(log=self.log)
            self.after(0, lambda: self.anatel_base_status.set(self._descricao_base_anatel()))
            self.log("ANATEL: base oficial atualizada com sucesso.")
        except Exception as erro:
            self.after(0, lambda: self.anatel_base_status.set("Erro ao atualizar a base."))
            self.log(f"ANATEL: erro ao atualizar base — {erro}")
            try:
                self.after(0, lambda: messagebox.showerror("Atualizar base ANATEL", str(erro)))
            except tk.TclError:
                pass
        finally:
            try:
                self.after(0, lambda: self.botao_anatel_atualizar.configure(state="normal"))
                self.after(0, lambda: self.botao_anatel_selecionar.configure(state="normal"))
                self.after(0, lambda: self.botao_anatel.configure(state="normal"))
            except tk.TclError:
                pass

    def _configuracao_ia_atual(self):
        return {
            "model": self.ia_modelo.get().strip() or IA_DEFAULT_MODEL,
            "api_key": self.ia_api_key.get().strip(),
            "endpoint": self.ia_endpoint.get().strip() or IA_DEFAULT_ENDPOINT,
            "google_drive_api_key": getattr(self, "drive_api_key").get().strip() if hasattr(self, "drive_api_key") else "",
            "languagetool_enabled": bool(self.lt_ativado.get()) if hasattr(self, "lt_ativado") else False,
            "languagetool_endpoint": self.lt_endpoint.get().strip() if hasattr(self, "lt_endpoint") else "",
            "languagetool_api_key": self.lt_api_key.get().strip() if hasattr(self, "lt_api_key") else "",
            "languagetool_username": self.lt_username.get().strip() if hasattr(self, "lt_username") else "",
            "prompts": self.ia_config.get("prompts", {}),
        }

    def salvar_configuracao_ia(self):
        self.ia_config = self._configuracao_ia_atual()
        salvar_config_ia(self.ia_config)
        self.status.set("Configurações salvas.")
        messagebox.showinfo("Configuração", "Configurações salvas com sucesso.")

    def _atualizar_lista_prompts(self, selecionado=None):
        opcoes = list(self.ia_presets.keys())
        self.ia_acao.configure(values=opcoes)
        if selecionado and selecionado in opcoes:
            self.ia_acao.set(selecionado)
        elif opcoes:
            self.ia_acao.set(opcoes[0])

    def _salvar_prompts_personalizados(self):
        prompts = {
            k: v for k, v in self.ia_presets.items()
            if k not in IA_PRESETS or v != IA_PRESETS[k]
        }
        self.ia_config["prompts"] = prompts
        salvar_config_ia(self.ia_config)

    def ia_salvar_prompt_como(self):
        conteudo = self.ia_prompt.get("1.0", tk.END).strip()
        if not conteudo:
            messagebox.showwarning("IA", "O prompt está vazio.")
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Salvar prompt")
        dialog.geometry("350x150")
        dialog.resizable(False, False)
        
        self.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() // 2) - 175
        y = self.winfo_rooty() + (self.winfo_height() // 2) - 75
        dialog.geometry(f"+{x}+{y}")
        
        dialog.transient(self)
        dialog.grab_set()

        nome_var = tk.StringVar()

        ctk.CTkLabel(dialog, text="Informe o nome para salvar este prompt:", font=("Segoe UI", 12, "bold")).pack(pady=(20, 10))
        entry = ctk.CTkEntry(dialog, textvariable=nome_var, width=280)
        entry.pack(pady=(0, 15))
        entry.focus()

        def _confirmar(event=None):
            dialog.destroy()
            
        def _cancelar(event=None):
            nome_var.set("")
            dialog.destroy()

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack()
        ctk.CTkButton(btn_frame, text="OK", width=100, command=_confirmar).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Cancelar", width=100, command=_cancelar, fg_color="#D9534F", hover_color="#C9302C").pack(side="left", padx=10)
        
        entry.bind("<Return>", _confirmar)
        entry.bind("<Escape>", _cancelar)

        self.wait_window(dialog)

        nome = nome_var.get().strip()
        if not nome:
            return
        nome = nome.strip()
        if nome in IA_PRESETS:
            messagebox.showwarning("IA", "Esse nome é reservado para um prompt padrão.")
            return
        self.ia_presets[nome] = conteudo
        self._salvar_prompts_personalizados()
        self._atualizar_lista_prompts(nome)
        self.status.set(f"Prompt salvo: {nome}")
        self.log(f"IA: prompt personalizado salvo como '{nome}'.")

    def ia_excluir_prompt(self):
        nome = self.ia_acao.get().strip()
        if not nome:
            return
        if nome in IA_PRESETS:
            messagebox.showwarning("IA", "Não é possível excluir um prompt padrão.")
            return
        if messagebox.askyesno("Confirmar Exclusão", f"Tem certeza que deseja excluir o prompt '{nome}'?"):
            del self.ia_presets[nome]
            self._salvar_prompts_personalizados()
            padrao = list(IA_PRESETS.keys())[0]
            self._atualizar_lista_prompts(padrao)
            self.status.set(f"Prompt excluído: {nome}")
            self.log(f"IA: prompt personalizado '{nome}' excluído.")
            self.ia_prompt.delete("1.0", tk.END)
            self.ia_prompt.insert("1.0", self.ia_presets.get(padrao, ""))

    def ia_atualizar_prompt(self):
        nome = self.ia_acao.get().strip()
        if not nome:
            messagebox.showwarning("IA", "Selecione uma ação/prompt.")
            return
        if nome in IA_PRESETS:
            messagebox.showinfo(
                "IA",
                "Prompts padrão não podem ser alterados diretamente. "
                "Use 'Salvar como novo' para criar a sua versão."
            )
            return
        novo = self.ia_prompt.get("1.0", tk.END).strip()
        if not novo:
            messagebox.showwarning("IA", "O prompt está vazio.")
            return
        self.ia_presets[nome] = novo
        self._salvar_prompts_personalizados()
        self.status.set(f"Prompt atualizado: {nome}")
        self.log(f"IA: prompt personalizado atualizado — '{nome}'.")

    def ia_gerenciar_prompts(self):
        win = ctk.CTkToplevel(self)
        win.title("Gerenciar prompts de IA")
        win.geometry("900x620")
        win.transient(self)
        win.grab_set()

        win.columnconfigure(1, weight=1)
        win.rowconfigure(1, weight=1)

        ctk.CTkLabel(win, text="Prompts salvos", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 4)
        )
        lista = tk.Listbox(win, exportselection=False, background="#151B23", foreground="#E6EDF3", selectbackground="#3B8EEA")
        lista.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=(0, 12))

        ctk.CTkLabel(win, text="Conteúdo do prompt", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=1, sticky="w", padx=6, pady=(12, 4)
        )
        editor = ctk.CTkTextbox(win, font=("Consolas", 11, "bold"))
        editor.grid(row=1, column=1, sticky="nsew", padx=6, pady=(0, 12))

        for nome in self.ia_presets.keys():
            lista.insert(tk.END, nome)

        def carregar(_=None):
            sel = lista.curselection()
            if not sel:
                return
            nome = lista.get(sel[0])
            editor.delete("1.0", tk.END)
            editor.insert("1.0", self.ia_presets.get(nome, ""))

        lista.bind("<<ListboxSelect>>", carregar)

        def salvar_alteracoes():
            sel = lista.curselection()
            if not sel:
                messagebox.showwarning("IA", "Selecione um prompt.", parent=win)
                return
            nome = lista.get(sel[0])
            novo = editor.get("1.0", tk.END).strip()
            if not novo:
                messagebox.showwarning("IA", "O prompt está vazio.", parent=win)
                return
            if nome in IA_PRESETS:
                messagebox.showinfo(
                    "IA",
                    "Prompt padrão não pode ser sobrescrito. "
                    "Crie uma cópia com 'Novo prompt'.",
                    parent=win
                )
                return
            self.ia_presets[nome] = novo
            self._salvar_prompts_personalizados()
            self._atualizar_lista_prompts(nome)
            self.status.set(f"Prompt atualizado: {nome}")

        def novo():
            from tkinter import simpledialog
            nome = simpledialog.askstring("Novo prompt", "Nome do prompt:", parent=win)
            if not nome:
                return
            nome = nome.strip()
            if nome in self.ia_presets:
                messagebox.showwarning("IA", "Esse nome já existe.", parent=win)
                return
            self.ia_presets[nome] = "Digite aqui o seu prompt..."
            self._salvar_prompts_personalizados()
            lista.insert(tk.END, nome)
            lista.selection_clear(0, tk.END)
            lista.selection_set(tk.END)
            carregar()
            self._atualizar_lista_prompts(nome)

        def excluir():
            sel = lista.curselection()
            if not sel:
                return
            nome = lista.get(sel[0])
            if nome in IA_PRESETS:
                messagebox.showinfo(
                    "IA", "Os prompts padrão não podem ser excluídos.", parent=win
                )
                return
            if not messagebox.askyesno(
                "Excluir prompt", f"Excluir '{nome}'?", parent=win
            ):
                return
            self.ia_presets.pop(nome, None)
            self._salvar_prompts_personalizados()
            idx = sel[0]
            lista.delete(idx)
            if lista.size():
                lista.selection_set(min(idx, lista.size()-1))
                carregar()
            self._atualizar_lista_prompts()
            self.status.set(f"Prompt excluído: {nome}")

        def usar():
            sel = lista.curselection()
            if not sel:
                return
            nome = lista.get(sel[0])
            self._atualizar_lista_prompts(nome)
            self.ia_carregar_prompt()
            win.destroy()

        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 12))

        ctk.CTkButton(btns, text="Usar este prompt", command=usar, fg_color="#3B8EEA").pack(side="left", padx=(0, 6))
        ctk.CTkButton(btns, text=" Salvar alterações", image=carregar_icone_ui("salvar", (16, 16)), compound="left", command=salvar_alteracoes).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btns, text=" Novo prompt", image=carregar_icone_ui("novo", (16, 16)), compound="left", command=novo).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btns, text=" Excluir prompt", image=carregar_icone_ui("limpar", (16, 16)), compound="left", command=excluir, fg_color="#E53935", hover_color="#D32F2F").pack(side="left", padx=(0, 6))
        ctk.CTkButton(btns, text="Fechar", command=win.destroy, fg_color="gray").pack(side="right")

    def ia_carregar_prompt(self):
        nome = self.ia_acao.get().strip()
        prompt = self.ia_presets.get(nome, "")
        self.ia_prompt.delete("1.0", tk.END)
        self.ia_prompt.insert("1.0", prompt)
        self.status.set(f"Prompt carregado: {nome}")

    def ia_restaurar_prompt(self):
        nome = self.ia_acao.get().strip()
        if nome in IA_PRESETS:
            self.ia_presets[nome] = IA_PRESETS[nome]
            self.ia_prompt.delete("1.0", tk.END)
            self.ia_prompt.insert("1.0", IA_PRESETS[nome])
            self.status.set(f"Prompt restaurado: {nome}")

    def ia_salvar_preset(self):
        self.ia_salvar_prompt_como()

    def ia_carregar_descricao(self):
        texto = self.output.get("1.0", tk.END).strip()
        if not texto:
            messagebox.showwarning("IA", "A aba Descrição está vazia.")
            return
        self.ia_resultado.delete("1.0", tk.END)
        self.ia_resultado.insert("1.0", texto)
        self._selecionar_view(4)

    def ia_aplicar_descricao(self):
        texto = self.ia_resultado.get("1.0", tk.END).strip()
        if not texto:
            messagebox.showwarning("IA", "Não há resultado de IA para aplicar.")
            return
        self.output.delete("1.0", tk.END)
        self.output.insert("1.0", texto)
        if self.ultima_pasta and self.ultima_pasta.exists():
            try:
                (self.ultima_pasta / "descricao_ia.txt").write_text(texto, encoding="utf-8")
                self.log(f"IA: descrição aplicada e salva em {self.ultima_pasta / 'descricao_ia.txt'}")
            except Exception as erro:
                self.log(f"IA: não foi possível salvar descricao_ia.txt — {erro}")
        self._selecionar_view(3)
        self.status.set("Resultado da IA aplicado à descrição.")

    def ia_copiar_resultado(self):
        texto = self.ia_resultado.get("1.0", tk.END).strip()
        if not texto:
            messagebox.showwarning("IA", "Não há resultado para copiar.")
            return
        self.clipboard_clear()
        self.clipboard_append(texto)
        self.update()
        self.status.set("Resultado da IA copiado.")

    def _reset_checklist(self):
        if not hasattr(self, "checklist_vars"):
            return
        for var in self.checklist_vars.values():
            var.set(False)
        if hasattr(self, "checklist_status"):
            try:
                self.checklist_status.configure(text="Aguardando processamento...")
            except Exception:
                pass

    def _marcar_check(self, chave, valor=True):
        if hasattr(self, "checklist_vars") and chave in self.checklist_vars:
            self.checklist_vars[chave].set(bool(valor))

    def _concluir_checklist(self, sucesso):
        if not hasattr(self, "checklist_status"):
            return
        if sucesso:
            self._marcar_check("final", True)
            try:
                self.checklist_status.configure(
                    text="✓ Descrição aprovada: todos os processos foram concluídos com êxito."
                )
            except Exception:
                pass
        else:
            self._marcar_check("final", False)
            try:
                self.checklist_status.configure(
                    text="⚠ A descrição ainda não foi aprovada em todos os processos."
                )
            except Exception:
                pass

    def _aplicar_filtros_descricao(self, fonte_original, descricao_candidata,
                                   prompt, api_key, model, endpoint):
        resultado = normalizar_estrutura_descricao(descricao_candidata)
        auditoria_ok = False
        lt_ok = False
        validador_ok = False
        validacao_ia = False

        if api_key.strip():
            try:
                self.log("----- TERCEIRO FILTRO | IA AUDITORA -----")
                resultado = auditar_descricao_com_ia(
                    fonte_original,
                    resultado,
                    prompt,
                    api_key,
                    model,
                    endpoint,
                    self.log,
                )
                resultado = restaurar_dois_pontos_atributos(resultado)
                resultado = normalizar_estrutura_descricao(resultado)
                auditoria_ok = bool(resultado.strip())
                self.log("IA auditora: comparação com a fonte concluída.")
            except Exception as erro:
                self.log(f"IA auditora: erro — {erro}")
        else:
            self.log("IA auditora: ignorada porque a API Key não está configurada.")

        lt_enabled = bool(self.lt_ativado.get()) if hasattr(self, "lt_ativado") else False
        lt_endpoint = self.lt_endpoint.get().strip() if hasattr(self, "lt_endpoint") else ""
        lt_api_key = self.lt_api_key.get().strip() if hasattr(self, "lt_api_key") else ""
        lt_username = self.lt_username.get().strip() if hasattr(self, "lt_username") else ""

        if lt_enabled:
            if not lt_endpoint:
                self.log("LanguageTool: ativado, mas nenhum endpoint foi configurado. Etapa pendente.")
            else:
                try:
                    resultado, _ = corrigir_com_languagetool(
                        resultado, lt_endpoint, lt_api_key, lt_username, self.log
                    )
                    resultado = normalizar_estrutura_descricao(resultado)
                    lt_ok = True
                except Exception as erro:
                    self.log(f"LanguageTool: erro — {erro}")
        else:
            self.log("LanguageTool: desativado/configuração não habilitada.")

        validador_ok, erros = validar_descricao_deterministica(
            fonte_original, resultado
        )
        if validador_ok:
            self.log("Validador local: descrição aprovada.")
        else:
            self.log("Validador local: pendências encontradas:")
            for erro in erros[:10]:
                self.log(f"  - {erro}")

        if api_key.strip() and resultado.strip() and auditoria_ok and validador_ok:
            try:
                validacao_ia = self._validar_descricao_com_prompt(
                    resultado, prompt, api_key, model, endpoint
                )
            except Exception as erro:
                self.log(f"Validação semântica final da IA não pôde ser confirmada: {erro}")
                validacao_ia = False

        return resultado.strip(), auditoria_ok, lt_ok, validador_ok, validacao_ia

    def _validar_descricao_com_prompt(self, descricao, prompt, api_key, model, endpoint):
        import json
        contexto = f"""
Você é um validador rigoroso de descrições de produtos.

PROMPT ORIGINAL:
{prompt}

DESCRIÇÃO FINAL:
{descricao}

Não corrija o texto e não invente informações.
Verifique se a descrição final cumpriu as instruções do PROMPT ORIGINAL.

Responda SOMENTE com JSON válido, sem Markdown, neste formato:
{{
  "aprovado": true,
  "criterios": {{
    "estrutura": true,
    "conteudo": true,
    "formatacao": true,
    "nao_inventou": true
  }}
}}

Marque false se houver qualquer descumprimento relevante.
"""
        resposta = chamar_ia(contexto, api_key, model, endpoint, self.log)
        data = json.loads(resposta)
        criterios = data.get("criterios", {})
        aprovado = data.get("aprovado") is True
        obrigatorios = ["estrutura", "conteudo", "formatacao", "nao_inventou"]
        return bool(aprovado and all(criterios.get(item) is True for item in obrigatorios))

    def buscar_descricao_novamente(self):
        url = self.entrada_url.get().strip()
        if not url.startswith("http"):
            messagebox.showwarning(
                "Descrição",
                "Cole primeiro o endereço completo da página da Decathlon."
            )
            return

        self._reset_checklist()
        self._marcar_check("busca", False)
        self._marcar_check("extracao", False)
        self._marcar_check("formatacao", False)
        self._marcar_check("ia", False)
        self._marcar_check("validacao", False)

        self.status.set("Buscando a descrição novamente...")
        threading.Thread(
            target=self._buscar_descricao_novamente_thread,
            args=(url,),
            daemon=True
        ).start()

    def _buscar_descricao_novamente_thread(self, url):
        try:
            self.log("----- BUSCAR DESCRIÇÃO NOVAMENTE -----")
            self.log("Acessando novamente a página da Decathlon...")
            html = baixar_html_fotos(url)
            self._mostrar_html(html)

            formato = self.var_formato.get()
            fonte_original = extract_from_html(html, url, formato)
            if not fonte_original.strip():
                raise RuntimeError("A Decathlon não retornou uma descrição utilizável.")

            api_key = self.ia_api_key.get().strip()
            model = self.ia_modelo.get().strip() or IA_DEFAULT_MODEL
            endpoint = self.ia_endpoint.get().strip() or IA_DEFAULT_ENDPOINT

            fonte_original = traduzir_para_portugues(fonte_original, api_key, model, endpoint, self.log)

            self._marcar_check("busca", True)
            self._marcar_check("extracao", True)
            self._marcar_check("formatacao", True)

            nome_prompt = self.ia_acao.get().strip() or "Padrão Decathlon"
            prompt = self.ia_presets.get(nome_prompt, "")

            resultado = fonte_original
            ia_ok = False
            auditoria_ok = False
            lt_ok = False
            validador_ok = False
            validado = False

            if api_key and prompt:
                self.log(f"Aplicando o prompt de IA: {nome_prompt}...")
                contexto = (
                    f"AÇÃO: {nome_prompt}\n\n"
                    f"PROMPT DA TAREFA:\n{prompt}\n\n"
                    f"CONTEÚDO FONTE DO PRODUTO:\n{fonte_original}\n\n"
                    "Retorne somente o resultado solicitado pelo prompt."
                )
                resultado = chamar_ia(contexto, api_key, model, endpoint, self.log)
                resultado = restaurar_dois_pontos_atributos(resultado)
                resultado = normalizar_estrutura_descricao(resultado)

                if resultado.strip():
                    ia_ok = True
                    self._marcar_check("ia", True)
                    (
                        resultado,
                        auditoria_ok,
                        lt_ok,
                        validador_ok,
                        validado,
                    ) = self._aplicar_filtros_descricao(
                        fonte_original,
                        resultado,
                        prompt,
                        api_key,
                        model,
                        endpoint,
                    )
                    self._marcar_check("auditoria", auditoria_ok)
                    lt_enabled = bool(self.lt_ativado.get()) if hasattr(self, "lt_ativado") else False
                    self._marcar_check("languagetool", lt_ok or not lt_enabled)
                    self._marcar_check("validador", validador_ok)
                    self._marcar_check("validacao", validado)
                else:
                    self.log("IA retornou vazio; mantendo descrição extraída.")
            else:
                self.log("API Key/prompt não configurados; descrição extraída sem etapa de IA.")

            self._mostrar_descricao(resultado)

            referencia = referencia_da_url(url)
            destino = self.pasta_base / referencia
            destino.mkdir(parents=True, exist_ok=True)
            (destino / "descricao.txt").write_text(resultado.strip(), encoding="utf-8")

            lt_enabled = bool(self.lt_ativado.get()) if hasattr(self, "lt_ativado") else False
            pipeline_ok = bool(
                ia_ok and auditoria_ok and validador_ok and validado
                and (lt_ok or not lt_enabled)
            )

            if api_key and resultado.strip() and pipeline_ok:
                try:
                    self.log("Gerando automaticamente a descrição curta para a Livelo...")
                    curta = self._gerar_descricao_curta_com_ia(
                        resultado.strip(), api_key, model, endpoint
                    )
                    if curta:
                        (destino / "descricao_curta_livelo.txt").write_text(
                            curta, encoding="utf-8"
                        )
                        self.after(0, lambda t=curta: (
                            self.descricao_curta.delete("1.0", tk.END),
                            self.descricao_curta.insert("1.0", t),
                            self._atualizar_contador_descricao_curta(),
                            self.descricao_curta_status.configure(
                                text=("✓ Descrição curta gerada dentro do limite da Livelo."
                                      if len(t) <= 2500 else
                                      "⚠ A descrição curta ultrapassou o limite.")
                            )
                        ))
                        self.log(f"Descrição curta Livelo salva ({len(curta)} caracteres).")
                except Exception as erro_curta:
                    self.log(f"ERRO na descrição curta Livelo: {erro_curta}")

            sucesso = bool(
                fonte_original.strip()
                and self.checklist_vars.get("busca").get()
                and self.checklist_vars.get("extracao").get()
                and self.checklist_vars.get("formatacao").get()
                and self.checklist_vars.get("ia").get()
                and self.checklist_vars.get("auditoria").get()
                and self.checklist_vars.get("languagetool").get()
                and self.checklist_vars.get("validador").get()
                and self.checklist_vars.get("validacao").get()
            )

            def finalizar():
                self._concluir_checklist(sucesso)
                self.status.set(
                    "Descrição novamente processada e validada."
                    if sucesso else
                    "Descrição novamente processada. Checklist pendente."
                )
                self._selecionar_view(3)

            self.after(0, finalizar)
            self.log("----- FIM DA NOVA BUSCA -----")

        except Exception as erro:
            self.log(f"ERRO ao buscar descrição novamente: {erro}")
            def falha():
                self._concluir_checklist(False)
                self.status.set("Erro ao buscar descrição novamente.")
                messagebox.showerror(
                    "Descrição",
                    f"Não foi possível buscar a descrição novamente:\n{erro}"
                )
            self.after(0, falha)

    def corrigir_erros_descricao(self):
        fonte_candidata = self.output.get("1.0", tk.END).strip()
        if not fonte_candidata:
            messagebox.showwarning("Correção", "Primeiro extraia uma descrição na aba Descrição.")
            return
        api_key = self.ia_api_key.get().strip()
        if not api_key:
            messagebox.showwarning("Correção", "Informe a API Key na configuração da IA.")
            return

        model = self.ia_modelo.get().strip() or IA_DEFAULT_MODEL
        endpoint = self.ia_endpoint.get().strip() or IA_DEFAULT_ENDPOINT
        nome_prompt = self.ia_acao.get().strip() or "Padrão Decathlon"
        prompt_validacao = self.ia_presets.get(nome_prompt, PROMPT_CORRECAO_ERROS)

        fonte_original = fonte_candidata
        try:
            html = self.texto_html.get("1.0", tk.END).strip()
            url = self.entrada_url.get().strip()
            if html and url.startswith("http"):
                fonte_extraida = extract_from_html(html, url, self.var_formato.get())
                if fonte_extraida.strip():
                    fonte_original = fonte_extraida
        except Exception:
            pass

        contexto = (
            "AÇÃO: Corrigir erros da descrição atual\n\n"
            f"PROMPT DE CORREÇÃO:\n{PROMPT_CORRECAO_ERROS}\n\n"
            f"DESCRIÇÃO ATUAL:\n{fonte_candidata}\n\n"
            "Retorne somente a descrição corrigida."
        )
        self.ia_resultado.delete("1.0", tk.END)
        self.ia_resultado.insert("1.0", "Corrigindo erros com a IA...\n")
        self._selecionar_view(4)
        self._reset_checklist()

        def worker():
            try:
                self.log("----- CORREÇÃO DE ERROS + TERCEIRO FILTRO -----")
                resultado = chamar_ia(contexto, api_key, model, endpoint, self.log)
                resultado = restaurar_dois_pontos_atributos(resultado)
                resultado = normalizar_estrutura_descricao(resultado)
                if not resultado.strip():
                    raise RuntimeError("A IA retornou uma descrição vazia.")

                self._marcar_check("busca", True)
                self._marcar_check("extracao", True)
                self._marcar_check("formatacao", True)
                self._marcar_check("ia", True)

                (
                    resultado,
                    auditoria_ok,
                    lt_ok,
                    validador_ok,
                    validado,
                ) = self._aplicar_filtros_descricao(
                    fonte_original,
                    resultado,
                    prompt_validacao,
                    api_key,
                    model,
                    endpoint,
                )

                self._marcar_check("auditoria", auditoria_ok)
                lt_enabled = bool(self.lt_ativado.get()) if hasattr(self, "lt_ativado") else False
                self._marcar_check("languagetool", lt_ok or not lt_enabled)
                self._marcar_check("validador", validador_ok)
                self._marcar_check("validacao", validado)

                sucesso = bool(
                    auditoria_ok and validador_ok and validado
                    and (lt_ok or not lt_enabled)
                )

                def finalizar():
                    self.ia_resultado.delete("1.0", tk.END)
                    self.ia_resultado.insert("1.0", resultado)
                    self._concluir_checklist(sucesso)
                    self.status.set(
                        "Correção concluída e validada." if sucesso
                        else "Correção concluída, mas o checklist ficou pendente."
                    )
                self.after(0, finalizar)
                self.log("----- FIM DA CORREÇÃO -----")
            except Exception as erro:
                self.log(f"ERRO na correção de erros: {erro}")
                self.after(0, lambda: messagebox.showerror(
                    "Correção", f"Não foi possível corrigir a descrição:\n{erro}"
                ))
        threading.Thread(target=worker, daemon=True).start()

    def iniciar_ia(self):
        fonte = self.output.get("1.0", tk.END).strip()
        if not fonte:
            messagebox.showwarning("IA", "Primeiro extraia uma descrição ou cole o conteúdo na aba Descrição.")
            return
        prompt = self.ia_prompt.get("1.0", tk.END).strip()
        if not prompt:
            messagebox.showwarning("IA", "O prompt está vazio.")
            return
        api_key = self.ia_api_key.get().strip()
        if not api_key:
            messagebox.showwarning("IA", "Informe a API Key na área de configuração da IA.")
            return
        model = self.ia_modelo.get().strip() or IA_DEFAULT_MODEL
        endpoint = self.ia_endpoint.get().strip() or IA_DEFAULT_ENDPOINT
        acao = self.ia_acao.get().strip()
        contexto = (
            f"AÇÃO: {acao}\n\n"
            f"PROMPT DA TAREFA:\n{prompt}\n\n"
            f"CONTEÚDO FONTE DO PRODUTO:\n{fonte}\n\n"
            "Retorne somente o resultado solicitado pelo prompt."
        )
        self.ia_resultado.delete("1.0", tk.END)
        self.ia_resultado.insert("1.0", "Processando com a IA...\n")
        self._selecionar_view(4)
        threading.Thread(
            target=self._ia_thread,
            args=(contexto, api_key, model, endpoint),
            daemon=True
        ).start()

    def _ia_thread(self, contexto, api_key, model, endpoint):
        try:
            texto = chamar_ia(contexto, api_key, model, endpoint, self.log)
            def _set():
                self.ia_resultado.delete("1.0", tk.END)
                self.ia_resultado.insert("1.0", texto)
                self.status.set("IA: cadastro processado com sucesso.")
            self.after(0, _set)
            self.log("IA: resultado recebido.")
        except Exception as erro:
            def _err():
                self.ia_resultado.delete("1.0", tk.END)
                self.ia_resultado.insert("1.0", f"ERRO NA IA:\n{erro}")
                self.status.set("IA: erro ao processar.")
            try: self.after(0, _err)
            except tk.TclError: pass
            self.log(f"IA: erro — {erro}")

    def _gerar_descricao_curta_com_ia(self, fonte, api_key, model, endpoint):
        contexto = (
            "AÇÃO: Gerar descrição curta para Livelo\n\n"
            f"PROMPT DA DESCRIÇÃO CURTA:\n{PROMPT_DESCRICAO_CURTA_LIVELO}\n\n"
            f"DESCRIÇÃO COMPLETA JÁ REVISADA:\n{fonte}\n\n"
            "Retorne somente a descrição curta final."
        )
        resultado = chamar_ia(contexto, api_key, model, endpoint, self.log).strip()

        if len(resultado) > 2500:
            self.log(f"Descrição curta excedeu 2500 caracteres ({len(resultado)}). Compactando novamente...")
            contexto_compacto = (
                "Reduza o texto abaixo para NO MÁXIMO 2500 caracteres, contando espaços. "
                "Preserve apenas as informações essenciais e todos os dados técnicos importantes. "
                "Não invente informações. Retorne somente o texto final.\n\n"
                f"TEXTO A COMPACTAR:\n{resultado}"
            )
            resultado = chamar_ia(
                contexto_compacto, api_key, model, endpoint, self.log
            ).strip()

        if len(resultado) > 2500:
            self.log("A IA ainda excedeu o limite. Aplicando limite local de segurança de 2500 caracteres.")
            resultado = resultado[:2500].rstrip()

        return resultado

    def gerar_descricao_curta(self):
        fonte = self.output.get("1.0", tk.END).strip()
        if not fonte:
            messagebox.showwarning(
                "Descrição Curta",
                "Primeiro extraia ou gere a descrição completa na aba Descrição."
            )
            return
        api_key = self.ia_api_key.get().strip()
        if not api_key:
            messagebox.showwarning(
                "Descrição Curta",
                "Informe a API Key na configuração da IA."
            )
            return
        model = self.ia_modelo.get().strip() or IA_DEFAULT_MODEL
        endpoint = self.ia_endpoint.get().strip() or IA_DEFAULT_ENDPOINT

        self.descricao_curta.delete("1.0", tk.END)
        self.descricao_curta.insert("1.0", "Gerando descrição curta...\n")
        self.descricao_curta_status.configure(text="Processando com a IA...")

        threading.Thread(
            target=self._gerar_descricao_curta_thread,
            args=(fonte, api_key, model, endpoint),
            daemon=True
        ).start()

    def _gerar_descricao_curta_thread(self, fonte, api_key, model, endpoint):
        try:
            self.log("----- DESCRIÇÃO CURTA LIVELO -----")
            resultado = self._gerar_descricao_curta_com_ia(
                fonte, api_key, model, endpoint
            )
            if not resultado:
                raise RuntimeError("A IA retornou uma descrição curta vazia.")

            total = len(resultado)
            def finalizar():
                self.descricao_curta.delete("1.0", tk.END)
                self.descricao_curta.insert("1.0", resultado)
                self._atualizar_contador_descricao_curta()
                if total <= 2500:
                    self.descricao_curta_status.configure(
                        text="✓ Descrição curta gerada dentro do limite da Livelo."
                    )
                    self.status.set("Descrição curta Livelo gerada com sucesso.")
                else:
                    self.descricao_curta_status.configure(
                        text="⚠ A descrição curta ultrapassou o limite."
                    )
                    self.status.set("Descrição curta gerada com alerta de limite.")
            self.after(0, finalizar)

            referencia = getattr(self, "referencia_atual", "produto")
            destino = self.pasta_base / referencia
            destino.mkdir(parents=True, exist_ok=True)
            (destino / "descricao_curta_livelo.txt").write_text(
                resultado, encoding="utf-8"
            )
            self.log(f"Descrição curta salva em: {destino / 'descricao_curta_livelo.txt'} ({total} caracteres).")
            self.log("----- FIM DA DESCRIÇÃO CURTA LIVELO -----")
        except Exception as erro:
            erro_str = str(erro).lower()
            self.log(f"ERRO na descrição curta Livelo: {erro}")
            if "quota" in erro_str or "credit" in erro_str or "429" in erro_str:
                self._mostrar_popup_aviso(
                    "IA Sem Crédito", 
                    "Sua chave de API da IA está sem créditos disponíveis!\n\nA descrição curta não pôde ser gerada."
                )
            try:
                self.after(0, lambda err=erro: self.descricao_curta_status.configure(
                    text=f"⚠ Erro: {err}"
                ))
            except tk.TclError:
                pass

    def colar_anatel(self):
        try:
            texto = self.clipboard_get()
        except Exception:
            texto = ""
        numero = normalizar_homologacao_anatel(texto)
        if not numero:
            messagebox.showwarning("ANATEL", "Não encontrei um número de homologação válido na área de transferência.")
            return
        self.entrada_anatel.delete(0, tk.END)
        self.entrada_anatel.insert(0, numero)

    def _mostrar_resultado_anatel(self, resultado):
        def _set():
            for w in self.anatel_container.winfo_children(): w.destroy()
            if resultado.get("encontrado"):
                self.anatel_status.set("HOMOLOGAÇÃO CONFIRMADA NA BASE ANATEL")
                for i, r in enumerate(resultado["registros"]):
                    frame_reg = ctk.CTkFrame(self.anatel_container, fg_color=("#e0e0e0", "#2b2b2b"), corner_radius=8)
                    frame_reg.pack(fill="x", pady=4, padx=4)
                    if len(resultado["registros"]) > 1:
                        ctk.CTkLabel(frame_reg, text=f"Registro {i+1}", font=("Segoe UI", 11, "bold"), text_color="#1E90FF").pack(anchor="w", padx=10, pady=(5, 0))
                    for label_text, valor in [
                        ("Número de Homologação", r.get("Numero", "")),
                        ("Fabricante", r.get("Fabricante", "")),
                        ("Modelo", r.get("Modelo", "")),
                        ("País do Fabricante", r.get("Pais", ""))
                    ]:
                        row = ctk.CTkFrame(frame_reg, fg_color="transparent")
                        row.pack(fill="x", padx=10, pady=2)
                        lbl = ctk.CTkLabel(row, text=f"{label_text}:", font=("Segoe UI", 11, "bold"), width=150, anchor="w")
                        lbl.pack(side="left")
                        val = ctk.CTkEntry(row, font=("Segoe UI", 12))
                        val.pack(side="left", fill="x", expand=True)
                        val.insert(0, valor)
                        val.configure(state="readonly")
                    ctk.CTkFrame(frame_reg, fg_color="transparent", height=5).pack()
            else:
                self.anatel_status.set("HOMOLOGAÇÃO NÃO ENCONTRADA NA BASE ANATEL")
                ctk.CTkLabel(self.anatel_container, text=f"Número consultado: {resultado.get('numero', '')}\n\nNenhum registro correspondente foi encontrado na base consultada.", font=("Segoe UI", 12), text_color="#ff5555", justify="left").pack(anchor="w", pady=10, padx=5)

            txt_tempo = []
            if resultado.get("tempo_download"): txt_tempo.append(f"Tempo de atualização/download da base: {resultado['tempo_download']}")
            if resultado.get("tempo_busca"): txt_tempo.append(f"Tempo da busca: {resultado['tempo_busca']}")
            if txt_tempo:
                ctk.CTkLabel(self.anatel_container, text="\n".join(txt_tempo), font=("Segoe UI", 10), text_color="gray", justify="left").pack(anchor="w", pady=(10, 0), padx=5)
        try: self.after(0, _set)
        except tk.TclError: pass

    def iniciar_anatel(self):
        numero = normalizar_homologacao_anatel(self.entrada_anatel.get())
        if not numero:
            numero = localizar_numero_anatel_html(self.texto_html.get("1.0", tk.END))
            if numero:
                self.entrada_anatel.delete(0, tk.END)
                self.entrada_anatel.insert(0, numero)
        if not numero:
            messagebox.showwarning("ANATEL", "Informe o número de homologação ANATEL.")
            return
        self.botao_anatel.configure(state="disabled")
        self.anatel_status.set("Consultando a base ANATEL...")
        for w in self.anatel_container.winfo_children(): w.destroy()
        ctk.CTkLabel(self.anatel_container, text="Consultando...", font=("Segoe UI", 12)).pack(anchor="w", pady=10, padx=5)
        threading.Thread(target=self._consultar_anatel_thread, args=(numero,), daemon=True).start()

    def _consultar_anatel_thread(self, numero):
        try:
            resultado = consultar_anatel(numero, self.log)
            self._mostrar_resultado_anatel(resultado)
            if resultado.get("encontrado"):
                self._status("Homologação ANATEL confirmada.")
                self.log(f"ANATEL: homologação {resultado['numero']} confirmada ({len(resultado['registros'])} registro(s)).")
            else:
                self._status("Homologação ANATEL não encontrada.")
                self.log(f"ANATEL: homologação {resultado['numero']} não encontrada na base.")
        except Exception as erro:
            self.anatel_status.set("ERRO NA CONSULTA ANATEL")
            self.log(f"ANATEL: erro — {erro}")
            try:
                self.after(0, lambda: messagebox.showerror("Consulta ANATEL", str(erro)))
            except tk.TclError:
                pass
        finally:
            try: self.after(0, lambda: self.botao_anatel.configure(state="normal"))
            except tk.TclError: pass

    def _alternar_personalizado(self, escolha=None):
        if self.combo_tamanho.get() == "Personalizado...":
            self.frame_personalizado.grid()
        else:
            self.frame_personalizado.grid_remove()

    def _tamanho_escolhido(self):
        escolha = self.combo_tamanho.get()
        if escolha == "Personalizado...":
            try: return int(self.campo_largura.get()), int(self.campo_altura.get())
            except ValueError: return 1000, 1000
        largura, altura = escolha.split("x")
        return int(largura), int(altura)

    def log(self, texto):
        def _append():
            for widget in (getattr(self, "saida", None), getattr(self, "saida_full", None)):
                if widget is not None:
                    try:
                        widget.configure(state="normal")
                        widget.insert("end", texto + "\n")
                        widget.see("end")
                        widget.configure(state="disabled")
                    except Exception:
                        pass
        try: self.after(0, _append)
        except tk.TclError: pass

    def escolher_pasta(self):
        escolhida = filedialog.askdirectory(initialdir=str(self.pasta_base))
        if escolhida:
            self.pasta_base = Path(escolhida)
            self.rotulo_pasta.configure(text=str(self.pasta_base))

    def abrir(self):
        if self.ultima_pasta and self.ultima_pasta.exists(): abrir_pasta(self.ultima_pasta)

    def limpar_tudo(self):
        self.entrada_url.delete(0, tk.END)
        self.entrada_anatel.delete(0, tk.END)
        self.anatel_status.set("Aguardando número de homologação.")
        for w in self.anatel_container.winfo_children(): w.destroy()
        self.texto_html.delete("1.0", tk.END)
        self.output.delete("1.0", tk.END)
        self.saida.configure(state="normal"); self.saida.delete("1.0", tk.END); self.saida.configure(state="disabled")
        if hasattr(self, "saida_full"):
            self.saida_full.configure(state="normal"); self.saida_full.delete("1.0", tk.END); self.saida_full.configure(state="disabled")
        self.combo_tamanho.set("1000x1000")
        self.campo_largura.delete(0, tk.END); self.campo_largura.insert(0, "1000")
        self.campo_altura.delete(0, tk.END); self.campo_altura.insert(0, "1000")
        self._alternar_personalizado()
        self.info_ref.configure(text="—"); self.info_nome.configure(text="—"); self.info_marca.configure(text="—"); self.info_categoria.configure(text="—")
        self.galeria_arquivos = []
        self._render_galeria()
        self.ultima_pasta = None; self.referencia_atual = ""
        self.botao_pasta.configure(state="disabled")
        self.status.set("Tudo limpo. Pronto para o próximo produto.")
        self.entrada_url.focus_set()

    def copiar_descricao(self):
        text = self.output.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Atenção", "Gere uma descrição primeiro."); return
        self.clipboard_clear(); self.clipboard_append(text); self.update()
        self.status.set("Descrição copiada para a área de transferência.")

    def _iniciar_fotos(self):
        """Coleta apenas fotos (ação dedicada do botão na view Coleta)."""
        self.var_fotos.set(True)
        self.var_descricao.set(False)
        self.iniciar()

    def _iniciar_descricao(self):
        """Gera apenas a descrição (ação dedicada do botão na view Descrição)."""
        self.var_fotos.set(False)
        self.var_descricao.set(True)
        self.iniciar()

    def iniciar(self):
        self._reset_checklist()
        url = self.entrada_url.get().strip()
        if not url.startswith("http"):
            messagebox.showwarning("URL inválida", "Cole o endereço completo da página."); return
        # Se nenhuma var foi definida (chamada direta do header), fazer ambos
        if not self.var_fotos.get() and not self.var_descricao.get():
            self.var_fotos.set(True)
            self.var_descricao.set(True)
        self.botao_pasta.configure(state="disabled")
        self.status.set("Coletando produto...")
        html_manual = self.texto_html.get("1.0", "end").strip()
        largura, altura = self._tamanho_escolhido()
        ia_api_key = self.ia_api_key.get().strip()
        ia_model = self.ia_modelo.get().strip() or IA_DEFAULT_MODEL
        ia_endpoint = self.ia_endpoint.get().strip() or IA_DEFAULT_ENDPOINT
        nome_prompt = self.ia_acao.get().strip() or "Template Decathlon - Estrutura Automática"
        ia_prompt = self.ia_presets.get(
            nome_prompt,
            self.ia_presets.get(
                "Template Decathlon - Estrutura Automática",
                IA_PRESETS["Template Decathlon - Estrutura Automática"]
            )
        )
        threading.Thread(
            target=self.trabalhar,
            args=(url, html_manual or None, largura, altura, self.var_fotos.get(), self.var_descricao.get(),
                  ia_api_key, ia_model, ia_endpoint, ia_prompt),
            daemon=True
        ).start()

    def _mostrar_descricao(self, texto):
        def _set():
            self.output.delete("1.0", tk.END); self.output.insert("1.0", texto)
            self._selecionar_view(2)
        try: self.after(0, _set)
        except tk.TclError: pass

    def _mostrar_popup_aviso(self, titulo, mensagem):
        def _show():
            popup = ctk.CTkToplevel(self)
            popup.title(titulo)
            popup.geometry("450x200")
            popup.attributes("-topmost", True)
            popup.grab_set()
            popup.update_idletasks()
            x = (self.winfo_screenwidth() - 450) // 2
            y = (self.winfo_screenheight() - 200) // 2
            popup.geometry(f"+{x}+{y}")
            
            lbl = ctk.CTkLabel(popup, text=mensagem, font=("Segoe UI", 14), wraplength=400)
            lbl.pack(expand=True, padx=20, pady=20)
            btn = ctk.CTkButton(popup, text="OK", command=popup.destroy, width=120)
            btn.pack(pady=(0, 20))
        try: self.after(0, _show)
        except tk.TclError: pass

    def _mostrar_html(self, html):
        def _set():
            self.texto_html.delete("1.0", tk.END); self.texto_html.insert("1.0", html)
        try: self.after(0, _set)
        except tk.TclError: pass

    def _mostrar_info(self, html, referencia):
        nome = marca = categoria = "—"
        try:
            soup = BeautifulSoup(html, "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            nome = title.replace(" | Decathlon", "").strip() or "—"
            for tag in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(tag.string or tag.get_text())
                    items = data if isinstance(data, list) else [data]
                    for d in items:
                        if isinstance(d, dict):
                            prod = d.get("@graph", [d])
                            if isinstance(prod, list):
                                for x in prod:
                                    if isinstance(x, dict) and x.get("@type") == "Product":
                                        nome = x.get("name") or nome
                                        br = x.get("brand")
                                        marca = br.get("name") if isinstance(br, dict) else (br or marca)
                                        cat = x.get("category")
                                        categoria = cat or categoria
                except Exception:
                    continue
        except Exception:
            pass
        def _set():
            self.info_ref.configure(text=referencia); self.info_nome.configure(text=nome); self.info_marca.configure(text=marca); self.info_categoria.configure(text=categoria)
        try: self.after(0, _set)
        except tk.TclError: pass

    def _mostrar_galeria(self, pasta):
        arquivos = sorted(pasta.glob(f"{self.referencia_atual}_*.jpg"))

        def _set():
            self.galeria_arquivos = arquivos
            self._render_galeria()
            self._selecionar_view(0)

        try: self.after(0, _set)
        except tk.TclError: pass

    def _status(self, texto):
        try: self.after(0, lambda: self.status.set(texto))
        except tk.TclError: pass

    def _pasta_pronta(self, destino):
        def _set(): self.ultima_pasta = destino; self.botao_pasta.configure(state="normal")
        try: self.after(0, _set)
        except tk.TclError: pass

    def trabalhar(self, url, html_manual, largura, altura, fazer_fotos, fazer_descricao,
                  ia_api_key="", ia_model="", ia_endpoint="", ia_prompt=""):
        try:
            referencia = referencia_da_url(url)
            self.referencia_atual = referencia
            self.log(""); self.log(f"========== DECATHLON | PRODUTO {referencia} ==========")

            if html_manual:
                html = html_manual
                self.log("Usando código-fonte colado manualmente.")
            else:
                self.log("Acessando a página da Decathlon...")
                html = baixar_html_fotos(url)

            self._mostrar_html(html)

            numero_anatel = localizar_numero_anatel_html(html)
            if numero_anatel:
                def _fill_anatel():
                    self.entrada_anatel.delete(0, tk.END)
                    self.entrada_anatel.insert(0, numero_anatel)
                    self.anatel_status.set("Número ANATEL identificado. Clique em Consultar e confirmar.")
                try: self.after(0, _fill_anatel)
                except tk.TclError: pass

            formato = self.var_formato.get()
            self._mostrar_info(html, referencia)
            destino = self.pasta_base / referencia

            if fazer_fotos:
                try:
                    self.log("----- FOTOS -----")
                    urls = coletar(html, referencia, url, largura, altura, self.log)
                    if not urls:
                        self.log("Nenhuma imagem reconhecida no código-fonte.")
                    else:
                        self.log(f"Encontradas {len(urls)} imagens na galeria.")
                        formato_img = self.var_formato_img.get()
                        total = salvar(urls, destino, referencia, largura, altura, formato_img, self.log)
                        self._pasta_pronta(destino); self._mostrar_galeria(destino)
                        self.log(f"Fotos salvas com sucesso (formato {formato_img}): {total} arquivo(s).")
                except Exception as erro:
                    self.log(f"ERRO nas fotos: {erro}")

            if fazer_descricao:
                try:
                    nome_prompt = "Padrão Decathlon"
                    self.log("----- DESCRIÇÃO -----")
                    fonte_original = extract_from_html(html, url, formato)
                    fonte_original = traduzir_para_portugues(
                        fonte_original, ia_api_key, ia_model, ia_endpoint, self.log
                    )
                    descricao = fonte_original
                    ia_ok = False
                    auditoria_ok = False
                    lt_ok = False
                    validador_ok = False
                    validado = False

                    if fonte_original.strip():
                        self._marcar_check("busca", True)
                        self._marcar_check("extracao", True)
                        self._marcar_check("formatacao", True)

                    if ia_api_key:
                        try:
                            self.log(f"Aplicando segundo filtro da IA ({nome_prompt})...")
                            contexto = (
                                "AÇÃO: Segundo filtro de revisão da descrição\n\n"
                                f"PROMPT DA TAREFA:\n{ia_prompt}\n\n"
                                f"CONTEÚDO FONTE DO PRODUTO:\n{fonte_original}\n\n"
                                "Retorne somente o resultado solicitado pelo prompt."
                            )
                            resultado_ia = chamar_ia(
                                contexto, ia_api_key, ia_model, ia_endpoint, self.log
                            )
                            resultado_ia = restaurar_dois_pontos_atributos(resultado_ia)
                            resultado_ia = normalizar_estrutura_descricao(resultado_ia)
                            if resultado_ia.strip():
                                descricao = resultado_ia.strip()
                                ia_ok = True
                                self._marcar_check("ia", True)
                                self.log("Descrição formatada pela primeira IA com sucesso.")

                                (
                                    descricao,
                                    auditoria_ok,
                                    lt_ok,
                                    validador_ok,
                                    validado,
                                ) = self._aplicar_filtros_descricao(
                                    fonte_original,
                                    descricao,
                                    ia_prompt,
                                    ia_api_key,
                                    ia_model,
                                    ia_endpoint,
                                )

                                self._marcar_check("auditoria", auditoria_ok)
                                lt_enabled = bool(self.lt_ativado.get()) if hasattr(self, "lt_ativado") else False
                                self._marcar_check("languagetool", lt_ok or not lt_enabled)
                                self._marcar_check("validador", validador_ok)
                                self._marcar_check("validacao", validado)
                            else:
                                self.log("IA retornou vazio; mantendo a descrição bruta.")
                        except Exception as erro_ia:
                            erro_str = str(erro_ia).lower()
                            self.log(f"ERRO na formatação/auditoria por IA (mantendo descrição bruta): {erro_ia}")
                            if "quota" in erro_str or "credit" in erro_str or "429" in erro_str:
                                self._mostrar_popup_aviso(
                                    "IA Sem Crédito", 
                                    "Sua chave de API da IA está sem créditos disponíveis!\n\nA descrição foi extraída normalmente com os dados originais do produto."
                                )
                    else:
                        self.log("Chave da API de IA não configurada; descrição sem os filtros de IA.")

                    self._mostrar_descricao(descricao)
                    destino.mkdir(parents=True, exist_ok=True)
                    arquivo_desc = destino / "descricao.txt"
                    arquivo_desc.write_text(descricao, encoding="utf-8")
                    self.log(f"Descrição final salva em: {arquivo_desc}")

                    lt_enabled = bool(self.lt_ativado.get()) if hasattr(self, "lt_ativado") else False
                    lt_etapa_ok = lt_ok or not lt_enabled
                    pipeline_ok = bool(
                        ia_ok and auditoria_ok and validador_ok and validado and lt_etapa_ok
                    )

                    if ia_api_key and descricao.strip() and pipeline_ok:
                        try:
                            self.log("Gerando automaticamente a descrição curta para a Livelo...")
                            descricao_curta = self._gerar_descricao_curta_com_ia(
                                descricao, ia_api_key, ia_model, ia_endpoint
                            )
                            if descricao_curta:
                                arquivo_curta = destino / "descricao_curta_livelo.txt"
                                arquivo_curta.write_text(
                                    descricao_curta, encoding="utf-8"
                                )
                                self.after(0, lambda t=descricao_curta: (
                                    self.descricao_curta.delete("1.0", tk.END),
                                    self.descricao_curta.insert("1.0", t),
                                    self._atualizar_contador_descricao_curta(),
                                    self.descricao_curta_status.configure(
                                        text=("✓ Descrição curta gerada dentro do limite da Livelo."
                                              if len(t) <= 2500 else
                                              "⚠ A descrição curta ultrapassou o limite.")
                                    )
                                ))
                                self.log(
                                    f"Descrição curta Livelo salva em: {arquivo_curta} ({len(descricao_curta)} caracteres)."
                                )
                            else:
                                self.log("Descrição curta Livelo retornou vazia.")
                        except Exception as erro_curta:
                            self.log(f"ERRO na geração automática da descrição curta: {erro_curta}")
                    else:
                        self.log(
                            "Descrição curta Livelo não gerada: a descrição completa ainda não passou por todos os filtros."
                        )

                    def _final_check():
                        self._concluir_checklist(pipeline_ok)
                    try:
                        self.after(0, _final_check)
                    except tk.TclError:
                        pass

                except Exception as erro:
                    self.log(f"ERRO na descrição: {erro}")

            self._status(f"Processo concluído — referência {referencia}")
            self.log("========== CONCLUÍDO ==========")
        except Exception as erro:
            self.log(f"ERRO GERAL: {erro}"); self._status("Erro na coleta.")
        finally:
            pass



    def _montar_view_planilha(self, parent):
        parent.grid_rowconfigure(0, weight=0)
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(parent, corner_radius=12)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        top_bar = ctk.CTkFrame(hdr, fg_color="transparent")
        top_bar.pack(fill="x", padx=16, pady=(12, 12))

        ctk.CTkLabel(top_bar, text="Fotos via Planilha", font=("Segoe UI", 15, "bold")).pack(side="left")
        
        self.btn_anexar_planilha = ctk.CTkButton(top_bar, text="Anexar", image=carregar_icone_ui("pasta", (16, 16)), compound="left", fg_color="#303030", hover_color="#404040", width=100, command=self._anexar_planilha)
        self.btn_anexar_planilha.pack(side="left", padx=(20, 10))

        self.lbl_planilha = ctk.CTkLabel(top_bar, text="Nenhuma planilha", font=("Segoe UI", 11), text_color="gray60")
        self.lbl_planilha.pack(side="left")

        self.dropdown_coluna = ctk.CTkOptionMenu(top_bar, values=["- Coluna -"], width=200, dynamic_resizing=False)
        self.dropdown_coluna.pack(side="right")
        ctk.CTkLabel(top_bar, text="Coluna Referência (EAN/SKU):", font=("Segoe UI", 11, "bold")).pack(side="right", padx=(0, 10))

        actions_container = ctk.CTkFrame(hdr, fg_color="transparent")
        actions_container.pack(fill="x", padx=16, pady=(0, 16))
        
        frame_unico = ctk.CTkFrame(actions_container, corner_radius=8, fg_color="#1E1E1E", border_width=1, border_color="#303030")
        frame_unico.pack(side="left", fill="both", expand=True, padx=(0, 4))
        ctk.CTkLabel(frame_unico, text="Apenas 1 Produto", font=("Segoe UI", 12, "bold")).pack(pady=(8, 0))
        
        row_unico = ctk.CTkFrame(frame_unico, fg_color="transparent")
        row_unico.pack(fill="x", padx=10, pady=(8, 12))
        self.entrada_ean_planilha = ctk.CTkEntry(row_unico, placeholder_text="Digite o valor...", width=110)
        self.entrada_ean_planilha.pack(side="left", padx=(0, 6), fill="x", expand=True)
        self.entrada_ean_planilha.bind("<Return>", lambda e: self._buscar_ean_planilha())
        self.btn_buscar_planilha = ctk.CTkButton(row_unico, text="Baixar Único", image=carregar_icone_branco("coleta", (16, 16)), compound="left", fg_color="#3B8EEA", hover_color="#57A0F0", width=90, command=self._buscar_ean_planilha)
        self.btn_buscar_planilha.pack(side="left")

        frame_lote = ctk.CTkFrame(actions_container, corner_radius=8, fg_color="#1E1E1E", border_width=1, border_color="#303030")
        frame_lote.pack(side="left", fill="both", expand=True, padx=(4, 4))
        ctk.CTkLabel(frame_lote, text="Múltiplos Produtos", font=("Segoe UI", 12, "bold"), text_color="#107C41").pack(pady=(8, 0))
        
        row_lote = ctk.CTkFrame(frame_lote, fg_color="transparent")
        row_lote.pack(fill="x", padx=10, pady=(8, 12))
        self.entrada_lote = ctk.CTkTextbox(row_lote, height=28, fg_color="#2A2A2A", border_width=1, border_color="#3A3A3A")
        self.entrada_lote.insert("1.0", "Cole...")
        self.entrada_lote.bind("<FocusIn>", lambda e: self.entrada_lote.delete("1.0", "end") if self.entrada_lote.get("1.0", "end-1c") == "Cole..." else None)
        self.entrada_lote.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.btn_baixar_todos = ctk.CTkButton(row_lote, text="Baixar Lote", image=carregar_icone_branco("coleta", (16, 16)), compound="left", fg_color="#107C41", hover_color="#185C37", font=("Segoe UI", 11, "bold"), width=90, command=self._baixar_todos_planilha)
        self.btn_baixar_todos.pack(side="left")

        frame_drive = ctk.CTkFrame(actions_container, corner_radius=8, fg_color="#1E1E1E", border_width=1, border_color="#303030")
        frame_drive.pack(side="left", fill="both", expand=True, padx=(4, 0))
        ctk.CTkLabel(frame_drive, text="Google Drive", font=("Segoe UI", 12, "bold"), text_color="#F4B400").pack(pady=(8, 0))
        
        row_drive = ctk.CTkFrame(frame_drive, fg_color="transparent")
        row_drive.pack(fill="x", expand=True, padx=10, pady=(8, 12))
        self.btn_drive = ctk.CTkButton(row_drive, text=" Acessar Drive", image=carregar_icone_branco("coleta", (16, 16)), compound="left", fg_color="#F4B400", hover_color="#C69300", font=("Segoe UI", 11, "bold"), command=self._abrir_modal_drive)
        self.btn_drive.pack(expand=True, fill="both")

        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        c3_fotos = ctk.CTkFrame(scroll, corner_radius=12)
        c3_fotos.grid(row=0, column=0, sticky="nsew", pady=(0, 12), padx=4)
        c3_fotos.grid_columnconfigure(0, weight=1)
        c3_fotos.grid_rowconfigure(1, weight=1)
        
        header = ctk.CTkFrame(c3_fotos, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        ctk.CTkLabel(header, text="Galeria de Imagens (Planilha)", font=("Segoe UI", 14, "bold")).pack(side="left")
        
        btn_abrir = ctk.CTkButton(header, text=" Abrir Pasta no Explorer", image=carregar_icone_ui("pasta", (16, 16)), compound="left", command=lambda: abrir_pasta(self.pasta_base))
        btn_abrir.pack(side="right", padx=13, pady=12)
        
        self.galeria_frame_planilha = ctk.CTkScrollableFrame(c3_fotos, height=360, fg_color="#1E1E1E", corner_radius=8)
        self.galeria_frame_planilha.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        
        self.galeria_arquivos_planilha = []
        self._render_galeria_planilha()

    def _render_galeria_planilha(self):
        for child in self.galeria_frame_planilha.winfo_children():
            child.destroy()
            
        if not hasattr(self, 'thumb_images_planilha'):
            self.thumb_images_planilha = []
        self.thumb_images_planilha.clear()

        if not hasattr(self, 'galeria_arquivos_planilha') or not self.galeria_arquivos_planilha:
            import tkinter as tk
            tk.Label(self.galeria_frame_planilha,
                     text="Nenhuma foto carregada.\nFaça a busca por EAN.",
                     justify="center", background="#1E1E1E", foreground="#CCCCCC",
                     font=("Segoe UI", 10)).grid(row=0, column=0, padx=24, pady=28, sticky="w")
            return

        cols = max(1, self._galeria_cols or 3)
        for c in range(cols):
            self.galeria_frame_planilha.columnconfigure(c, weight=1)

        for i, arq in enumerate(self.galeria_arquivos_planilha):
            import tkinter as tk
            card = tk.Frame(self.galeria_frame_planilha, background="#2B2B2B", padx=8, pady=8)
            card.grid(row=i // cols, column=i % cols, padx=6, pady=6, sticky="nsew")
            try:
                img = Image.open(arq).convert("RGB")
                img.thumbnail((170, 170))
                photo = ImageTk.PhotoImage(img)
                self.thumb_images_planilha.append(photo)
                tk.Label(card, image=photo, background="#2B2B2B").pack()
            except Exception:
                tk.Label(card, text="[imagem]", background="#2B2B2B", foreground="#CCCCCC").pack(padx=45, pady=60)
            tk.Label(card, text=arq.stem.split("_")[-1], anchor="center",
                     background="#2B2B2B", foreground="#CCCCCC",
                     font=("Segoe UI", 9)).pack(fill="x", pady=(6, 0))

    def _anexar_planilha(self):
        caminho = filedialog.askopenfilename(filetypes=[("Planilhas Excel/CSV", "*.xlsx *.csv")])
        if caminho:
            self.caminho_planilha = caminho
            nome = os.path.basename(caminho)
            if len(nome) > 25: nome = nome[:22] + "..."
            self.lbl_planilha.configure(text=nome)
            
            try:
                cabecalhos = []
                if caminho.lower().endswith('.csv'):
                    import csv
                    with open(caminho, 'r', encoding='utf-8', errors='ignore') as f:
                        sample = f.read(1024)
                        f.seek(0)
                        delim = ';' if ';' in sample else ','
                        reader = csv.reader(f, delimiter=delim)
                        for row in reader:
                            cabecalhos = [str(c).strip() for c in row if c]
                            break
                else:
                    import openpyxl
                    wb = openpyxl.load_workbook(caminho, data_only=True, read_only=True)
                    ws = wb.active
                    for row in ws.iter_rows(values_only=True):
                        cabecalhos = [str(c).strip() for c in row if c is not None]
                        break
                
                if cabecalhos:
                    self.cabecalhos_planilha = cabecalhos
                    self.dropdown_coluna.configure(values=[c.upper() for c in cabecalhos])
                    
                    colunas_principais = ["pai", "sku", "ref", "título", "titulo", "ean", "código", "codigo", "item", "id"]
                    coluna_selecionada = None
                    for c in cabecalhos:
                        c_low = c.lower()
                        for p in colunas_principais:
                            if p in c_low:
                                coluna_selecionada = c
                                break
                        if coluna_selecionada:
                            break
                            
                    if coluna_selecionada:
                        self.dropdown_coluna.set(coluna_selecionada.upper())
                    else:
                        self.dropdown_coluna.set(cabecalhos[0].upper())
                        
            except Exception as e:
                self.log(f"Erro ao ler cabeçalhos da planilha: {e}")
                
            self.log(f"Planilha anexada: {caminho}")

    def _baixar_todos_planilha(self):
        coluna = self.dropdown_coluna.get()
        codigos_raw = self.entrada_lote.get("1.0", "end-1c").strip()
        
        if codigos_raw == "" or codigos_raw == "Cole os códigos aqui...":
            messagebox.showwarning("Aviso", "Cole pelo menos um código na caixa para baixar em lote.")
            return
            
        if coluna == "- Coluna -":
            messagebox.showwarning("Aviso", "Selecione a coluna (ex: EAN/SKU) para dar nome às pastas baixadas.")
            return
        if not hasattr(self, 'caminho_planilha') or not self.caminho_planilha:
            messagebox.showwarning("Aviso", "Anexe uma planilha primeiro.")
            return
        
        codigos = [c.strip() for c in codigos_raw.replace(',', '\n').split('\n') if c.strip()]
        
        threading.Thread(target=self._processar_todos_planilha, args=(coluna, codigos), daemon=True).start()

    def _buscar_ean_planilha(self):
        ean = self.entrada_ean_planilha.get().strip()
        coluna = self.dropdown_coluna.get()
        if not ean:
            messagebox.showwarning("Aviso", "Digite um valor de busca no campo.")
            return
        if not hasattr(self, 'caminho_planilha') or not self.caminho_planilha:
            messagebox.showwarning("Aviso", "Anexe uma planilha primeiro.")
            return
        
        threading.Thread(target=self._processar_planilha, args=(ean, coluna), daemon=True).start()

    def _processar_planilha(self, ean, coluna="- Coluna -"):
        self.log(f"Buscando EAN {ean} na planilha...")
        self.status.set(f"Buscando EAN {ean}...")
        try:
            linha_alvo = None
            idx_col = None
            if coluna != "- Coluna -" and hasattr(self, 'cabecalhos_planilha'):
                for i, c in enumerate(self.cabecalhos_planilha):
                    if c.upper() == coluna:
                        idx_col = i
                        break

            if self.caminho_planilha.lower().endswith('.csv'):
                import csv
                with open(self.caminho_planilha, 'r', encoding='utf-8', errors='ignore') as f:
                    sample = f.read(1024)
                    f.seek(0)
                    delim = ';' if ';' in sample else ','
                    reader = csv.reader(f, delimiter=delim)
                    for row in reader:
                        if idx_col is not None and idx_col < len(row):
                            if str(ean) in str(row[idx_col]):
                                linha_alvo = row
                                break
                        else:
                            if any(str(ean) in str(cell) for cell in row if cell):
                                linha_alvo = row
                                break
            else:
                import openpyxl
                wb = openpyxl.load_workbook(self.caminho_planilha, data_only=True)
                ws = wb.active
                for row in ws.iter_rows(values_only=True):
                    if idx_col is not None and idx_col < len(row):
                        if str(ean) in str(row[idx_col]):
                            linha_alvo = row
                            break
                    else:
                        if any(str(ean) in str(cell) for cell in row if cell is not None):
                            linha_alvo = row
                            break
            
            if not linha_alvo:
                self.log(f"EAN {ean} não encontrado na planilha.")
                self.status.set("EAN não encontrado.")
                return
            
            urls = []
            for cell in linha_alvo:
                val = str(cell).strip()
                if "http" in val:
                    # Extrai múltiplas URLs separadas por vírgulas, ponto-e-vírgula ou quebras de linha
                    partes = val.replace(',', ' ').replace(';', ' ').replace('\n', ' ').split()
                    for p in partes:
                        if p.startswith("http"):
                            urls.append(p)
            
            if not urls:
                self.log(f"EAN {ean} encontrado, mas nenhuma URL de foto na linha.")
                self.status.set("Nenhuma URL na planilha.")
                return
            
            self.log(f"Encontradas {len(urls)} URLs. Iniciando download...")
            self.status.set("Baixando imagens da planilha...")
            
            pasta_produto = self.pasta_base / str(ean)
            pasta_produto.mkdir(parents=True, exist_ok=True)
            
            # Limpar imagens antigas para não acumular
            for arq in pasta_produto.glob(f"{ean}_*.*"):
                try:
                    arq.unlink()
                except Exception:
                    pass
            
            self.galeria_arquivos_planilha = []
            
            for i, url in enumerate(urls, 1):
                try:
                    req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urlopen(req, timeout=10) as resp:
                        img_data = resp.read()
                    
                    formato_forcado = self.var_formato_img.get() if hasattr(self, 'var_formato_img') else "JPG"
                    extensao_final = ""
                    try:
                        from io import BytesIO
                        if not PILLOW:
                            raise RuntimeError("Pillow não instalado")
                        imagem = Image.open(BytesIO(img_data))
                        largura_alvo, altura_alvo = self._tamanho_escolhido()
                        from PIL import ImageOps
                        alvo = formato_forcado.upper()
                        if alvo == "JPG":
                            alvo, extensao_final = "JPEG", ".jpg"
                            if imagem.mode in ("RGBA", "P"):
                                imagem = imagem.convert("RGBA")
                                fundo_branco = Image.new("RGB", imagem.size, (255, 255, 255))
                                fundo_branco.paste(imagem, mask=imagem)
                                imagem = fundo_branco
                            else:
                                imagem = imagem.convert("RGB")
                            imagem = ImageOps.pad(imagem, (largura_alvo, altura_alvo), color=(255, 255, 255))
                        else:
                            extensao_final = f".{formato_forcado.lower()}"
                            if imagem.mode == "P":
                                imagem = imagem.convert("RGBA")
                            cor_fundo = (255, 255, 255, 0) if imagem.mode == "RGBA" else (255, 255, 255)
                            imagem = ImageOps.pad(imagem, (largura_alvo, altura_alvo), color=cor_fundo)
                        buffer = BytesIO()
                        imagem.save(buffer, format=alvo)
                        img_data = buffer.getvalue()
                    except Exception as erro:
                        self.log(f"Imagem {i} ignorada, não é uma imagem válida: {erro}")
                        continue
                        
                    nome_arq = f"{ean}_{i}{extensao_final}"
                    caminho_img = pasta_produto / nome_arq
                    with open(caminho_img, "wb") as f:
                        f.write(img_data)
                    
                    self.galeria_arquivos_planilha.append(caminho_img)
                    self.log(f"Imagem {i} baixada: {nome_arq}")
                except Exception as e:
                    self.log(f"Erro na imagem {i}: {e}")
            
            self.ultima_pasta = pasta_produto
            self.after(0, self._render_galeria_planilha)
            self.status.set(f"Concluído! {len(self.galeria_arquivos_planilha)} fotos salvas em '{pasta_produto.name}'")
            self.log("Download via planilha concluído com sucesso.")
            
            # Abre a pasta se a opção estiver ativada
            if getattr(self, 'var_abrir_pasta', None) and self.var_abrir_pasta.get():
                self.after(0, lambda p=pasta_produto: abrir_pasta(p))

        except Exception as e:
            self.log(f"Erro ao processar planilha: {e}")
            self.status.set("Erro na planilha.")


    def _extrair_id_drive(self, url):
        # Extracts the folder or file ID from a Google Drive URL
        import re
        match = re.search(r'[-\w]{25,}', url)
        return match.group(0) if match else None

    def _abrir_modal_drive(self):
        api_key = self.ia_config.get("google_drive_api_key", "")
        if not api_key:
            from tkinter import messagebox
            messagebox.showwarning("API Key Ausente", "Você precisa configurar a API Key do Google Drive na aba 'Configurações da IA' antes de usar essa funcionalidade.")
            self._selecionar_view(3)
            return

        win = ctk.CTkToplevel(self)
        self.drive_win = win
        win.title("Navegador do Google Drive")
        win.geometry("700x500")
        
        # Centralize
        self.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() // 2) - 350
        y = self.winfo_rooty() + (self.winfo_height() // 2) - 250
        win.geometry(f"+{x}+{y}")
        
        win.transient(self)
        win.grab_set()

        win.grid_rowconfigure(1, weight=1)
        win.grid_columnconfigure(0, weight=1)

        # Header
        hdr = ctk.CTkFrame(win, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=16)

        ctk.CTkLabel(hdr, text="URL da Pasta:", font=("Segoe UI", 12, "bold")).pack(side="left")
        
        self.drive_url_entry = ctk.CTkEntry(hdr, width=350, placeholder_text="Cole o link do Google Drive aqui...")
        self.drive_url_entry.pack(side="left", padx=10)

        ctk.CTkButton(hdr, text="Listar", width=80, command=self._listar_drive_atual).pack(side="left")
        
        self.drive_back_btn = ctk.CTkButton(hdr, text="← Voltar", width=80, fg_color="#555", hover_color="#444", command=self._drive_voltar)
        self.drive_back_btn.pack(side="right")
        self.drive_back_btn.pack_forget()

        # List
        self.drive_scroll = ctk.CTkScrollableFrame(win, corner_radius=8, fg_color="#1E1E1E")
        self.drive_scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))

        # Footer
        ftr = ctk.CTkFrame(win, fg_color="transparent")
        ftr.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))

        self.drive_status = ctk.CTkLabel(ftr, text="Aguardando link...", font=("Segoe UI", 11), text_color="gray")
        self.drive_status.pack(side="left")

        ctk.CTkButton(ftr, text="Baixar Selecionados", fg_color="#4CAF50", hover_color="#45A049", command=self._baixar_selecionados_drive).pack(side="right")
        ctk.CTkButton(ftr, text="Selecionar Tudo", fg_color="#333", hover_color="#222", command=self._drive_selecionar_tudo).pack(side="right", padx=10)

        self.drive_hist = []
        self.drive_current_folder = None
        self.drive_items = []
        self.drive_checkboxes = []

    def _listar_drive_atual(self):
        url = self.drive_url_entry.get().strip()
        if not url:
            return
        folder_id = self._extrair_id_drive(url)
        if not folder_id:
            self.drive_status.configure(text="Erro: Link inválido.")
            return
        
        self.drive_hist = []
        self.drive_back_btn.pack_forget()
        self._carregar_pasta_drive(folder_id, "Pasta Raiz")

    def _drive_voltar(self):
        if len(self.drive_hist) > 1:
            self.drive_hist.pop() # remove current
            prev = self.drive_hist.pop() # remove and reload prev
            self._carregar_pasta_drive(prev['id'], prev['name'])
            if len(self.drive_hist) <= 1:
                self.drive_back_btn.pack_forget()

    def _carregar_pasta_drive(self, folder_id, folder_name):
        self.drive_status.configure(text=f"Carregando '{folder_name}'...")
        self.drive_current_folder = {'id': folder_id, 'name': folder_name}
        self.drive_hist.append(self.drive_current_folder)
        
        if len(self.drive_hist) > 1:
            self.drive_back_btn.pack(side="right")
        else:
            self.drive_back_btn.pack_forget()

        import threading
        threading.Thread(target=self._carregar_pasta_drive_thread, args=(folder_id,), daemon=True).start()

    def _carregar_pasta_drive_thread(self, folder_id):
        try:
            api_key = self.ia_config.get("google_drive_api_key", "")
            drive_service = build('drive', 'v3', developerKey=api_key)
            
            results = drive_service.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="files(id, name, mimeType)",
                pageSize=1000
            ).execute()
            
            items = results.get('files', [])
            self.after(0, lambda: self._render_drive_items(items))
        except Exception as e:
            self.after(0, lambda: self.drive_status.configure(text=f"Erro na API: {e}"))

    def _render_drive_items(self, items):
        for child in self.drive_scroll.winfo_children():
            child.destroy()
        
        self.drive_items = items
        self.drive_checkboxes = []

        if not items:
            import tkinter as tk
            tk.Label(self.drive_scroll, text="A pasta está vazia.", background="#1E1E1E", foreground="gray", font=("Segoe UI", 11)).pack(pady=20)
            self.drive_status.configure(text="Pasta carregada (vazia).")
            return

        # Sort: folders first
        items.sort(key=lambda x: (x.get('mimeType') != 'application/vnd.google-apps.folder', x.get('name').lower()))

        for item in items:
            f = ctk.CTkFrame(self.drive_scroll, fg_color="transparent")
            f.pack(fill="x", pady=2)
            
            is_folder = (item.get('mimeType') == 'application/vnd.google-apps.folder')
            
            if is_folder:
                btn = ctk.CTkButton(f, text=f" 📁 {item.get('name')}", fg_color="transparent", hover_color="#333", anchor="w", font=("Segoe UI", 12, "bold"))
                btn.pack(side="left", fill="x", expand=True)
                btn.configure(command=lambda i=item['id'], n=item['name']: self._carregar_pasta_drive(i, n))
            else:
                var = __import__('tkinter').BooleanVar(value=True)
                chk = ctk.CTkCheckBox(f, text=f"🖼️ {item.get('name')}", variable=var, font=("Segoe UI", 12))
                chk.pack(side="left", padx=10)
                self.drive_checkboxes.append((item, var))
                
        self.drive_status.configure(text=f"{len(items)} item(s) encontrado(s).")

    def _drive_selecionar_tudo(self):
        # Toggle based on the first checkbox
        if not self.drive_checkboxes: return
        target = not self.drive_checkboxes[0][1].get()
        for _, var in self.drive_checkboxes:
            var.set(target)

    def _baixar_selecionados_drive(self):
        selecionados = [item for item, var in self.drive_checkboxes if var.get()]
        if not selecionados:
            return
        
        # Get EAN from parent view if typed
        ean = self.entrada_ean_planilha.get().strip()
        if not ean:
            ean = "Drive"
            
        pasta_produto = self.pasta_base / str(ean)
        pasta_produto.mkdir(parents=True, exist_ok=True)
        
        self.drive_status.configure(text=f"Baixando {len(selecionados)} arquivo(s)...")
        import threading
        threading.Thread(target=self._baixar_selecionados_drive_thread, args=(selecionados, pasta_produto), daemon=True).start()

    def _baixar_selecionados_drive_thread(self, selecionados, pasta_produto):
        try:
            api_key = self.ia_config.get("google_drive_api_key", "")
            drive_service = build('drive', 'v3', developerKey=api_key)
            
            self.galeria_arquivos_planilha = []
            self.ultima_pasta = pasta_produto
            
            for i, item in enumerate(selecionados, 1):
                self.after(0, lambda idx=i: self.drive_status.configure(text=f"Baixando {idx}/{len(selecionados)}..."))
                
                import io
                conteudo = b""
                try:
                    request = drive_service.files().get_media(fileId=item['id'])
                    from googleapiclient.http import MediaIoBaseDownload
                    
                    fh = io.BytesIO()
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while done is False:
                        status, done = downloader.next_chunk()
                    conteudo = fh.getvalue()
                except Exception as erro_api:
                    self.log(f"Aviso: API do Drive falhou ao baixar '{item['name']}', tentando link alternativo...")
                    try:
                        url_fallback = f"https://drive.google.com/uc?export=download&id={item['id']}"
                        resp = requests.get(url_fallback, timeout=60)
                        resp.raise_for_status()
                        conteudo = resp.content
                        # Verifica se o link alternativo retornou um erro HTML do Google
                        if b"<!DOCTYPE html>" in conteudo[:50] and b"google" in conteudo[:500].lower():
                            raise RuntimeError("Link alternativo também foi bloqueado.")
                    except Exception as erro_fallback:
                        raise RuntimeError(f"Falha dupla no download. API: {erro_api}. Alternativa: {erro_fallback}")
                
                formato_forcado = self.var_formato_img.get() if hasattr(self, 'var_formato_img') else "JPG"
                extensao_final = ""
                try:
                    from io import BytesIO
                    if not PILLOW:
                        raise RuntimeError("Pillow não instalado")
                    imagem = Image.open(BytesIO(conteudo))
                    largura_alvo, altura_alvo = self._tamanho_escolhido()
                    from PIL import ImageOps
                    alvo = formato_forcado.upper()
                    if alvo == "JPG":
                        alvo, extensao_final = "JPEG", ".jpg"
                        if imagem.mode in ("RGBA", "P"):
                            imagem = imagem.convert("RGBA")
                            fundo_branco = Image.new("RGB", imagem.size, (255, 255, 255))
                            fundo_branco.paste(imagem, mask=imagem)
                            imagem = fundo_branco
                        else:
                            imagem = imagem.convert("RGB")
                        imagem = ImageOps.pad(imagem, (largura_alvo, altura_alvo), color=(255, 255, 255))
                    else:
                        extensao_final = f".{formato_forcado.lower()}"
                        if imagem.mode == "P":
                            imagem = imagem.convert("RGBA")
                        cor_fundo = (255, 255, 255, 0) if imagem.mode == "RGBA" else (255, 255, 255)
                        imagem = ImageOps.pad(imagem, (largura_alvo, altura_alvo), color=cor_fundo)
                    buffer = BytesIO()
                    imagem.save(buffer, format=alvo)
                    conteudo = buffer.getvalue()
                except Exception as erro:
                    self.log(f"Arquivo '{item['name']}' ignorado, não é uma imagem válida: {erro}")
                    continue
                
                nome_base = item['name']
                if '.' in nome_base:
                    nome_base = nome_base.rsplit('.', 1)[0]
                
                caminho_img = pasta_produto / f"{nome_base}{extensao_final}"
                with open(caminho_img, "wb") as f:
                    f.write(conteudo)
                
                self.after(0, lambda path=caminho_img: self.galeria_arquivos_planilha.append(path))
            
            self.after(0, lambda: self._render_galeria_planilha())
            self.after(0, lambda: self.drive_status.configure(text=f"Concluído! {len(selecionados)} baixados para {pasta_produto.name}."))
            self.log(f"Baixados {len(selecionados)} arquivos do Google Drive para {pasta_produto.name}")
            
            # Fecha a janela do Drive após baixar
            if hasattr(self, 'drive_win') and self.drive_win.winfo_exists():
                self.after(1500, lambda: self.drive_win.destroy())
                
            # Abre a pasta se a opção estiver ativada
            if getattr(self, 'var_abrir_pasta', None) and self.var_abrir_pasta.get():
                self.after(0, lambda p=pasta_produto: abrir_pasta(p))
        except Exception as e:
            self.after(0, lambda: self.drive_status.configure(text=f"Erro no download: {e}"))
            self.log(f"Erro no download do Google Drive: {e}")

    def _processar_todos_planilha(self, coluna, codigos_alvo):
        self.status.set("Iniciando download em massa...")
        self.log(f"Iniciando download em massa para {len(codigos_alvo)} códigos na planilha...")
        
        try:
            idx_col = None
            if hasattr(self, 'cabecalhos_planilha'):
                for i, c in enumerate(self.cabecalhos_planilha):
                    if c.upper() == coluna:
                        idx_col = i
                        break
            if idx_col is None:
                self.log("Erro: Coluna não encontrada para nomear as pastas.")
                self.status.set("Erro na coluna.")
                return

            rows_to_process = []
            if self.caminho_planilha.lower().endswith('.csv'):
                import csv
                with open(self.caminho_planilha, 'r', encoding='utf-8', errors='ignore') as f:
                    sample = f.read(1024)
                    f.seek(0)
                    delim = ';' if ';' in sample else ','
                    reader = csv.reader(f, delimiter=delim)
                    next(reader, None) # skip header
                    for row in reader:
                        if len(row) > idx_col:
                            ean_row = str(row[idx_col]).strip()
                            if ean_row in codigos_alvo:
                                rows_to_process.append(row)
            else:
                import openpyxl
                wb = openpyxl.load_workbook(self.caminho_planilha, data_only=True)
                ws = wb.active
                is_header = True
                for row in ws.iter_rows(values_only=True):
                    if is_header:
                        is_header = False
                        continue
                    if len(row) > idx_col and row[idx_col] is not None:
                        ean_row = str(row[idx_col]).strip()
                        if ean_row in codigos_alvo:
                            rows_to_process.append(row)

            total = len(rows_to_process)
            self.log(f"Foram encontradas {total} linhas válidas para processar.")
            
            sucessos = 0
            for row_idx, row in enumerate(rows_to_process, 1):
                ean = str(row[idx_col]).strip()
                urls = []
                for cell in row:
                    val = str(cell).strip()
                    if "http" in val:
                        partes = val.replace(',', ' ').replace(';', ' ').replace('\n', ' ').split()
                        for p in partes:
                            if p.startswith("http"):
                                urls.append(p)
                                
                if not urls:
                    self.log(f"[{row_idx}/{total}] EAN {ean}: Nenhuma URL de foto na linha.")
                    continue
                    
                self.log(f"[{row_idx}/{total}] EAN {ean}: Baixando {len(urls)} fotos...")
                self.status.set(f"Baixando {row_idx}/{total}...")
                
                pasta_produto = self.pasta_base / str(ean)
                pasta_produto.mkdir(parents=True, exist_ok=True)

                for arq in pasta_produto.glob(f"{ean}_*.*"):
                    try: arq.unlink()
                    except: pass
                    
                for i, url in enumerate(urls, 1):
                    try:
                        req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                        with urlopen(req, timeout=10) as resp:
                            img_data = resp.read()
                        
                        formato_forcado = self.var_formato_img.get() if hasattr(self, 'var_formato_img') else "JPG"
                        extensao_final = ""
                        try:
                            from io import BytesIO
                            if not PILLOW: raise RuntimeError("Pillow não instalado")
                            imagem = Image.open(BytesIO(img_data))
                            largura_alvo, altura_alvo = self._tamanho_escolhido()
                            from PIL import ImageOps
                            alvo = formato_forcado.upper()
                            if alvo == "JPG":
                                alvo, extensao_final = "JPEG", ".jpg"
                                if imagem.mode in ("RGBA", "P"):
                                    imagem = imagem.convert("RGBA")
                                    fundo_branco = Image.new("RGB", imagem.size, (255, 255, 255))
                                    fundo_branco.paste(imagem, mask=imagem)
                                    imagem = fundo_branco
                                else:
                                    imagem = imagem.convert("RGB")
                                    imagem = ImageOps.pad(imagem, (largura_alvo, altura_alvo), color=(255, 255, 255))
                            else:
                                extensao_final = f".{formato_forcado.lower()}"
                                if imagem.mode == "P": imagem = imagem.convert("RGBA")
                                cor_fundo = (255, 255, 255, 0) if imagem.mode == "RGBA" else (255, 255, 255)
                                imagem = ImageOps.pad(imagem, (largura_alvo, altura_alvo), color=cor_fundo)
                            buffer = BytesIO()
                            imagem.save(buffer, format=alvo)
                            img_data = buffer.getvalue()
                        except Exception:
                            extensao_final = ".jpg" if "jpg" in url.lower() or "jpeg" in url.lower() else ".png"

                        caminho_final = pasta_produto / f"{ean}_{i}{extensao_final}"
                        with open(caminho_final, "wb") as f:
                            f.write(img_data)
                    except Exception as e:
                        self.log(f"Falha ao baixar imagem {i} do EAN {ean}: {e}")
                        
                sucessos += 1
                
            self.status.set("Download em massa concluído!")
            self.log(f"========== DOWNLOAD EM MASSA CONCLUÍDO ==========")
            self.log(f"Foram processados {sucessos} produtos com sucesso de um total de {total}.")
            messagebox.showinfo("Sucesso", f"Download em massa concluído!\n{sucessos} de {total} produtos processados.")
            
            if getattr(self, 'var_abrir_pasta', None) and self.var_abrir_pasta.get():
                self.after(0, lambda p=self.pasta_base: abrir_pasta(p))
            
        except Exception as e:
            self.log(f"Erro no download em massa: {e}")
            self.status.set("Erro no download em massa.")

if __name__ == "__main__":

    app = App()
    app.mainloop()
