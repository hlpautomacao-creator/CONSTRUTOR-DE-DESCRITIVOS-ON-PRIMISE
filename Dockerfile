FROM python:3.11-slim

WORKDIR /app

# Instalar Node.js e dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Instalar dependências Python
RUN pip install --no-cache-dir python-docx psycopg2-binary

# Instalar pacote docx do Node.js globalmente
RUN npm install -g docx

# Copiar arquivos da aplicação
COPY guardian_server.py .
COPY builder-descritivo.html .
COPY generate_docx.js .

EXPOSE 5555

CMD ["python", "guardian_server.py"]
