FROM psql-base

RUN pip3 install --no-cache-dir astm

COPY app/ /app/

RUN mkdir /data
VOLUME /data

CMD ["python", "sofia_server.py"]
