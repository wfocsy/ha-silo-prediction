FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir \
    requests==2.31.0 \
    numpy==1.24.3 \
    scipy==1.11.4

# Create logs directory
RUN mkdir -p /app/logs

# Copy application
COPY silo_prediction.py /app/
COPY run.sh /run.sh

RUN chmod +x /run.sh

CMD ["/run.sh"]
