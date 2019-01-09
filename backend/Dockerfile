FROM tiangolo/uwsgi-nginx-flask:python3.7

RUN apt update
RUN apt-get install -y postgresql-client
RUN apt-get install -y python3-psycopg2
COPY requirements.txt /tmp/
RUN pip install -U pip
RUN pip install -r /tmp/requirements.txt

COPY ./app /app
