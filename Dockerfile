FROM python:3.11
WORKDIR /code
COPY wallet_base/requirements.txt /code/
RUN pip install -r requirements.txt
CMD ["gunicorn", "wallet_base.wsgi:application", "-b", "0.0.0.0:8080"]
