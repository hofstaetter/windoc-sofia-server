FROM psql-base

RUN pip3 install --no-cache-dir astm

RUN mkdir /data
VOLUME /data

COPY app/ /app/

CMD ["python", "sofia_server.py"]
