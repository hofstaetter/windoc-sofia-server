FROM psql-base

RUN pip3 install --no-cache-dir astm

CMD ["python", "sofia_server.py"]
