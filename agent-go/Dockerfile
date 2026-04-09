FROM gcr.io/distroless/base-debian12:nonroot

COPY dgraph-agent /usr/local/bin/dgraph-agent

# Agent needs to read the host filesystem via volume mounts
# Run as nonroot for security — scanner uses read-only mounts
USER nonroot

ENV DGRAPH_LOG_FORMAT=json \
    DGRAPH_LOG_LEVEL=info

EXPOSE 9090

ENTRYPOINT ["/usr/local/bin/dgraph-agent"]
