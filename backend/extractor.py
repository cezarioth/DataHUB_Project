#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/extractor.py
Ponto de entrada do pipeline de extração: recebe URL/HTML e orquestra
description.py + cadastro.py para devolver o texto final formatado.
"""

import re

from bs4 import BeautifulSoup

from .config import SECTION_ORDER, CHAR_ALIASES, TECH_ALIASES, GAR_ALIASES, STOP_WORDS
from .text_utils import (
    norm, clean_text, clean_char, dedupe,
    is_commercial_text, is_review_only_text,
    strip_review_content, strip_style_review_noise, strip_style_suggestion,
)
from .description import (
    visible_soup, best_marker, iter_blocks_after, group_technical,
    find_product_description, extract_characteristics, extract_inline_blob,
    add_inline, dedupe_sections, remove_standalone_suggestion_names,
)
from .cadastro import extrair_nome_produto, montar_cadastro
from .images import get_page, referencia_da_url


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def extract_decathlon_exact(soup, raw_html: str, tech_marker, formato: str = "PRECODE",
                             referencia: str = "") -> str:
    """Extrator dedicado ao padrão aprovado da Decathlon."""
    about = find_product_description(soup, None, tech_marker, None, raw_html)

    char_marker = best_marker(soup, CHAR_ALIASES)
    characteristics = (
        extract_characteristics(soup, char_marker, tech_marker, None)
        if char_marker
        else []
    )

    blocks = iter_blocks_after(tech_marker, CHAR_ALIASES | STOP_WORDS)
    technical = group_technical(blocks)

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
        r"^[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý''.-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý''.-]*){0,1}$"
    )

    maintenance_idx = None
    for idx, item in enumerate(technical):
        if norm(item) in {"conselhos de manutenção", "conselhos de manutenção do produto"}:
            maintenance_idx = idx
            break

    review_name_indices: set = set()
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
    seen: set = set()
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

    # Filtro final de nomes soltos
    protected_tech_titles = {
        "composição", "armazenamento", "restrição de uso",
        "conselhos de manutenção", "conselhos de manutenção do produto", "garantia",
    }
    filtered = []
    i = 0
    while i < len(clean_tech):
        item = clean_tech[i].strip()
        ni = norm(item)
        if (
            ni in protected_tech_titles
            or len(item.split()) > 3
            or len(item) > 60
            or re.search(r"\d", item)
        ):
            filtered.append(item)
            i += 1
            continue
        if re.fullmatch(
            r"[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý''.-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý''.-]*){0,2}", item
        ):
            j = i
            while j < len(clean_tech):
                candidate = clean_tech[j].strip()
                nc = norm(candidate)
                if (
                    nc in protected_tech_titles
                    or len(candidate.split()) > 3
                    or len(candidate) > 60
                    or re.search(r"\d", candidate)
                    or not re.fullmatch(
                        r"[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý''.-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý''.-]*){0,2}",
                        candidate,
                    )
                ):
                    break
                j += 1
            if j - i >= 2:
                i = j
                continue
        filtered.append(item)
        i += 1
    clean_tech = filtered

    if not guarantee:
        gar_marker = best_marker(soup, GAR_ALIASES)
        if gar_marker:
            gb = iter_blocks_after(gar_marker, STOP_WORDS, limit=5)
            for _, txt in gb:
                n = norm(txt)
                if n != "garantia" and not any(term in n for term in review_terms):
                    guarantee.append(clean_text(txt, True))
                    break

    clean_chars = []
    seen_chars: set = set()
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

    if not guarantee:
        guarantee = ["Garantia de 24 meses (Somente para defeitos de fabrica)."]

    nome = extrair_nome_produto(soup, referencia)
    return montar_cadastro(formato, nome, dedupe(about), clean_tech, clean_chars, guarantee)


def extract_from_html(html: str, url: str, formato: str = "PRECODE") -> str:
    """Pipeline genérico: HTML → texto de cadastro formatado."""
    soup = visible_soup(html)
    sections = {s: [] for s in SECTION_ORDER}
    referencia = referencia_da_url(url) if url else ""

    tech_marker = best_marker(soup, TECH_ALIASES)
    if tech_marker:
        return extract_decathlon_exact(soup, html, tech_marker, formato, referencia)

    char_marker = best_marker(soup, CHAR_ALIASES)
    tech_marker = best_marker(soup, TECH_ALIASES)
    gar_marker = best_marker(soup, GAR_ALIASES)
    sections["Sobre o produto"].extend(
        find_product_description(soup, char_marker, tech_marker, gar_marker, html)
    )

    if tech_marker:
        blocks = iter_blocks_after(tech_marker, CHAR_ALIASES | STOP_WORDS)
        sections["Informações técnicas"].extend(group_technical(blocks))

    if gar_marker and not tech_marker:
        blocks = iter_blocks_after(gar_marker, STOP_WORDS, limit=40)
        for _, txt in blocks:
            n = norm(txt)
            if n == "garantia":
                continue
            sections["Garantia"].append(clean_text(txt, True))
            if len(sections["Garantia"]) >= 3:
                break

    fields = extract_inline_blob(soup)
    if fields and not tech_marker:
        add_inline(sections, fields)

    if not sections["Garantia"]:
        sections["Garantia"].append("Garantia de 24 meses (Somente para defeitos de fabrica).")

    if not sections["Sobre o produto"]:
        for attrs in [{"name": "description"}, {"property": "og:description"}]:
            m = soup.find("meta", attrs=attrs)
            if m and m.get("content"):
                sections["Sobre o produto"].append(clean_text(m["content"], True))
                break

    if not sections["Sobre o produto"]:
        desc = best_marker(soup, {"descrição", "descricao", "sobre o produto"})
        if desc:
            blocks = iter_blocks_after(
                desc, CHAR_ALIASES | TECH_ALIASES | GAR_ALIASES | STOP_WORDS, limit=30
            )
            sections["Sobre o produto"].extend(
                clean_text(t, True)
                for _, t in blocks
                if not is_commercial_text(t) and len(t.strip()) >= 25
            )

    for s in SECTION_ORDER:
        sections[s] = [strip_review_content(x) for x in sections[s]]
        sections[s] = [strip_style_review_noise(x) for x in sections[s]]
        sections[s] = [strip_style_suggestion(x) for x in sections[s]]
        sections[s] = [x for x in sections[s] if not is_commercial_text(x)]
        sections[s] = [x for x in sections[s] if not is_review_only_text(x)]
        sections[s] = [x for x in sections[s] if x.strip()]
        sections[s] = dedupe(sections[s])

    sections = dedupe_sections(sections)
    sections = remove_standalone_suggestion_names(sections)

    protected_titles = {
        "composição", "armazenamento", "restrição de uso",
        "conselhos de manutenção", "conselhos de manutenção do produto",
        "garantia", "teste de qualidade",
    }
    for s in ("Sobre o produto", "Informações técnicas"):
        cleaned_items = []
        for x in sections[s]:
            lines = []
            for line in x.splitlines():
                if norm(line) in protected_titles:
                    lines.append(line)
                    continue
                if re.fullmatch(
                    r"[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý''.-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý''.-]*){0,2}",
                    line.strip(),
                ):
                    continue
                lines.append(line)
            x = "\n".join(lines).strip()
            if x:
                cleaned_items.append(x)
        sections[s] = cleaned_items

    for s, aliases in [
        ("Características", CHAR_ALIASES),
        ("Informações técnicas", TECH_ALIASES),
        ("Garantia", GAR_ALIASES),
    ]:
        if s == "Informações técnicas":
            sections[s] = [x for x in sections[s] if norm(x) not in TECH_ALIASES]
        else:
            sections[s] = [x for x in sections[s] if norm(x) not in aliases]

    tech_clean = []
    guarantee_found = []
    if tech_marker:
        sections["Garantia"] = []
    i = 0
    tech_items = sections.get("Informações técnicas", [])
    while i < len(tech_items):
        item = tech_items[i]
        if norm(item) == "garantia":
            if i + 1 < len(tech_items):
                guarantee_found.append(tech_items[i + 1])
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

    chars = []
    for x in sections["Características"]:
        if ":" in x:
            a, b = x.split(":", 1)
            x = clean_char(a, b)
        elif "," in x:
            a, b = x.split(",", 1)
            x = clean_char(a, b)
        else:
            x = clean_text(x, True)
        chars.append(x)
    chars = dedupe(chars)

    garantia_itens = (
        sections["Garantia"]
        if sections["Garantia"]
        else ["Garantia de 24 meses (Somente para defeitos de fabrica)."]
    )
    nome = extrair_nome_produto(soup, referencia)
    return montar_cadastro(
        formato, nome,
        sections["Sobre o produto"],
        sections["Informações técnicas"],
        chars,
        garantia_itens,
    )


def extract(url: str) -> str:
    """Compatibilidade com a versão original."""
    return extract_from_html(get_page(url), url)
