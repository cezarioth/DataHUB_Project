#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/config.py
Constantes globais, aliases e configurações compartilhadas por todos os módulos.
"""

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Caminhos base (suporte a executável PyInstaller e execução normal)
# ---------------------------------------------------------------------------

if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).parent
    ASSETS_DIR = Path(sys._MEIPASS) / "assets"
else:
    APP_DIR = Path(__file__).resolve().parent.parent
    ASSETS_DIR = APP_DIR / "assets"

# ---------------------------------------------------------------------------
# Ordem canônica das seções da descrição
# ---------------------------------------------------------------------------

SECTION_ORDER = ["Sobre o produto", "Informações técnicas", "Características", "Garantia"]

# ---------------------------------------------------------------------------
# Stop-words: marcadores de fim de conteúdo útil na página
# ---------------------------------------------------------------------------

STOP_WORDS = {
    "avaliações", "avaliação", "avaliações do produto", "comentários", "comentário",
    "reviews", "review", "customer reviews", "avis clients",
    "perguntas e respostas", "você também pode gostar", "compre junto",
    "produtos similares", "veja também", "relacionados",
    "códigos internos do produto", "codigo interno do produto",
    "códigos internos", "codigos internos",
}

# ---------------------------------------------------------------------------
# Aliases de seções técnicas
# ---------------------------------------------------------------------------

TECH_ALIASES = {
    "informações técnicas", "informacao tecnica", "informações tecnica",
    "informações tecnicas", "ficha técnica", "ficha tecnica", "dados técnicos",
    "dados tecnicos",
}
CHAR_ALIASES = {
    "características", "caracteristicas",
    "características do produto", "caracteristicas do produto",
}
GAR_ALIASES = {"garantia"}

# ---------------------------------------------------------------------------
# Cabeçalhos HTTP para requisições de página e imagens
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Referer": "https://www.decathlon.com.br/",
    "Connection": "close",
}

# ---------------------------------------------------------------------------
# Rótulos inline de campos técnicos
# ---------------------------------------------------------------------------

INLINE_LABELS = [
    "Nome", "Gênero", "Indicado para", "Detalhes", "Composição", "Armação",
    "História do design", "Que tamanho escolher?",
    "O que envolve a parceria com a NBA?", "Armazenamento",
    "Restrição de Uso", "Teste de Qualidade", "Cabedal", "Lingueta", "Palmilha",
    "Solado", "Terreno", "Fechamento", "Marca", "Código do Artigo", "Tecnologia",
    "Tecnologias", "Nível", "Material", "Peso", "Dimensões",
    "Facilidade de transporte", "Conselhos de Manutenção",
    "Conselhos de manutenção", "Manutenção", "Tipo de jogo", "Equilíbrio",
    "Garantia",
]

ATRIBUTOS_COM_DOIS_PONTOS = sorted(
    set(INLINE_LABELS) | {
        "Altura", "Largura", "Profundidade", "Peso do produto", "Peso bruto",
        "Composição", "Cor", "Voltagem", "Capacidade", "Potência", "Tamanho",
        "Modelo", "Referência", "Código EAN", "Códigos EAN13 do produto",
        "Códigos internos do produto",
    },
    key=len,
    reverse=True,
)

# ---------------------------------------------------------------------------
# Padrões de cadastro (PRECODE / CASAS BAHIA)
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Tamanhos / formatos de imagem disponíveis na UI
# ---------------------------------------------------------------------------

TAMANHOS_PRESET = ["1000x1000", "800x800", "500x500", "Personalizado..."]
FORMATOS = ["JPG"]

# ---------------------------------------------------------------------------
# ANATEL
# ---------------------------------------------------------------------------

ANATEL_CONFIG_FILE = "anatel_config.json"
ANATEL_URL_OFICIAL = (
    "https://www.anatel.gov.br/dadosabertos/paineis_de_dados/"
    "certificacao_de_produtos/produtos_certificados.zip"
)
ANATEL_CACHE_DIAS = 7

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

# ---------------------------------------------------------------------------
# IA
# ---------------------------------------------------------------------------

IA_DEFAULT_ENDPOINT = "https://api.openai.com/v1/responses"
IA_DEFAULT_MODEL = "gpt-5.6-luna"
LANGUAGETOOL_DEFAULT_ENDPOINT = "http://localhost:8081/v2/check"
