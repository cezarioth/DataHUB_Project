#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/anatel.py
Consulta, download, indexação e busca na base de homologação ANATEL.
"""

import csv
import json
import re
import shutil
import time
import unicodedata
import zipfile
from pathlib import Path

import requests

from .config import (
    ANATEL_CONFIG_FILE,
    ANATEL_URL_OFICIAL,
    ANATEL_CACHE_DIAS,
    ANATEL_COLUNAS,
    APP_DIR,
    HEADERS,
)


# ---------------------------------------------------------------------------
# Cache em memória
# ---------------------------------------------------------------------------

_anatel_cache: dict = {"caminho": None, "mtime": None, "linhas": None, "colunas": None}


# ---------------------------------------------------------------------------
# Normalização de número de homologação
# ---------------------------------------------------------------------------

def normalizar_homologacao_anatel(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    digits = re.sub(r"[^0-9]", "", value)
    if 7 <= len(digits) <= 15:
        return digits.lstrip("0")
    m = re.search(
        r"(?i)n(?:ú|u)mero\s+de\s+homologa(?:ç|c)(?:a|ã)o\s*[:\-]?\s*([0-9][0-9\s.\-]{7,20}[0-9])",
        value,
    )
    if m:
        digits = re.sub(r"[^0-9]", "", m.group(1))
        if 7 <= len(digits) <= 15:
            return digits.lstrip("0")
    return ""


def localizar_numero_anatel_html(html: str) -> str:
    """Tenta localizar um número de homologação no HTML."""
    if not html:
        return ""
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


# ---------------------------------------------------------------------------
# Caminhos locais
# ---------------------------------------------------------------------------

def _norm_col(nome: str) -> str:
    nome = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode("ascii")
    return nome.strip().lower()


def salvar_caminho_base_anatel(caminho: str):
    cfg_path = APP_DIR / ANATEL_CONFIG_FILE
    try:
        cfg_path.write_text(
            json.dumps({"caminho_base": str(caminho)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def carregar_caminho_base_anatel_salvo() -> str:
    cfg_path = APP_DIR / ANATEL_CONFIG_FILE
    if not cfg_path.exists():
        return ""
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        return data.get("caminho_base", "") or ""
    except Exception:
        return ""


def _pasta_dados_anatel() -> Path:
    pasta = APP_DIR / "dados_anatel"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _caminho_indice_anatel() -> Path:
    return _pasta_dados_anatel() / "indice_anatel.tsv"


def _caminho_zip_anatel() -> Path:
    return _pasta_dados_anatel() / "produtos_certificados.zip"


def _pasta_extraida_anatel() -> Path:
    return _pasta_dados_anatel() / "extraido"


def idade_dias_arquivo(caminho) -> float:
    try:
        mtime = Path(caminho).stat().st_mtime
        return (time.time() - mtime) / 86400
    except Exception:
        return -1


def localizar_base_anatel() -> str:
    salvo = carregar_caminho_base_anatel_salvo()
    if salvo and Path(salvo).exists():
        return salvo

    indice = _caminho_indice_anatel()
    if indice.exists():
        return str(indice)

    pasta = APP_DIR
    candidatos = []
    for ext in ("*.csv", "*.txt", "*.xlsx", "*.xls", "*.zip"):
        candidatos.extend(pasta.glob(ext))

    palavras_chave = ("anatel", "homologa", "certificad")
    for arq in candidatos:
        if any(p in arq.name.lower() for p in palavras_chave):
            return str(arq)
    return ""


# ---------------------------------------------------------------------------
# Leitura da base
# ---------------------------------------------------------------------------

def _detectar_delimitador(amostra: str) -> str:
    try:
        return csv.Sniffer().sniff(amostra, delimiters=[",", ";", "\t", "|"]).delimiter
    except Exception:
        contagens = {d: amostra.count(d) for d in (",", ";", "\t", "|")}
        return max(contagens, key=contagens.get)


def _mapear_colunas(cabecalho) -> dict:
    normalizados = [_norm_col(c) for c in cabecalho]
    mapa = {}
    for campo, variantes in ANATEL_COLUNAS.items():
        for idx, col in enumerate(normalizados):
            if col in variantes:
                mapa[campo] = idx
                break
        if campo in mapa:
            continue
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
            "Para ler a base em Excel (.xlsx) é preciso instalar 'openpyxl' "
            "(pip install openpyxl), ou exportar a base como CSV/TXT."
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
    destino = _pasta_extraida_anatel()
    if destino.exists():
        shutil.rmtree(destino, ignore_errors=True)
    destino.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(caminho_zip) as zf:
            zf.extractall(destino)
    except PermissionError:
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


def garantir_base_anatel_oficial(forcar_download: bool = False, log=None) -> Path:
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
    caminho = garantir_base_anatel_oficial(forcar_download=True, log=log)
    salvar_caminho_base_anatel(str(caminho))
    return str(caminho)


def carregar_base_anatel(caminho: str, forcar: bool = False):
    caminho_obj = Path(caminho)
    if not caminho_obj.exists():
        raise FileNotFoundError(f"Base ANATEL não encontrada em: {caminho}")

    mtime = caminho_obj.stat().st_mtime
    if (
        not forcar
        and _anatel_cache["caminho"] == str(caminho_obj)
        and _anatel_cache["mtime"] == mtime
    ):
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

    _anatel_cache.update({"caminho": str(caminho_obj), "mtime": mtime,
                          "linhas": linhas, "colunas": mapa})
    return linhas, mapa


def consultar_anatel(numero: str, log=None) -> dict:
    """Busca o número de homologação na base local da ANATEL."""
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
                f"oficial automaticamente ({erro})."
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
