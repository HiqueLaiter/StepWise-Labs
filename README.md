# 🦵 StepWise Analytics

Bem-vindo ao **StepWise Analytics**! Este dashboard foi desenvolvido para auxiliar profissionais da saúde na visualização e análise de dados cinemáticos de reabilitação.

O sistema traduz dados brutos (capturados por visão computacional via KinesiOS ou Brainn_XR) em indicadores objetivos do **progresso terapêutico**, facilitando a tomada de decisão clínica.

---

## 🛠️ Pré-requisitos

Antes de começar, certifique-se de que você tem instalado no seu computador:
1. **Python** (versão 3.8 ou superior).
   * **Como verificar:** Abra o terminal (ou Prompt de Comando) e digite o seguinte comando e aperte Enter:
     ```bash
     python --version
     ```
     *(Se o terminal responder com algo como `Python 3.10.x`, você já tem o Python instalado. Se aparecer uma mensagem de erro ou abrir a loja de aplicativos do Windows, será necessário baixar e instalar o Python pelo site oficial).*
2. Um editor de código, recomendamos o **VS Code** (Visual Studio Code).

---

## 🚀 Como instalar e rodar o projeto

Siga o passo a passo abaixo no terminal do seu editor de código (VS Code):

### 1. Baixe o projeto

Você pode baixar o projeto de duas formas:

* **Pelo navegador:** Clique no botão verde `<> Code` no topo desta página e selecione **"Download ZIP"**. Extraia a pasta no seu computador e abra essa pasta no VS Code.
* **Pelo Terminal (Git):**
  
```bash
git clone https://github.com/HiqueLaiter/StepWise-Labs.git

```

### 2. Abra a pasta no terminal

No terminal do VS Code, navegue até a pasta onde o projeto foi salvo:

```bash
cd caminho/para/a/pasta/StepWise-Labs

```

*(Exemplo: `cd Documentos/StepWise-Labs`)*

### 3. Crie um ambiente virtual

O ambiente virtual isola o projeto para não interferir em outros programas do seu computador. Rode o comando:

```bash
python -m venv .venv

```

*(Nota: no Mac/Linux, você pode precisar usar `python3 -m venv .venv`)*

### 4. Ative o ambiente virtual

Dependendo do sistema operacional ou terminal que você está usando, o comando muda um pouco. Escolha o seu abaixo:

* **Prompt de Comando (CMD - Windows):**
```cmd
.venv\Scripts\activate

```


* **PowerShell (Windows):**
```powershell
.\.venv\Scripts\Activate.ps1

```


* **Git Bash (Windows) ou Terminal (Mac/Linux):**
```bash
source .venv/Scripts/activate

```



*(Se der certo, você verá um `(.venv)` aparecendo no início da linha do seu terminal).*

### 5. Instale as dependências

Agora, vamos instalar as bibliotecas necessárias para o painel funcionar (este passo **pode demorar alguns minutos**, aguarde finalizar):

```bash
pip install -r requirements.txt

```

### 6. Inicie o Dashboard!

Com tudo instalado, rode o comando abaixo para abrir o sistema:

```bash
streamlit run main.py

```

Uma nova aba será aberta automaticamente no seu navegador de internet com o dashboard pronto para uso! 🎉

---

## 📋 Como usar o Dashboard

1. **Configuração Clínica:** Na barra lateral esquerda, defina os limiares clínicos de flexão (em graus) esperados para o quadril e o joelho do paciente.
2. **Modo de Análise:** Escolha se deseja analisar uma sessão única (bilateral ou unilateral) ou fazer uma **Comparação** (Sessão Inicial vs. Sessão Final).
3. **Upload dos Dados:** Arraste e solte o arquivo da sessão (formatos `.CSV`, `.XLSX` ou `.XLSM`). O sistema detecta automaticamente se os dados vieram do KinesiOS ou do Brainn_XR.
4. **Análise de Resultados:** Navegue pelos gráficos gerados automaticamente e consulte a aba **📖 Guia de métricas** para entender como interpretar a Amplitude de Movimento e a Consistência Temporal.

---

### ⚠️ Atenção

*Para fechar o sistema quando terminar de usar, basta ir ao terminal do VS Code e apertar `Ctrl + C`.*

---
