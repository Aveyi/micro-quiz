FROM golang:1.27-alpine AS build

WORKDIR /live

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/live ./cmd/live

FROM alpine:3.22

RUN adduser -D -H -s /sbin/nologin -u 10001 appuser

COPY --from=build /out/live /live

USER 10001
ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:$PORT/health || exit 1

ENTRYPOINT ["/live"]
