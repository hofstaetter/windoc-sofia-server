FROM psql-base

COPY requirements.txt /
RUN pip3 install --no-cache-dir -r /requirements.txt

RUN mkdir /data
VOLUME /data

RUN mkdir /utils
ADD examples /utils
COPY send.py /utils

COPY app/ /app/

CMD ["python", "sofia_server.py"]
