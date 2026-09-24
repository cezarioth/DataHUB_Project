#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/text_utils.py
Funções de limpeza, normalização e utilidades de texto.
"""

import re
import unicodedata

from .config import ATRIBUTOS_COM_DOIS_PONTOS


# ---------------------------------------------------------------------------
# Normalização básica
# ---------------------------------------------------------------------------

def norm(s: str) -> str:
    """Normaliza para comparação: remove espaço duplo, caixa baixa, NBSP."""
    s = (s or "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip().casefold()


def normalize_celsius(text: str) -> str:
    """Converte temperaturas no formato numérico seguido de C para Graus Celsius."""
    return re.sub(
        r"(?<![\\w])(\\d+(?:[.,]\\d+)?)\\s*[°º]?\\s*C\\b",
        r"\\1 Graus Celsius",
        text,
    )


def clean_text(text: str, keep_parentheses: bool = False) -> str:
    text = (text or "").replace("\xa0", " ")
    text = text.replace("™", "").replace("®", "").replace("²", "")
    text = re.sub(r"(\d+(?:[.,]\d+)?)\s*%", r"\1 por cento", text)
    text = text.replace("/", " e ")
    if not keep_parentheses:
        text = text.replace(":", ",")
        text = re.sub(r"\(([^()]*)\)", r"\1", text)
    allowed = r"[^\wÀ-ÿ\s.,?!():]" if keep_parentheses else r"[^\wÀ-ÿ\s.,?!]"
    text = re.sub(allowed, " ", text, flags=re.UNICODE)
    text = text.replace("–", " ").replace("—", " ").replace("-", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[ \t]*([.,?!])[ \t]*", r"\1 ", text)
    text = re.sub(r"([.!?])([A-Za-zÀ-ÿ0-9])", r"\1 \2", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return normalize_celsius(text.strip())


def clean_char(label: str, answer: str) -> str:
    label = clean_text(label, True).rstrip(".,?!: ")
    answer = clean_text(answer, True).lstrip(" ,:; ")
    return f"{label}: {answer}" if answer else label


def normalize_guarantee(text: str) -> str:
    """Converte prazos de garantia expressos em anos para meses."""
    text = clean_text(text, True)

    def repl(m):
        raw = m.group(1).replace(",", ".")
        try:
            months = float(raw) * 12
            value = str(int(months)) if months.is_integer() else str(months).replace(".", ",")
            return f"{value} meses"
        except ValueError:
            return m.group(0)

    text = re.sub(r"(?i)\b(\d+(?:[.,]\d+)?)\s*anos?\b", repl, text)

    def days_to_months(m):
        days = float(m.group(1).replace(",", "."))
        months = round(days / 30)
        if months < 1 and days > 0:
            months = 1
        return f"{months} meses"

    text = re.sub(r"(?i)\b(\d+(?:[.,]\d+)?)\s*dias?\b", days_to_months, text)
    text = re.sub(
        r"(?i)\bgarantia\s+de\s+(\d+(?:[.,]\d+)?)\s*mes(?:es)?\b",
        lambda m: (
            f"Garantia de "
            f"{m.group(1).replace(',', '.').rstrip('0').rstrip('.') if '.' in m.group(1) else m.group(1)}"
            f" meses"
        ),
        text,
    )
    return text


# ---------------------------------------------------------------------------
# Deduplicação
# ---------------------------------------------------------------------------

def dedupe(items):
    out, seen = [], set()
    for x in items:
        x = x.strip()
        if not x:
            continue
        k = norm(x)
        if k not in seen:
            out.append(x)
            seen.add(k)
    return out


# ---------------------------------------------------------------------------
# Limpeza de marcadores
# ---------------------------------------------------------------------------

def _limpar_marcador_linha(linha: str) -> str:
    """Remove marcadores de lista apenas no início da linha."""
    linha = linha.strip()
    linha = re.sub(r"^(?:[-*•▪◦‣]+|\d+[.)])\s+", "", linha)
    return linha.strip()


def restaurar_dois_pontos_atributos(texto: str) -> str:
    """Corrige linhas em que a IA trocou 'Rótulo: valor' por 'Rótulo. valor'."""
    if not texto:
        return texto
    linhas = texto.split("\n")
    saida = []
    for linha in linhas:
        nova = linha
        for label in ATRIBUTOS_COM_DOIS_PONTOS:
            padrao = re.compile(
                rf"^(\s*{re.escape(label)})\.(\\s+)", re.IGNORECASE
            )
            m = padrao.match(nova)
            if m:
                nova = f"{m.group(1)}:{m.group(2)}" + nova[m.end():]
                break
        saida.append(nova)
    return "\n".join(saida)


# ---------------------------------------------------------------------------
# Strip de conteúdo de reviews / sugestões
# ---------------------------------------------------------------------------

COMMERCIAL_PATTERNS = [
    r"\b\d[\d.]*\s+vendidos?\b",
    r"\b\d[\d.]*\s+pessoas\s+favoritaram\b",
    r"\bref\s*[:.]\b",
    r"\bc[oó]digo\s+do\s+artigo\b",
    r"\bvendido\s+e\s+entregue\s+por\b",
    r"\bpor\s+r\$",
    r"\br\$\s*[\d.,]+",
    r"\bpre[cç]o\b",
    r"\bparcel",
    r"\bfrete\b",
    r"\bcalcular\s+frete\b",
    r"\bcompre\b",
    r"\bcashback\b",
    r"\bavalia[cç][oõ]es?\b",
    r"\bcoment[aá]rios?\b",
    r"\breviews?\b",
]


def is_commercial_text(text: str) -> bool:
    n = norm(text)
    if not n:
        return True
    return any(re.search(p, n, re.I) for p in COMMERCIAL_PATTERNS)


def strip_review_content(text: str) -> str:
    """Remove qualquer conteúdo de avaliações que tenha sido anexado ao bloco."""
    if not text:
        return text
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
        text = text[: min(positions)].rstrip()
    return text


def strip_style_review_noise(text: str) -> str:
    """Remove blocos de avaliações que aparecem como 'Estilo' + nome do avaliador."""
    if not text:
        return text
    lines = [x.strip() for x in re.split(r"\n+", text) if x.strip()]
    if not lines:
        return text
    review_names = re.compile(
        r"^[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-ÿ''-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-ÿ''-]*){1,3}$"
    )
    out = []
    skip_name = False
    for line in lines:
        n = norm(line)
        if n == "estilo":
            skip_name = True
            continue
        if skip_name and review_names.match(line) and len(line) <= 60:
            skip_name = False
            continue
        skip_name = False
        out.append(line)
    return "\n".join(out).strip()


def strip_style_suggestion(text: str) -> str:
    """Remove sugestões de outros produtos e nomes soltos."""
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
    standalone_name = re.compile(
        r"^[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý''.-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý''.-]*){0,2}$"
    )
    skip_names = False
    for line in lines:
        is_suggestion = any(re.search(p, line, re.I) for p in suggestion_patterns)
        if is_suggestion:
            skip_names = True
            continue
        if (
            skip_names
            and (norm(line) == "estilo" or standalone_name.match(line))
            and len(line) <= 60
        ):
            continue
        skip_names = False
        if norm(line) == "estilo":
            continue
        out.append(line)
    standalone_name2 = re.compile(
        r"^[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý''.-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý''.-]*){0,2}$"
    )
    while (
        len(out) >= 2
        and all(standalone_name2.match(x) for x in out[-2:])
        and not any(
            norm(x) in {"composição", "armação", "cabedal", "palmilha", "lingueta"}
            for x in out[-2:]
        )
    ):
        out.pop()
    return "\n".join(out).strip()


def is_review_only_text(text: str) -> bool:
    """Retorna True se o bloco de texto pertence a avaliações de clientes."""
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
    if re.search(r"\b\d(?:[.,]\d)?\s*(?:/\s*5|de\s*5|estrelas?)\b", n, re.I):
        return True
    if (
        re.fullmatch(
            r"[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý''.-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý''.-]*){0,3}",
            text.strip(),
        )
        and len(text.strip()) <= 60
    ):
        return True
    return False


def remove_size_information(text: str) -> str:
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
        "teste de qualidade",
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

        if re.match(
            r"^(?:tamanho|numeração|numeracao|número|numero)\s*[:\-]?\s*.+$",
            norm_line, re.I
        ):
            continue

        if re.search(r"\btamanho\s+único\b", norm_line, re.I):
            continue

        if re.search(
            r"\b(?:panturrilha|cintura|quadril|peito|tórax|torax|busto|circunferência|circunferencia)\b",
            norm_line, re.I,
        ):
            if re.search(r"\b(?:cm|mm|tamanho|medida|medidas)\b", norm_line, re.I):
                continue

        if re.fullmatch(
            r"(?:pp|pm|p|m|mg|g|gg|xg|xxg|xs|s|l|xl|xxl)"
            r"(?:\s*[,/;\-]\s*(?:pp|pm|p|m|mg|g|gg|xg|xxg|xs|s|l|xl|xxl))+",
            norm_line, re.I,
        ):
            continue

        result.append(raw)

    return re.sub(r"\n{3,}", "\n\n", "\n".join(result)).strip()
