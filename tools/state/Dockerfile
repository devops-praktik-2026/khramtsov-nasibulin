FROM golang:1.24.8-bookworm AS build
ENV CGO_ENABLED=0 GOBIN=/out
RUN go install github.com/minio/minio@RELEASE.2025-10-15T17-29-55Z \
    && go install github.com/minio/mc@RELEASE.2025-08-13T08-35-41Z

FROM debian:12-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /out/minio /out/mc /usr/local/bin/
CMD ["minio", "server", "/data", "--console-address", ":9001"]
