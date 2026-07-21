# 1. Usa uma imagem oficial do Python (versão leve)
FROM python:3.11-slim

# 2. Define a pasta de trabalho dentro do container
WORKDIR /app

# 3. Instala dependências do sistema operacional
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# 4. Copia apenas o arquivo de dependências primeiro (otimiza o cache do Docker)
COPY requirements.txt .

# 5. Instala as bibliotecas Python sem salvar cache inútil do pip
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copia todo o código do seu repositório para o container
COPY . .

# 7. Expõe a porta padrão do Streamlit
EXPOSE 8501

# 8. Verificação para o servidor saber se a aplicação está online e saudável
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# 9. Comando que inicia o dashboard
ENTRYPOINT ["streamlit", "run", "main.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]