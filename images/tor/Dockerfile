FROM python:3.10-slim-bullseye


RUN apt-get update -y && \
    apt-get install -y tor && \
    rm -rf /var/lib/apt/lists/*

RUN echo "SOCKSPort 0.0.0.0:9050" >> /etc/tor/torrc

EXPOSE 9050
CMD ["tor", "-f", "/etc/tor/torrc"]
