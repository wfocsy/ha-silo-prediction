ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python and required packages
RUN \
  apk add --no-cache \
    python3 \
    py3-pip \
    py3-numpy \
    py3-pandas \
    py3-scikit-learn && \
  pip3 install --break-system-packages --no-cache-dir \
    flask \
    mysql-connector-python

# Set working directory
WORKDIR /app

# Copy application files
COPY run.sh /run.sh
COPY prediction_service.py /app/prediction_service.py

# Make run script executable
RUN chmod a+x /run.sh

CMD ["/run.sh"]
