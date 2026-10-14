# 🎙️ Live Captions

Uma aplicação desktop moderna de **legendas em tempo real** para o áudio do computador, projetada para entrevistas, reuniões, vídeos e acessibilidade. O aplicativo captura o áudio do sistema (saída de alto-falantes/fones) e exibe transcrições em tempo real em uma janela flutuante com proteção de privacidade contra compartilhamento de tela.

---

## ✨ Principais Funcionalidades

- **🔊 Captura de Áudio Interno (Loopback)**:
  - Captura o áudio emitido pelo computador usando **WASAPI Loopback** (via biblioteca `SoundCard`), sem necessidade de microfones externos ou cabos de áudio virtuais.

- **🤖 Motores de Transcrição Flexíveis**:
  - **Deepgram (Nuvem)**: Transcrição em tempo real ultra-rápida de baixa latência usando o modelo `nova-3` via WebSocket com suporte a resultados parciais (*interim results*).
  - **OpenAI Whisper (Local/Offline)**: Processamento 100% local no próprio computador, ideal para privacidade total ou uso offline, com janelas deslizantes e algoritmo de remoção de sobreposição (*overlap deduplication*).

- **🛡️ Proteção de Privacidade contra Captura de Tela**:
  - Utiliza a API nativa do Windows (`SetWindowDisplayAffinity` com `WDA_EXCLUDEFROMCAPTURE`) para **esconder a janela de legendas** de compartilhamentos de tela e gravadores (OBS, Discord, Zoom, Teams, Google Meet, etc.).

- **🎨 Interface Flutuante e Moderna (PySide6 / Qt)**:
  - Janela sem bordas (*frameless*), translúcida (*dark glassmorphism*), *Always on Top* (sempre no topo), redimensionável e arrastável.
  - Indicador de status de conexão, privacidade e botão de cópia rápida para a área de transferência via Win32 API direta.

- **🌐 Suporte a Múltiplos Idiomas**:
  - Suporte pré-configurado para Português (PT-BR / pt) e Inglês (EN-US / en).

---

## 📁 Estrutura do Projeto

```text
.
├── main.py                        # Ponto de entrada da aplicação (QApplication e inicialização)
├── requirements.txt               # Dependências do projeto
├── .env                           # Arquivo de configuração de chaves de API e caminhos (não versionado)
├── models/                        # Diretório para modelos locais (ex: small.pt do Whisper)
└── live_captions/
    ├── __init__.py                # Metadados e versão do pacote
    ├── audio.py                   # Captura de áudio de saída do Windows (WASAPI Loopback)
    ├── capture_protection.py      # Integração Win32 para ocultar a janela de capturas de tela
    ├── clipboard.py               # Cópia segura para clipboard via ctypes/Win32 sem travar a thread
    ├── config.py                  # Carregamento de variáveis de ambiente (.env) e configurações
    ├── deepgram.py                # Thread de transcrição contínua via WebSocket da Deepgram
    ├── transcript.py              # Buffer de transcrição (gerencia texto final e texto intermediário)
    ├── ui.py                      # Interface gráfica (PySide6), estilos CSS, eventos de mouse e controles
    └── whisper_local.py           # Thread de transcrição local em tempo real via OpenAI Whisper
```

---

## ⚙️ Pré-requisitos e Instalação

### 1. Requisitos
- **Sistema Operacional**: Windows 10/11 (recomendado para suporte a WASAPI Loopback e proteção de tela).
- **Python**: versão 3.10 ou superior.

### 2. Instalação das Dependências

Crie e ative um ambiente virtual (opcional, porém recomendado):

```bash
python -m venv venv
venv\Scripts\activate  # No Windows
```

Instale os pacotes necessários:

```bash
pip install -r requirements.txt
```

---

## 🔧 Configuração (`.env`)

Crie um arquivo `.env` na raiz do projeto com as seguintes configurações:

```env
# Chave da API Deepgram (necessária para transcrição em nuvem)
DEEPGRAM_API_KEY=sua_chave_deepgram_aqui

# Caminho para o modelo local do Whisper (necessário para o modo Local Whisper)
WHISPER_MODEL_PATH=models/small.pt
```

> 💡 **Nota sobre o Whisper Local**:  
> Se for utilizar o modo local, certifique-se de ter o arquivo de pesos do modelo baixado no caminho configurado (ex: `models/small.pt` ou `models/base.pt`).

---

## 🚀 Como Executar

Execute o arquivo principal:

```bash
python main.py
```

---

## 🖥️ Como Usar a Interface

1. **Seleção de Motor (Engine)**:
   - **Deepgram**: Baixíssima latência (requer internet e chave configurada no `.env`).
   - **Local Whisper**: Processamento local direto na CPU/GPU sem envio de áudio para a internet.
2. **Seleção de Idioma**:
   - Alterne entre **PT** (Português) e **EN** (Inglês) no menu dropdown a qualquer momento.
3. **Controles**:
   - **Pause / Start**: Inicia ou pausa a captura e transcrição de áudio.
   - **Copy**: Copia todo o texto transcrito até o momento para a área de transferência.
   - **Clear**: Limpa o histórico de legendas na tela.
   - **Arrastar e Redimensionar**: Clique e arraste qualquer área da janela para movê-la, ou utilize a alça de redimensionamento no canto inferior direito.
4. **Status de Privacidade (`◈ Hidden from capture`)**:
   - O indicador no cabeçalho confirma se a proteção contra gravação/compartilhamento de tela está ativa.
