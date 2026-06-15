# --- Build stage ---
FROM golang:1.22-alpine AS builder

WORKDIR /app

COPY go.mod go.sum* ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /healthchecker ./cmd/healthchecker

# --- Runtime stage ---
FROM alpine:3.20

RUN addgroup -S app && adduser -S app -G app
WORKDIR /home/app

COPY --from=builder /healthchecker /usr/local/bin/healthchecker

USER app

ENTRYPOINT ["/usr/local/bin/healthchecker"]
