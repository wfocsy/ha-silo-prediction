FROM python:3.11-slim

WORKDIR /app

RUN pip install flask pandas numpy scikit-learn mysql-connector-python

COPY run.sh /run.sh
COPY prediction_service.py /app/prediction_service.py

RUN chmod a+x /run.sh

CMD ["/run.sh"]
