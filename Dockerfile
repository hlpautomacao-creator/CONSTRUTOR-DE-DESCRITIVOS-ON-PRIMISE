FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir python-docx psycopg2-binary

COPY guardian_server.py .
COPY builder-descritivo.html .

EXPOSE 5555

CMD ["python", "guardian_server.py"]