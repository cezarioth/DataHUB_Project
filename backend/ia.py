#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/ia.py
Integração com IA (OpenAI Responses API) e LanguageTool.
"""

import json
import re
from pathlib import Path

import requests

from .config import IA_DEFAULT_ENDPOINT, IA_DEFAULT_MODEL, LANGUAGETOOL_DEFAULT_ENDPOINT


# ---------------------------------------------------------------------------
# Constantes de configuração e prompts
# ---------------------------------------------------------------------------

IA_CONFIG_PATH = Path.home() / ".extrator_decathlon_ia.json"

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


if "Formatar cadastro Decathlon" in IA_PRESETS:
    IA_PRESETS["Padrão Decathlon"] = IA_PRESETS["Formatar cadastro Decathlon"]
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

Sempre que um conteúdo for colado, independentemente da ordem em que os blocos forem enviados, a IA deverá reorganizar automaticamente na ordem: Sobre o Produto → Informações Técnicas → Características do Produto → Garantia do Fornecedor, removendo qualquer marcador, símbolo ou formatação especial das listas.""",
}

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


# ---------------------------------------------------------------------------
# Configuração persistente
# ---------------------------------------------------------------------------

def carregar_config_ia() -> dict:
    try:
        if IA_CONFIG_PATH.exists():
            data = json.loads(IA_CONFIG_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def salvar_config_ia(config: dict):
    try:
        IA_CONFIG_PATH.write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Chamada à IA
# ---------------------------------------------------------------------------

def _extrair_texto_responses_api(data: dict) -> str:
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


def chamar_ia(prompt_usuario: str, api_key: str, model: str,
              endpoint: str = IA_DEFAULT_ENDPOINT, log=None) -> str:
    if not api_key.strip():
        raise RuntimeError("Informe a chave da API na área de IA.")
    if not endpoint.strip():
        endpoint = IA_DEFAULT_ENDPOINT
    payload = {
        "model": model.strip() or IA_DEFAULT_MODEL,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": IA_SYSTEM}]},
            {"role": "user", "content": [{"type": "input_text", "text": prompt_usuario}]},
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
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


# ---------------------------------------------------------------------------
# Detecção de idioma e tradução
# ---------------------------------------------------------------------------

_PALAVRAS_PT_COMUNS = {
    "de", "da", "do", "das", "dos", "para", "com", "não", "que", "uma", "um",
    "os", "as", "em", "por", "sua", "seu", "mais", "produto", "é", "e",
    "esta", "este", "sem", "muito", "também", "você",
}
_PALAVRAS_NAO_PT_COMUNS = {
    "le", "la", "les", "des", "avec", "pour", "vous", "produit", "est", "un", "une",
    "the", "and", "with", "product", "for", "this", "your", "is", "are",
    "el", "los", "las", "con", "para", "producto", "es", "una",
    "il", "und", "der", "die", "das", "een", "van", "het",
}


def _parece_portugues(texto: str) -> bool:
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


def traduzir_para_portugues(texto: str, api_key: str, model: str, endpoint: str, log=None) -> str:
    if not texto or not texto.strip():
        return texto
    if _parece_portugues(texto):
        return texto
    if not (api_key or "").strip():
        if log:
            log("TRADUÇÃO: texto em outro idioma, mas sem chave de IA; mantendo original.")
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


# ---------------------------------------------------------------------------
# Auditor IA
# ---------------------------------------------------------------------------

def auditar_descricao_com_ia(fonte_original: str, descricao_candidata: str,
                              prompt_original: str, api_key: str, model: str,
                              endpoint: str, log=None) -> str:
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


# ---------------------------------------------------------------------------
# LanguageTool
# ---------------------------------------------------------------------------

def _tokens_numericos(texto: str):
    return re.findall(r"\d+(?:[.,]\d+)?", texto or "")


def corrigir_com_languagetool(texto: str, endpoint: str,
                               api_key: str = "", username: str = "", log=None):
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

    corrigido = texto
    aplicadas = 0
    aceitas = []
    for match in sorted(matches, key=lambda m: int(m.get("offset", 0)), reverse=True):
        offset = int(match.get("offset", 0))
        length = int(match.get("length", 0))
        replacements = match.get("replacements") or []
        original = corrigido[offset : offset + length]
        if not original or not replacements:
            continue

        issue_type = str(match.get("rule", {}).get("issueType", "")).lower()
        if issue_type not in {"misspelling", "grammar", "typographical", "duplication", "other"}:
            continue

        substituto = str(replacements[0].get("value", ""))
        if not substituto or substituto == original:
            continue

        if _tokens_numericos(original) != _tokens_numericos(substituto):
            continue
        if re.search(r"[A-Za-zÀ-ÿ]*\d[A-Za-zÀ-ÿ]*", original) and original.casefold() != substituto.casefold():
            continue

        corrigido = corrigido[:offset] + substituto + corrigido[offset + length:]
        aceitas.append((original, substituto))
        aplicadas += 1

    if log:
        log(f"LanguageTool: {aplicadas} correção(ões) objetiva(s) aplicada(s).")
    return corrigido, aplicadas
