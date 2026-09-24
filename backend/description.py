#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/description.py
Extração, validação e normalização de descrições de produtos a partir de HTML.
"""

import re
import json

from bs4 import BeautifulSoup

from .config import (
    SECTION_ORDER,
    STOP_WORDS,
    TECH_ALIASES,
    CHAR_ALIASES,
    GAR_ALIASES,
    INLINE_LABELS,
)
from .text_utils import (
    norm,
    clean_text,
    clean_char,
    dedupe,
    is_commercial_text,
    is_review_only_text,
    strip_review_content,
    strip_style_review_noise,
    strip_style_suggestion,
    _limpar_marcador_linha,
)


# ---------------------------------------------------------------------------
# Helpers HTML
# ---------------------------------------------------------------------------

def visible_soup(html: str) -> BeautifulSoup:
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
    score = {}
    for tag in candidates:
        s = 0
        if tag.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            s += 10
        nxt = tag.find_next(["h3", "h4", "h5", "p"])
        if nxt:
            s += 5
        score[id(tag)] = s
    return max(candidates, key=lambda x: score[id(x)])


def iter_blocks_after(marker, stop_aliases, limit: int = 800):
    """Extrai apenas blocos de conteúdo, sem repetir texto de wrappers HTML."""
    if not marker:
        return []
    candidates = ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "strong", "b")
    blocks = []
    seen_text = set()

    for tag in marker.find_all_next(candidates):
        txt = tag.get_text(" ", strip=True)
        if not txt:
            continue
        n = norm(txt)

        if n in stop_aliases or n in STOP_WORDS:
            break
        if tag.name in {"h1", "h2"} and n in TECH_ALIASES | CHAR_ALIASES | GAR_ALIASES:
            break

        if tag.name == "p":
            strong_children = tag.find_all(["strong", "b"], recursive=False)
            if strong_children and norm(tag.get_text(" ", strip=True)) == norm(
                strong_children[0].get_text(" ", strip=True)
            ):
                continue

        key = norm(txt)
        if key in seen_text:
            continue
        if len(txt) > 2000:
            continue

        seen_text.add(key)
        blocks.append((tag.name, txt))
        if len(blocks) >= limit:
            break

    return blocks


# ---------------------------------------------------------------------------
# Extração técnica
# ---------------------------------------------------------------------------

def split_technical_inline_fields(text: str):
    """Separa especificações que a página entregou dentro do mesmo bloco de texto."""
    if not text:
        return []
    labels = sorted(INLINE_LABELS, key=len, reverse=True)
    labels = [
        x
        for x in labels
        if x not in {"Nome", "Gênero", "Indicado para", "Detalhes", "Características", "Garantia"}
    ]
    alt = "|".join(re.escape(x) for x in labels)
    rx = re.compile(rf"(?<!\w)({alt})\s*(?::|,|\u00a0)", re.I)
    matches = list(rx.finditer(text))
    if not matches:
        return [text]
    parts = []
    if matches[0].start() > 0:
        prefix = text[: matches[0].start()].strip(" \t,;|-")
        if prefix:
            parts.append(prefix)
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        value = text[m.start() : end].strip(" \t,;|-")
        if value:
            parts.append(value)
    return parts or [text]


def group_technical(blocks):
    """Mantém somente o conteúdo técnico oficial, na ordem original."""
    result = []
    current_title = None
    current_text = []
    after_maintenance = False
    possible_review_names = []

    technical_titles = {
        "composição", "armazenamento", "restrição de uso",
        "conselhos de manutenção", "conselhos de manutenção do produto",
        "teste de qualidade", "garantia",
    }

    def looks_like_person_name(txt):
        txt = txt.strip()
        if not txt or len(txt) > 50 or len(txt.split()) > 3:
            return False
        if re.search(r"\d", txt):
            return False
        if norm(txt) in technical_titles:
            return False
        return bool(
            re.fullmatch(
                r"[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý''.-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý''.-]*){0,2}",
                txt,
            )
        )

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

        if n in {
            "guillaume", "thomas", "ryan", "christophe", "aliès", "alies",
            "klaudia", "6076", "5 e 5", "5/5",
        }:
            if after_maintenance:
                discard_review_run()
            continue

        if re.fullmatch(
            r"\d+(?:[.,]\d+)?\s*(?:e|de|/)\s*\d+(?:[.,]\d+)?"
            r"(?:\s*(?:de\s*)?\5)?",
            n,
        ):
            continue

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

        if after_maintenance and not is_title and looks_like_person_name(stripped):
            possible_review_names.append(stripped)
            if len(possible_review_names) >= 2:
                if result and result[-1] == possible_review_names[0]:
                    result.pop()
                possible_review_names = []
            continue

        if possible_review_names:
            if len(possible_review_names) >= 2:
                possible_review_names = []
            else:
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

    possible_review_names = []
    flush()

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


# ---------------------------------------------------------------------------
# JSON-LD
# ---------------------------------------------------------------------------

def jsonld_descriptions(raw_html: str):
    vals = []
    soup = BeautifulSoup(raw_html, "html.parser")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        txt = script.string or script.get_text()
        if not txt:
            continue
        try:
            data = json.loads(txt)
        except Exception:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            obj = stack.pop()
            if isinstance(obj, dict):
                obj_type = obj.get("@type")
                if isinstance(obj_type, str) and norm(obj_type) in {"review", "aggregateRating"}:
                    continue
                d = obj.get("description")
                if (
                    isinstance(d, str)
                    and len(d.strip()) > 40
                    and not re.search(
                        r"(?i)\b(?:avalia[cç][oõ]es?|coment[aá]rios?|reviews?)\b", d
                    )
                ):
                    vals.append(d.strip())
                for v in obj.values():
                    if isinstance(v, (dict, list)):
                        stack.append(v)
            elif isinstance(obj, list):
                stack.extend(obj)
    return vals


# ---------------------------------------------------------------------------
# Extração de descrição
# ---------------------------------------------------------------------------

def find_product_description(soup, char_marker, tech_marker, gar_marker, raw_html=None):
    """Captura somente a descrição principal, sem invadir a ficha técnica."""
    result = []
    stops = CHAR_ALIASES | TECH_ALIASES | GAR_ALIASES | STOP_WORDS

    def contains_section_title(text):
        lines = [norm(x) for x in re.split(r"\n+", text or "") if norm(x)]
        return any(x in stops for x in lines)

    if raw_html:
        for d in jsonld_descriptions(raw_html):
            d = clean_text(BeautifulSoup(d, "html.parser").get_text("\n", strip=True), True)
            if d and not is_commercial_text(d):
                result.append(d)
                break

    markers = exact_markers(
        soup,
        {"descrição", "descricao", "sobre o produto", "descrição do produto", "descricao do produto"},
    )

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


# ---------------------------------------------------------------------------
# Extração de características
# ---------------------------------------------------------------------------

def extract_characteristics(soup, marker, tech_marker, gar_marker):
    if not marker:
        return []
    stop_aliases = TECH_ALIASES | GAR_ALIASES | STOP_WORDS
    items = []
    seen = set()
    for tag in marker.find_all_next(["h3", "h4", "h5", "p", "h2"]):
        txt = tag.get_text("\n", strip=True)
        if not txt:
            continue
        n = norm(txt)
        if n in stop_aliases or any(
            term in n
            for term in ("avaliação", "avaliações", "comentário", "comentários", "reviews", "review")
        ):
            break
        if tag.name in {"h2", "h3", "h4"} and any(
            term in n for term in ("avaliação", "avaliações", "comentário", "comentários", "reviews", "review")
        ):
            break
        if tag.name == "h2" and n not in CHAR_ALIASES:
            break
        if tag.name not in {"h3", "h4"}:
            continue
        label = txt
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
            parent = tag.parent
            if parent:
                texts = []
                for child in parent.find_all(recursive=True):
                    if child.name in {"h3", "h4", "p"} and child is not tag:
                        t = child.get_text(" ", strip=True)
                        if t and norm(t) != n:
                            texts.append(t)
                if texts:
                    answer = texts[-1]
        if answer:
            item = clean_char(label, answer)
            k = norm(item)
            if k not in seen:
                items.append(item)
                seen.add(k)
    return items


# ---------------------------------------------------------------------------
# Inline blob
# ---------------------------------------------------------------------------

def extract_inline_blob(soup):
    """Extrai páginas em que vários campos aparecem em um bloco corrido."""
    labels = sorted(INLINE_LABELS, key=len, reverse=True)
    label_alt = "|".join(re.escape(x) for x in labels)
    rx = re.compile(rf"(?<!\w)({label_alt})\s*(?::|,|\u00a0)", re.I)
    best = None
    best_score = 0
    for tag in soup.find_all(["p", "div", "section", "article"]):
        txt = tag.get_text("\n", strip=True)
        if not (80 <= len(txt) <= 20000):
            continue
        ms = list(rx.finditer(txt))
        if len(ms) < 2:
            continue
        score = len(ms)
        if re.search(r"\bNome\s*[:,]", txt, re.I):
            score += 4
        if re.search(r"\bCaracterísticas\s*[:,]", txt, re.I):
            score += 4
        if score > best_score:
            best, best_score = txt, score
    if not best:
        return []
    ms = list(rx.finditer(best))
    fields = []
    for i, m in enumerate(ms):
        label = m.group(1).strip()
        start = m.end()
        end = ms[i + 1].start() if i + 1 < len(ms) else len(best)
        value = best[start:end].strip(" \t,;|-\n")
        if value and not re.search(
            r"(?i)\b(?:avalia[cç][oõ]es?|coment[aá]rios?|reviews?)\b", value
        ):
            fields.append((label, value))
    return fields


def add_inline(sections, fields):
    about = {norm(x) for x in ["Nome", "Gênero", "Indicado para", "Detalhes"]}
    tech = {
        norm(x)
        for x in INLINE_LABELS
        if x not in {"Nome", "Gênero", "Indicado para", "Detalhes", "Garantia", "Características"}
    }
    for label, value in fields:
        n = norm(label)
        if n == norm("Características"):
            sections["Características"].append(clean_text(value, True))
        elif n in about:
            sections["Sobre o produto"].append(clean_text(value, True))
        elif n in tech:
            sections["Informações técnicas"].append(clean_text(f"{label}, {value}", True))
        elif n == norm("Garantia"):
            sections["Garantia"].append(clean_text(f"Garantia de {value}", True))


# ---------------------------------------------------------------------------
# Deduplicação entre seções
# ---------------------------------------------------------------------------

def dedupe_sections(sections):
    def key_of(item):
        return re.sub(r"[^\wÀ-ÿ]+", " ", item, flags=re.UNICODE).strip().casefold()

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


def remove_standalone_suggestion_names(sections):
    known = {norm(x) for x in INLINE_LABELS} | {
        "estilo", "termos e condições de uso", "teste de qualidade",
        "conselhos de manutenção", "composição", "armação",
    }
    name_only = re.compile(
        r"^[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý''.-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿÀ-Ý''.-]*){0,2}$"
    )

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


# ---------------------------------------------------------------------------
# Normalização / validação da estrutura de descrição
# ---------------------------------------------------------------------------

def formatar_espacamento_informacoes_tecnicas(texto: str) -> str:
    if not texto:
        return texto

    inicio_match = re.search(r"(?im)^\s*Informações\s+T[eé]cnicas\s*:?\s*$", texto)
    if not inicio_match:
        return texto

    fim_match = re.search(
        r"(?im)^\s*(?:Características(?:\s+do\s+Produto)?|Garantia(?:\s+do\s+(?:Fornecedor|fabricante))?)\s*:?\s*$",
        texto[inicio_match.end() :],
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


def normalizar_estrutura_descricao(texto: str) -> str:
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

    secoes: dict = {}
    atual = None
    conteudo_sem_secao = []

    for raw in texto.replace("\r\n", "\n").split("\n"):
        linha = _limpar_marcador_linha(raw)
        if not linha:
            if atual:
                secoes.setdefault(atual, []).append("")
            continue

        chave = norm(re.sub(r":\s*$", "", linha))
        chave = re.sub(r"^\d+[.)]\s*", "", chave)
        if chave in aliases:
            atual = chave
            secoes.setdefault(atual, [])
            continue

        if atual:
            secoes[atual].append(linha)
        else:
            conteudo_sem_secao.append(linha)

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


def _extrair_secoes_descricao(texto: str):
    texto = normalizar_estrutura_descricao(texto)
    padroes = [
        ("sobre", r"(?im)^Sobre o Produto:\s*$"),
        ("tecnicas", r"(?im)^Informações Técnicas:\s*$"),
        ("caracteristicas", r"(?im)^Características do Produto:\s*$"),
        ("garantia", r"(?im)^Garantia do Fornecedor:\s*$"),
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


def validar_descricao_deterministica(fonte: str, descricao: str):
    erros = []
    secoes = _extrair_secoes_descricao(descricao)
    if secoes is None:
        return False, ["As quatro seções não estão presentes na ordem obrigatória."]

    linhas = descricao.replace("\r\n", "\n").split("\n")
    for i, linha in enumerate(linhas, 1):
        if re.match(r"^\s*(?:[-*•▪◦‣]+|\d+[.)])\s+", linha):
            erros.append(f"Marcador de lista encontrado na linha {i}.")

    if any(not l.strip() for l in secoes["caracteristicas"].splitlines()):
        erros.append("Há linha em branco dentro de Características do Produto.")

    bloco = secoes["tecnicas"].strip()
    if bloco:
        if re.search(r"\n{3,}", bloco):
            erros.append("Há mais de uma linha em branco entre informações técnicas.")
        if "\n" in bloco and not re.search(r"\S\n\n\S", bloco):
            erros.append("As informações técnicas não estão separadas por uma linha em branco.")

    def numeros(txt):
        return re.findall(r"(?<![A-Za-zÀ-ÿ])(\d+(?:[.,]\d+)?)(?![A-Za-zÀ-ÿ])", txt or "")

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
