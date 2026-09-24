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
from frontend import StatusBar
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
    APP_DIR = Path(__file__).resolve().parent.parent
    ASSETS_DIR = APP_DIR / "assets"

import requests
from bs4 import BeautifulSoup

try:
    from PIL import Image, ImageTk
    PILLOW = True
except ImportError:
    PILLOW = False




# Cabeçalhos usados nas requisições da página e das imagens.
# Mantém a mesma aparência de um navegador comum para reduzir bloqueios do site.

# Campos que aparecem em algumas páginas de parceiros/vendedores em formato corrido.

# Rótulos de atributo (Nome do item: valor) que a IA às vezes converte para
# "Nome do item. valor" por engano. Depois da resposta da IA, forçamos de
# volta o formato com dois pontos para esses rótulos conhecidos.


























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


































































# https://loja.vteximg.com.br/arquivos/ids/1234567-500-500/nome.jpg
# https://loja.vtexassets.com/arquivos/ids/1234567-800-auto?v=638...

# A Decathlon atual usa URLs VTEX embrulhadas pelo CDN "unsafe/..." e
# codificadas com %2F. Por isso procuramos também a URL VTEX interna.

# https://contents.mediadecathlon.com/p/p/<hash>/...jpg?f=500x500










# --------------------------------------------------------------------------
# Identificação da referência (a partir da URL da página)
# --------------------------------------------------------------------------




# --------------------------------------------------------------------------
# Serviço de Busca de URL por REF (Decathlon)
# --------------------------------------------------------------------------







# --------------------------------------------------------------------------
# Leitura do código-fonte
# --------------------------------------------------------------------------












# --------------------------------------------------------------------------
# Plano B "inteligente": bloco de estado JS (__NEXT_DATA__, window.__STATE__,
# etc.). Muitas lojas VTEX/FastStore só colocam a imagem "principal" no
# JSON-LD e escondem a galeria completa (todas as 10 fotos) num desses
# blocos. A lógica de pontuação por SKU/referência é a mesma do JSON-LD,
# mas aqui ela é aplicada a QUALQUER dicionário do JSON que tenha uma lista
# de imagens, não só a nós "@type": "Product".
# --------------------------------------------------------------------------


# outras stacks (Nuxt, apps React que fazem hidratação manual, etc.) deixam
# o estado numa variável global do tipo "window.__ALGO__ = {...};"


















# --------------------------------------------------------------------------
# Identificação da galeria da variação aberta
# --------------------------------------------------------------------------




















# --------------------------------------------------------------------------
# Normalização: ID canônico (dedupe) + reescrita de tamanho
# --------------------------------------------------------------------------







# --------------------------------------------------------------------------
# Download + conversão de formato
# --------------------------------------------------------------------------








# --------------------------------------------------------------------------
# ANATEL - BUSCA E CONFIRMACAO
# --------------------------------------------------------------------------






# URL oficial de dados abertos da ANATEL usada pelo backend original em
# PowerShell: um ZIP contendo o CSV "Produtos_Homologados_Anatel.csv".

# Nomes de coluna aceitos (normalizados: minúsculo e sem acento) para cada
# campo que usamos. Os nomes oficiais da ANATEL vêm primeiro; o restante
# cobre variações comuns de outras exportações/fontes.

# Cache em memória para não reler o arquivo inteiro a cada consulta.
_anatel_cache = {"caminho": None, "mtime": None, "linhas": None, "colunas": None}










































# --------------------------------------------------------------------------
# Interface
# --------------------------------------------------------------------------











# ============================================================
# IA PARA APOIO AO CADASTRO
# ============================================================









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


# Backend services used by the window. Keeping these imports explicit makes the
# dependency direction visible and prevents accidental cross-layer coupling.
from backend.anatel import (
    atualizar_base_anatel_oficial,
    carregar_base_anatel,
    consultar_anatel,
    idade_dias_arquivo,
    localizar_base_anatel,
    localizar_numero_anatel_html,
    normalizar_homologacao_anatel,
    salvar_caminho_base_anatel,
)
from backend.config import (
    ASSETS_DIR,
    FORMATOS_CADASTRO,
    IA_DEFAULT_ENDPOINT,
    IA_DEFAULT_MODEL,
    TAMANHOS_PRESET,
)
from backend.description import (
    normalizar_estrutura_descricao,
    validar_descricao_deterministica,
)
from backend.extractor import extract_from_html, referencia_da_url
from backend.ia import (
    IA_PRESETS,
    PROMPT_CORRECAO_ERROS,
    PROMPT_DESCRICAO_CURTA_LIVELO,
    auditar_descricao_com_ia,
    carregar_config_ia,
    chamar_ia,
    corrigir_com_languagetool,
    salvar_config_ia,
    traduzir_para_portugues,
)
from backend.images import (
    abrir_pasta,
    baixar_html_fotos,
    buscar_produto_por_ref,
    coletar,
    normalizar_ref,
    salvar,
)
from backend.text_utils import restaurar_dois_pontos_atributos


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
        self.status_bar = StatusBar(self.main_container, self.status)
        self.status_bar.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.status_label = self.status_bar.label

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

