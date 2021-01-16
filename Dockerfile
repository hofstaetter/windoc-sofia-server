FROM psql-base

RUN pip install astm



CMD ["python", "sofia_server.py"]
