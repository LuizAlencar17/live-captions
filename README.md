# 🎙️ Live Captions

Uma aplicação desktop moderna de **legendas em tempo real** para o áudio do computador, projetada para entrevistas, reuniões, vídeos e acessibilidade. O aplicativo captura o áudio do sistema (saída de alto-falantes/fones) e exibe transcrições em tempo real em uma janela flutuante com proteção de privacidade contra compartilhamento de tela.

---

## ✨ Principais Funcionalidades

- **🔊 Captura de Áudio Interno (Loopback)**:
  - Captura o áudio emitido pelo computador usando a biblioteca `SoundCard` (WASAPI no Windows; PulseAudio ou PipeWire com compatibilidade PulseAudio no Linux), sem necessidade de microfones externos ou cabos de áudio virtuais.

- **🤖 Motores de Transcrição Flexíveis**:
  - **Deepgram (Nuvem)**: Transcrição em tempo real ultra-rápida de baixa latência usando o modelo `nova-3` via WebSocket com suporte a resultados parciais (*interim results*).
  - **OpenAI Whisper (Local/Offline)**: Processamento 100% local no próprio computador, ideal para privacidade total ou uso offline, com janelas deslizantes e algoritmo de remoção de sobreposição (*overlap deduplication*).

- **🛡️ Proteção de Privacidade contra Captura de Tela**:
  - No Windows, utiliza a API nativa (`SetWindowDisplayAffinity` com `WDA_EXCLUDEFROMCAPTURE`) para **esconder a janela de legendas** de compartilhamentos de tela e gravadores (OBS, Discord, Zoom, Teams, Google Meet, etc.). Essa proteção não está disponível no Linux; a janela poderá aparecer em capturas de tela e compartilhamentos.

- **🎨 Interface Flutuante e Moderna (PySide6 / Qt)**:
  - Janela sem bordas (*frameless*), translúcida (*dark glassmorphism*), *Always on Top* (sempre no topo), redimensionável e arrastável.
  - Indicador de status de conexão e privacidade, além de cópia rápida para a área de transferência usando a API nativa de cada plataforma.

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
    ├── audio.py                   # Captura de áudio de saída e microfone
    ├── capture_protection.py      # Proteção de captura de tela (disponível apenas no Windows)
    ├── clipboard.py               # Cópia para a área de transferência
    ├── config.py                  # Carregamento de variáveis de ambiente (.env) e configurações
    ├── deepgram.py                # Thread de transcrição contínua via WebSocket da Deepgram
    ├── transcript.py              # Buffer de transcrição (gerencia texto final e texto intermediário)
    ├── ui.py                      # Interface gráfica (PySide6), estilos CSS, eventos de mouse e controles
    └── whisper_local.py           # Thread de transcrição local em tempo real via OpenAI Whisper
```

---

## ⚙️ Pré-requisitos e Instalação

### 1. Requisitos
- **Sistema Operacional**: Windows 10/11 ou Linux desktop. A captura do áudio do sistema no Linux requer PulseAudio ou PipeWire com `pipewire-pulse`; a proteção contra captura de tela só funciona no Windows.
- **Python**: versão 3.10 ou superior.

No Ubuntu/Debian, instale os pré-requisitos do sistema e, se usar PipeWire, habilite a compatibilidade PulseAudio:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip ffmpeg libpulse0
# Para PipeWire, instale/ative também o pacote pipewire-pulse da sua distribuição.
```

Se `python3 -m venv` informar que `ensurepip` não está disponível, instale o pacote correspondente à versão do Python (por exemplo, `sudo apt install python3.12-venv`) e crie o ambiente virtual novamente.

### 2. Instalação das Dependências

Crie e ative um ambiente virtual (recomendado):

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux
# Windows PowerShell: .venv\Scripts\Activate.ps1
```

Instale os pacotes necessários:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
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

No Linux, se o áudio do computador não for encontrado, confirme que o servidor PulseAudio está ativo ou que `pipewire-pulse` está instalado e em execução. O modo **Mic** pode ser usado para verificar a captura do microfone independentemente do monitor de saída.

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
