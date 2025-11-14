ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python and required packages
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-numpy \
    jq

# Install Python packages
RUN pip3 install --break-system-packages --no-cache-dir \
    requests==2.31.0 \
    scipy==1.11.4 \
    pytz==2024.1

# Create app and logs directory
RUN mkdir -p /app/logs

# Copy application files
COPY silo_prediction.py /app/
COPY run.sh /

# Make run.sh executable
RUN chmod a+x /run.sh

CMD ["/run.sh"]
