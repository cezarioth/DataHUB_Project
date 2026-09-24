# DataHUB / PRODEXA

> Ferramenta para acelerar o cadastro de produtos a partir de paginas da Decathlon.

O DataHUB, tambem chamado de PRODEXA, centraliza em uma interface desktop as tarefas repetitivas do cadastro de produtos: coleta de imagens, extracao e organizacao de informacoes, consulta de homologacao ANATEL e apoio de inteligencia artificial na preparacao da descricao.

> **Status:** projeto em evolucao. O fluxo atual foi desenvolvido para paginas da Decathlon Brasil e pode precisar de ajustes quando o site mudar.

## Principais recursos

- Coleta de imagens do produto a partir de uma URL.
- Extracao de descricao e informacoes tecnicas da pagina do produto.
- Organizacao da descricao em secoes padronizadas para catalogo.
- Consulta local da base de produtos homologados da ANATEL.
- Interface grafica com tema escuro e controles para executar as etapas do cadastro.
- Assistencia de IA para revisar ou estruturar textos, quando configurada.
- Recursos visuais reutilizaveis em `assets/icons`.

## Requisitos

- Windows 10 ou superior.
- Python 3.11 ou mais recente.
- Conexao com a internet para acessar paginas de produtos e servicos externos.
- Permissao para instalar pacotes Python e gravar arquivos na pasta do projeto.
- Uma chave de API, caso os recursos de IA sejam utilizados.

## Instalacao

### Opcao recomendada: ambiente virtual

No PowerShell, a partir da pasta do projeto:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Se o PowerShell bloquear a ativacao do ambiente, execute a instalacao usando diretamente o interpretador do ambiente:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Execucao rapida

Com o ambiente virtual ativado:

```powershell
python datahub.py
```

Tambem e possivel executar `executar_datahub.bat`. Esse arquivo instala as dependencias com o launcher `py` e inicia a interface automaticamente. A primeira execucao pode demorar enquanto os pacotes sao instalados.

## Configuracao da base ANATEL

O arquivo `anatel_config.json` guarda o caminho da base local. O caminho original pode pertencer a outra maquina, portanto revise-o antes da primeira execucao:

```json
{
  "caminho_base": "C:\\caminho\\para\\DataHUB_Project\\dados_anatel\\indice_anatel.tsv"
}
```

A base distribuida no projeto fica em:

- `dados_anatel/indice_anatel.tsv`: indice usado nas consultas.
- `dados_anatel/extraido/Produtos_Homologados_Anatel.csv`: dados extraidos.
- `dados_anatel/produtos_certificados.zip`: arquivo de referencia compactado.

Use um caminho absoluto valido no seu computador. Se a base for movida, atualize o JSON novamente.

## Como usar

1. Abra o aplicativo pela opcao de execucao escolhida acima.
2. Informe a URL do produto da Decathlon e a referencia/codigo solicitada pela interface.
3. Execute a coleta de imagens e confira os arquivos obtidos.
4. Execute a extracao da descricao e revise os blocos de informacoes tecnicas, caracteristicas e garantia.
5. Consulte a homologacao ANATEL quando o produto exigir essa verificacao.
6. Na aba de IA, informe a chave de API somente se precisar dos recursos de assistencia textual.
7. Revise o resultado antes de publicar ou importar o cadastro em outro sistema.

A pagina precisa estar acessivel publicamente. Bloqueios, alteracoes de layout, limites de requisicao ou indisponibilidade da rede podem interromper a coleta.

## Estrutura do projeto

```text
DataHUB_Project/
|-- assets/                              Icones da interface
|-- backend/                             Modulos de consulta, extracao e texto
|   |-- anatel.py                        Consulta da base ANATEL
|   |-- cadastro.py                      Apoio ao fluxo de cadastro
|   |-- config.py                        Configuracoes compartilhadas
|   |-- description.py                   Tratamento de descricoes
|   |-- extractor.py                     Extracao de dados
|   |-- ia.py                            Integracao de IA
|   |-- images.py                        Coleta e tratamento de imagens
|   `-- text_utils.py                    Utilitarios de texto
|-- dados_anatel/                        Bases locais da ANATEL
|-- frontend/                            Pacote reservado para a camada visual
|-- datahub.spec                         Configuracao principal de empacotamento
|-- datahub_extractor.spec               Configuracao alternativa de empacotamento
|-- executar_datahub.bat                 Launcher para Windows
|-- requirements.txt                     Dependencias Python
`-- datahub.py                           Aplicacao principal
```

Os diretorios `build/`, `dist/` e `__pycache__/` sao artefatos locais e ficam fora do versionamento por configuracao do `.gitignore`.

## Dependencias principais

As dependencias diretas estao listadas em `requirements.txt`:

- `requests` e `beautifulsoup4` para acesso e leitura de paginas.
- `Pillow` para tratamento de imagens.
- `openpyxl` para rotinas que trabalham com planilhas.
- `customtkinter` e `google-api-python-client` para a interface e integracoes
  correspondentes.

Instale sempre pelo arquivo de requisitos para manter o ambiente reproduzivel.

## Desenvolvimento e validacao

Para verificar a sintaxe dos modulos Python:

```powershell
python -m compileall -q backend datahub.py
```

Para visualizar as alteracoes locais:

```powershell
git status
git diff
```

Os arquivos `datahub.spec` e `datahub_extractor.spec` podem ser usados como ponto de partida para gerar uma distribuicao empacotada com PyInstaller, desde que essa ferramenta esteja instalada no ambiente.

## Solucao de problemas

### `py` ou `python` nao e reconhecido

Instale o Python pelo instalador oficial e habilite a opcao de adicionar o Python ao `PATH`. Feche e abra o PowerShell novamente depois da instalacao.

### A base ANATEL nao foi encontrada

Confirme se `dados_anatel/indice_anatel.tsv` existe e se o valor de `caminho_base` em `anatel_config.json` aponta para o caminho absoluto correto.

### A coleta retornou poucos dados ou falhou

Verifique a URL, sua conexao e se a pagina abre normalmente no navegador. O extrator depende da estrutura atual da pagina da Decathlon e pode exigir manutencao quando o site for atualizado.

### A funcionalidade de IA nao funciona

Confira se a chave foi informada na aba de IA, se ela esta valida e se a conta possui acesso ao servico correspondente. Nunca coloque chaves diretamente no codigo ou em commits.

## Seguranca e dados locais

- Nao versione chaves de API, certificados, tokens ou arquivos `.env`.
- Revise os dados coletados antes de compartilha-los ou importa-los em outro sistema.
- O projeto ignora artefatos de build, caches Python e arquivos `*.pem` por padrao.
- O uso de dados e servicos externos deve respeitar os termos aplicaveis e as politicas dos respectivos provedores.

## Licenca

Este repositorio ainda nao declara uma licenca de distribuicao. Defina uma licenca antes de publicar ou redistribuir o projeto fora da equipe.
