FROM psql-base

RUN pip3 install --no-cache-dir astm

RUN mkdir /data
VOLUME /data

RUN mkdir /utils
COPY send.py /utils/
COPY demo_dump.*.dat /utils/

COPY app/ /app/

CMD ["python", "sofia_server.py"]
