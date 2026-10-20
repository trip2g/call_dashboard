FROM golang:1.26 AS builder
ARG TRIP2G_REF=v0.12.0
RUN git clone --depth 1 --branch ${TRIP2G_REF} https://github.com/trip2g/trip2g.git /src
WORKDIR /src
RUN go mod download
RUN CGO_ENABLED=0 go build -o /fleet ./cmd/fleet

FROM alpine:3.22
RUN apk add --no-cache ca-certificates
COPY --from=builder /fleet /fleet
ENTRYPOINT ["/fleet"]
