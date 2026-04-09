FROM gcr.io/distroless/base-debian12:nonroot
COPY dgraph-proxy /usr/local/bin/dgraph-proxy
VOLUME /data
ENV DGPROXY_DATA_DIR=/data \
    DGPROXY_LISTEN_ADDR=0.0.0.0:7433 \
    DGPROXY_METRICS_ADDR=0.0.0.0:9091 \
    DGPROXY_LOG_FORMAT=json
EXPOSE 7433 9091
ENTRYPOINT ["/usr/local/bin/dgraph-proxy"]
