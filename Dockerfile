FROM psql-base

RUN pip3 install --no-cache-dir astm

COPY app/ /app/

CMD ["python", "sofia_server.py"]
