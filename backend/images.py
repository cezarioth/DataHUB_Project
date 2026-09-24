#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/images.py
Download, detecção e normalização de imagens de produto (VTEX / MediaDecathlon).
"""

import re
import json
import platform
import os
import subprocess
import urllib.parse
import time
from io import BytesIO
from pathlib import Path

import requests
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .config import HEADERS

try:
    from PIL import Image, ImageOps
    PILLOW = True
except ImportError:
    PILLOW = False


# ---------------------------------------------------------------------------
# Regexes de URL
# ---------------------------------------------------------------------------

RE_VTEX = re.compile(
    r"https?://[\w.-]*vtex(?:img\.com\.br|assets\.com)/arquivos/ids/(\d+)",
    re.IGNORECASE,
)
RE_VTEX_URL_COMPLETA = re.compile(
    r"https?://[^\s\"'<>]+vtex(?:img\.com\.br|assets\.com)[^\s\"'<>]*",
    re.IGNORECASE,
)
RE_MEDIA = re.compile(
    r"https?://contents\.mediadecathlon\.com/[^\s\"'<>]+",
    re.IGNORECASE,
)
RE_JSONLD = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
RE_NEXT_DATA_ABERTURA = re.compile(
    r'<script[^>]+id=["\'']__NEXT_DATA__["\''][^>]*>',
    re.IGNORECASE,
)
RE_MARCADORES_ESTADO = re.compile(
    r"window\.(?:__[a-zA-Z0-9_]+__|pageData)\s*=\s*",
    re.IGNORECASE,
)

CHAVES_LISTA_IMAGEM = ("images", "image", "pictures", "gallery", "photos")
CHAVES_URL_DENTRO_DO_ITEM = ("imageUrl", "url", "src", "imageURL", "href")
CHAVES_ID_GENERICO = (
    "sku", "skuId", "itemId", "productId", "productReferenceId",
    "referenceId", "gtin", "gtin13", "mpn", "productID", "@id", "id",
    "slug", "linkText", "detailUrl", "url",
)
EXTENSAO_POR_TIPO = {"png": ".png", "webp": ".webp", "jpeg": ".jpg", "jpg": ".jpg"}


# ---------------------------------------------------------------------------
# Requisição HTTP simples
# ---------------------------------------------------------------------------

def get_page(url: str) -> bytes:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/140 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "close",
    }
    last = None
    for attempt in range(3):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=35) as r:
                return r.read()
        except (HTTPError, URLError, TimeoutError, OSError) as e:
            last = e
            time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"Não foi possível acessar a página da Decathlon. {last}")


def baixar_html_fotos(url: str) -> str:
    headers = dict(HEADERS)
    headers["Referer"] = "https://www.decathlon.com.br/"
    try:
        resp = requests.get(url, headers=headers, timeout=40, allow_redirects=True)
        resp.raise_for_status()
        resp.encoding = resp.encoding or "utf-8"
        return resp.text
    except requests.RequestException as erro_requests:
        try:
            return get_page(url).decode("utf-8", errors="replace")
        except Exception as erro_urllib:
            raise RuntimeError(
                "Não foi possível acessar a página da Decathlon. "
                f"Requests: {erro_requests}. Tentativa alternativa: {erro_urllib}"
            ) from erro_urllib


# ---------------------------------------------------------------------------
# Identificação / filtragem de URLs de imagem
# ---------------------------------------------------------------------------

def _caminho_media_embutido(url: str) -> str:
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
    caminho = _caminho_media_embutido(url)
    if not caminho:
        return True
    if re.match(r"^/b\d+(?:/|$)", caminho, re.IGNORECASE):
        return False
    if re.match(r"^/s\d+(?:/|$)", caminho, re.IGNORECASE):
        return False
    return bool(re.match(r"^/p(?:/|$)", caminho, re.IGNORECASE))


def _e_imagem_nao_produto(url: str) -> bool:
    caminho = _caminho_media_embutido(url)
    if not caminho:
        return False
    return not bool(re.match(r"^/p(?:/|$)", caminho, re.IGNORECASE))


def _desembrulhar_url_vtex(url: str) -> str:
    atual = (url or "").replace("&amp;", "&").strip().strip("\"' ,;)")
    atual = atual.replace("\\/", "/").replace("\u002F", "/")
    if atual.startswith("//"):
        atual = "https:" + atual

    for _ in range(4):
        decodificada = urllib.parse.unquote(atual)
        decodificada = decodificada.replace("\\/", "/")

        m_media = re.search(
            r"https?://contents\.mediadecathlon\.com/[^\s\"'<>]+",
            decodificada,
            re.IGNORECASE,
        )
        if m_media:
            return m_media.group(0).rstrip("),]}")

        m = re.search(
            r"https?://[^\s\"'<>]*vtex(?:img\.com\.br|assets\.com)"
            r"[^\s\"'<>]*?/arquivos/ids/(\d+)(?:[^\s\"'<>]*)",
            decodificada,
            re.IGNORECASE,
        )
        if m:
            return m.group(0).rstrip("),]}")

        if decodificada == atual:
            break
        atual = decodificada
    return atual


def _id_vtex(url: str):
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


def _atributos_tag(tag: str) -> dict:
    resultado = {}
    padrao = re.compile(
        r'''([:\w-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))''',
        re.IGNORECASE,
    )
    for m in padrao.finditer(tag):
        resultado[m.group(1).lower()] = m.group(2) or m.group(3) or m.group(4) or ""
    return resultado


def _normalizar_texto(texto: str) -> str:
    import unicodedata
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()
    texto = re.sub(r"\bpret[ao]s?\b", "preto", texto)
    texto = re.sub(r"\bbranc[ao]s?\b", "branco", texto)
    texto = re.sub(r"\bvermelh[ao]s?\b", "vermelho", texto)
    texto = re.sub(r"\bamarel[ao]s?\b", "amarelo", texto)
    return texto


def _identidade_da_pagina(url_pagina: str, referencia: str):
    partes_path = [p for p in urllib.parse.urlparse(url_pagina).path.split("/") if p]
    if partes_path and partes_path[-1].lower() == "p" and len(partes_path) >= 2:
        slug = partes_path[-2]
    else:
        slug = partes_path[-1] if partes_path else ""
    slug = re.sub(r"-?p$", "", slug, flags=re.IGNORECASE)
    tokens = [t for t in re.split(r"[-_]+", slug.lower()) if t]
    ref = referencia.lower()

    pos = next((i for i, t in enumerate(tokens) if ref in t), len(tokens))
    antes = tokens[:pos]
    variante = antes[-1] if antes else ""

    stop = {
        "de", "da", "do", "das", "dos", "e", "para", "com",
        "feminina", "feminino", "masculina", "masculino",
        "a", "o", "um", "uma",
    }
    base = [t for t in antes[:-1] if len(t) >= 3 and t not in stop]
    return base, variante


def _nome_arquivo_vtex(url: str) -> str:
    real = _desembrulhar_url_vtex(url)
    caminho = urllib.parse.urlparse(real).path
    return caminho.rstrip("/").split("/")[-1].lower()


# ---------------------------------------------------------------------------
# Referência da URL
# ---------------------------------------------------------------------------

def referencia_da_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    numeros = re.findall(r"(\d{5,})", path)
    return numeros[-1] if numeros else "produto"


def normalizar_ref(raw_ref: str) -> str:
    if not raw_ref:
        return ""
    ref_limpa = raw_ref.strip()
    apenas_numeros = re.sub(r"\D", "", ref_limpa)
    return apenas_numeros if apenas_numeros else ref_limpa


# ---------------------------------------------------------------------------
# Busca de produto por REF
# ---------------------------------------------------------------------------

REF_CACHE: dict = {}


def buscar_produto_por_ref(ref: str, cache: bool = True, log=None) -> dict:
    from .config import HEADERS as _HEADERS

    ref_limpa = normalizar_ref(ref)
    if not ref_limpa:
        return {
            "sucesso": False, "ref": ref, "ref_encontrada": "",
            "nome": "—", "url": "—",
            "status_texto": "⚠ REF inválida ou vazia.", "codigo_status": "INVALID_REF",
        }

    if cache and ref_limpa in REF_CACHE:
        if log:
            log(f"Busca por REF {ref_limpa}: resultado obtido do cache.")
        return REF_CACHE[ref_limpa]

    search_url = f"https://www.decathlon.com.br/pesquisa?q={ref_limpa}"
    headers = dict(_HEADERS)
    headers["Referer"] = "https://www.decathlon.com.br/"

    try:
        if log:
            log(f"Consultando a Decathlon para a REF {ref_limpa}...")
        resp = requests.get(search_url, headers=headers, timeout=20, allow_redirects=True)

        if resp.status_code != 200:
            return {
                "sucesso": False, "ref": ref_limpa, "ref_encontrada": "",
                "nome": "—", "url": "—",
                "status_texto": f"⚠ Não foi possível consultar (HTTP {resp.status_code}).",
                "codigo_status": "BLOCK",
            }

        match = re.search(r"window\.pageData\s*=\s*(\{.*?\});\s*/\*", resp.text)
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
                            "sucesso": True, "ref": ref_limpa, "ref_encontrada": p_ref or ref_limpa,
                            "nome": p_name or "Produto Decathlon", "url": canonical_url,
                            "status_texto": "✓ Produto encontrado", "codigo_status": "OK",
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
                from bs4 import BeautifulSoup as BS
                soup = BS(resp.text, "html.parser")
                title = soup.title.get_text(" ", strip=True) if soup.title else ""
                nome = title.replace(" | Decathlon", "").strip() or f"Produto REF {ref_limpa}"
                res = {
                    "sucesso": True, "ref": ref_limpa, "ref_encontrada": ref_limpa,
                    "nome": nome, "url": resp.url,
                    "status_texto": "✓ Produto encontrado", "codigo_status": "OK",
                }
                if cache:
                    REF_CACHE[ref_limpa] = res
                return res
            except Exception:
                pass

        res = {
            "sucesso": False, "ref": ref_limpa, "ref_encontrada": "",
            "nome": "—", "url": "—",
            "status_texto": "⚠ Produto não encontrado", "codigo_status": "NOT_FOUND",
        }
        if cache:
            REF_CACHE[ref_limpa] = res
        return res

    except requests.RequestException as erro_http:
        if log:
            log(f"REF {ref_limpa}: erro de conexão — {erro_http}")
        return {
            "sucesso": False, "ref": ref_limpa, "ref_encontrada": "",
            "nome": "—", "url": "—",
            "status_texto": "⚠ Erro ao consultar a Decathlon. Verifique sua conexão.",
            "codigo_status": "CONNECTION_ERROR",
        }
    except Exception as erro_geral:
        if log:
            log(f"REF {ref_limpa}: erro inesperado — {erro_geral}")
        return {
            "sucesso": False, "ref": ref_limpa, "ref_encontrada": "",
            "nome": "—", "url": "—",
            "status_texto": f"⚠ Erro inesperado: {erro_geral}",
            "codigo_status": "ERROR",
        }


# ---------------------------------------------------------------------------
# Galeria de imagens
# ---------------------------------------------------------------------------

def imagens_do_jsonld(html: str, referencia: str, url_pagina: str, log):
    def _achar_produtos(no):
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
            if url_pagina and (
                texto == url_pagina
                or url_pagina.endswith(texto)
                or texto.endswith(url_pagina)
            ):
                pontos += 15
        return pontos

    candidatos = []
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
        log("AVISO: não consegui confirmar qual variação (cor) é a da URL.")
    elif len(melhores) > 1:
        log(f"AVISO: {len(melhores)} variações empataram; usando a primeira.")

    log(
        f"Variação identificada com confiança {melhor_pontuacao} "
        f"(nós candidatos: {len(candidatos)})."
    )
    return melhores[0]


def _extrair_blocos_apos_marcador(html: str, regex_marcador):
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
        blocos.append(html[fim_abertura + 1 : fim_tag])
    blocos.extend(_extrair_blocos_apos_marcador(html, RE_MARCADORES_ESTADO))
    return blocos


def imagens_de_estado_js(html: str, referencia: str, url_pagina: str, log):
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
            if url_pagina and (
                texto == url_pagina
                or url_pagina.endswith(texto)
                or texto.endswith(url_pagina)
            ):
                pontos += 15
        return pontos

    def _varrer(no, referencia, url_pagina, candidatos, profundidade=0):
        if profundidade > 60:
            return
        if isinstance(no, dict):
            imagens = _imagens_genericas_do_no(no)
            if imagens:
                pontuacao = _pontuar_no_generico(no, referencia, url_pagina)
                candidatos.append((pontuacao, imagens))
            for valor in no.values():
                _varrer(valor, referencia, url_pagina, candidatos, profundidade + 1)
        elif isinstance(no, list):
            for item in no:
                _varrer(item, referencia, url_pagina, candidatos, profundidade + 1)

    blocos = _blocos_json_de_estado(html)
    if not blocos:
        return []
    candidatos = []
    for bruto in blocos:
        try:
            dados = json.loads(bruto)
        except json.JSONDecodeError:
            continue
        _varrer(dados, referencia, url_pagina, candidatos)

    if not candidatos:
        return []
    melhor_pontuacao = max(p for p, _ in candidatos)
    melhores = [imgs for p, imgs in candidatos if p == melhor_pontuacao]
    melhores.sort(key=len, reverse=True)
    if melhor_pontuacao <= 0:
        log("AVISO: no estado JS, usando o bloco de imagens mais completo.")
    return melhores[0]


def imagens_por_varredura(html: str):
    media = [u for u in RE_MEDIA.findall(html) if _e_foto_produto_mediadecathlon(u)]
    return RE_VTEX_URL_COMPLETA.findall(html) + media


def imagens_de_pagedata(html: str, url_pagina: str, referencia: str, log):
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


def imagens_da_galeria_html(html: str, url_pagina: str, referencia: str, log):
    base, variante = _identidade_da_pagina(url_pagina, referencia)
    variante_n = _normalizar_texto(variante)
    if not variante_n:
        variante_n = variante.lower()

    candidatos = []

    def _extrair_candidatos_por_tag(html: str):
        resultados = []
        for m in re.finditer(r"<(?:img|source)\b[^>]*>", html, re.IGNORECASE):
            tag = m.group(0)
            attrs = _atributos_tag(tag)
            contexto = " ".join(
                attrs.get(k, "") for k in ("alt", "title", "aria-label", "data-alt")
            )
            for chave in ("src", "data-src", "data-original", "data-lazy-src", "srcset", "data-srcset"):
                valor = attrs.get(chave, "")
                if not valor:
                    continue
                urls = re.findall(r"(?:https?:)?//[^\s,]+|https?://[^\s,]+", valor)
                for u in urls:
                    u = u.strip("\"'()[];,")
                    if u:
                        resultados.append((u, m.start(), contexto))
        return resultados

    for url_bruta, pos, contexto_tag in _extrair_candidatos_por_tag(html):
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

        if variante_n and variante_n in contexto:
            pontos += 200

        janela = html[max(0, pos - 1200) : min(len(html), pos + 1200)]
        if "<script" not in janela.lower() and re.search(
            rf"(?<!\d){re.escape(referencia)}(?!\d)", janela, re.IGNORECASE
        ):
            pontos += 80

        nome = _nome_arquivo_vtex(real)
        if variante_n and variante_n in _normalizar_texto(nome):
            pontos += 120

        if pontos <= 0:
            continue

        if vid:
            chave = f"vtex:{vid}"
        else:
            chave = f"media:{urllib.parse.urlparse(real).path}"
        candidatos.append((pontos, pos, url_bruta, chave, nome))

    if candidatos:
        melhores = {}
        for item in candidatos:
            chave = item[3]
            if chave not in melhores or item[0] > melhores[chave][0]:
                melhores[chave] = item
        candidatos = list(melhores.values())
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

        grupo = max(grupos, key=lambda g: (len(g), sum(x[0] for x in g)))
        grupo.sort(key=lambda x: x[1])
        urls = [x[2] for x in grupo]

        log(f"Galeria da variação '{variante}' encontrada nas tags/HTML: {len(urls)} imagem(ns).")
        if len(urls) >= 2:
            return urls

    def _extrair_urls_imagem_do_html(html: str):
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

    brutas = _extrair_urls_imagem_do_html(html)
    fallback = []
    for url_bruta, pos in brutas:
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
        janela = _normalizar_texto(html[max(0, pos - 1800) : min(len(html), pos + 1800)])
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
        log(f"Galeria da variação '{variante}' encontrada no HTML bruto: {len(urls)} imagem(ns).")
        return urls

    return []


# ---------------------------------------------------------------------------
# Normalização de URL de imagem
# ---------------------------------------------------------------------------

def normalizar(url: str, largura: int, altura: int):
    original = (url or "").replace("&amp;", "&").strip()
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


def coletar(html: str, referencia: str, url_pagina: str, largura: int, altura: int, log):
    """Coleta e normaliza a galeria de imagens da variante aberta."""
    brutas_pagedata = imagens_de_pagedata(html, url_pagina, referencia, log)
    brutas_galeria = imagens_da_galeria_html(html, url_pagina, referencia, log)
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
        log("AVISO: não encontrei uma galeria identificada. Caindo na varredura geral.")
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
        log(f"{descartadas} repetida(s) descartada(s) (mesma imagem em outro tamanho).")

    log("----- URLs de origem das imagens coletadas (debug) -----")
    for i, url in enumerate(finais, start=1):
        log(f"  origem [{i:02d}]: {url}")

    return finais


# ---------------------------------------------------------------------------
# Download e salvamento
# ---------------------------------------------------------------------------

def salvar(urls, destino: Path, referencia: str, largura: int, altura: int,
           formato_forcado: str, log) -> int:
    destino.mkdir(parents=True, exist_ok=True)
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
                log(f"[{indice}] Pillow não instalado — salvando como veio ({extensao_original}).")
            else:
                try:
                    imagem = Image.open(BytesIO(conteudo))
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
