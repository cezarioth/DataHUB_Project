#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/cadastro.py
Montagem dos formatos de cadastro PRECODE e CASAS BAHIA.
"""

import re

from .config import (
    DIMENSAO_LABELS,
    DIMENSAO_ORDEM,
    DIFERENCIAIS_LABELS,
    RECOMENDACOES_CONSERVACAO,
    OBSERVACOES_PADRAO,
    SECTION_ORDER,
)
from .text_utils import norm, clean_text, clean_char, normalize_guarantee, dedupe


# ---------------------------------------------------------------------------
# Dimensões
# ---------------------------------------------------------------------------

def _rotulo(item: str) -> str:
    return norm(item.split(":", 1)[0]) if ":" in item else ""


def separar_dimensoes(itens):
    """Separa campos de dimensão (Altura, Largura, Profundidade, Peso) da lista."""
    restantes, encontradas = [], {}
    for item in itens:
        rotulo = _rotulo(item)
        if rotulo in DIMENSAO_LABELS:
            encontradas.setdefault(rotulo, item)
        else:
            restantes.append(item)
    dimensoes = [encontradas[r] for r in DIMENSAO_ORDEM if r in encontradas]
    return restantes, dimensoes


# ---------------------------------------------------------------------------
# Garantia
# ---------------------------------------------------------------------------

def formatar_garantia_padrao(itens) -> str:
    """'<tempo> contra defeitos de fabricação.', com 90 dias/3 meses → '3 Meses...'"""
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


def format_guarantee_items(items):
    """Normaliza garantia para o formato do Mercado Livre."""
    if not items:
        return []
    text = clean_text(" ".join(items), True)
    text = normalize_guarantee(text)
    m = re.search(r"(?i)\b(\d+(?:[.,]\d+)?)\s*mes(?:es)?\s+de\s+garantia\b", text)
    if m:
        prazo = m.group(1)
        before = text[: m.start()].strip(" ,.-")
        after = text[m.end() :].strip(" ,.-")
        if after:
            after = re.sub(r"(?i)^contra\s+", "contra ", after)
            return [f"Garantia de {prazo} meses, {after}"]
        return [f"Garantia de {prazo} meses"]
    m = re.search(r"(?i)\bgarantia\s+de\s+(\d+(?:[.,]\d+)?)\s*mes(?:es)?\b", text)
    if m:
        prazo = m.group(1)
        rest = (text[m.end() :]).strip(" ,.-")
        return [f"Garantia de {prazo} meses" + (f", {rest}" if rest else "")]
    return [text]


# ---------------------------------------------------------------------------
# Diferenciais
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Produto: nome
# ---------------------------------------------------------------------------

def extrair_nome_produto(soup, referencia: str = "") -> str:
    """Nome comercial do produto (via <title> ou JSON-LD)."""
    import json as _json
    nome = ""
    try:
        if soup.title:
            nome = soup.title.get_text(" ", strip=True)
            nome = re.sub(r"\s*[\|\-–]\s*Decathlon.*$", "", nome, flags=re.I).strip()
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = _json.loads(tag.string or tag.get_text())
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


# ---------------------------------------------------------------------------
# Montagem PRECODE
# ---------------------------------------------------------------------------

def montar_cadastro_precode(nome, sobre, tecnicos, caracteristicas, garantia_itens) -> str:
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


# ---------------------------------------------------------------------------
# Montagem CASAS BAHIA
# ---------------------------------------------------------------------------

def montar_cadastro_casas_bahia(nome, sobre, tecnicos, caracteristicas, garantia_itens) -> str:
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


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def montar_cadastro(formato, nome, sobre, tecnicos, caracteristicas, garantia_itens) -> str:
    if (formato or "").strip().upper() == "CASAS BAHIA":
        return montar_cadastro_casas_bahia(nome, sobre, tecnicos, caracteristicas, garantia_itens)
    return montar_cadastro_precode(nome, sobre, tecnicos, caracteristicas, garantia_itens)
