#!/bin/sh
# Genera los certificados de prueba de los tests TLS (ver README.md).
# Las claves son SOLO de prueba. Uso: sh tests/fixtures/tls/make_certs.sh
set -eu

cd "$(dirname "$0")"
DAYS=36500   # unos 100 años, para que los tests no fallen al caducar
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

cat > "$WORK/ca.ext" <<'EXT'
basicConstraints = critical, CA:TRUE
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
EXT

server_ext() {
    cat > "$WORK/$1.ext" <<EXT
basicConstraints = CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = $2
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid
EXT
}

# Autoridad de prueba (su clave no se guarda: regenerar crea una nueva).
openssl req -new -newkey rsa:2048 -nodes -keyout "$WORK/ca.key" \
    -subj "/CN=Autoridad de prueba precios-gasolineras" -out "$WORK/ca.csr"
openssl x509 -req -in "$WORK/ca.csr" -signkey "$WORK/ca.key" -days "$DAYS" \
    -sha256 -extfile "$WORK/ca.ext" -out ca.pem

# Certificados de servidor firmados por la autoridad.
signed() {   # nombre, CN, subjectAltName
    server_ext "$1" "$3"
    openssl req -new -newkey rsa:2048 -nodes -keyout "$1.key" -subj "/CN=$2" -out "$WORK/$1.csr"
    openssl x509 -req -in "$WORK/$1.csr" -CA ca.pem -CAkey "$WORK/ca.key" -CAcreateserial \
        -CAserial "$WORK/ca.srl" -days "$DAYS" -sha256 -extfile "$WORK/$1.ext" -out "$1.pem"
}
signed localhost 127.0.0.1 "IP:127.0.0.1"
signed other otro.example "DNS:otro.example"

# Autofirmado, con las mismas extensiones de servidor que localhost.
server_ext selfsigned "IP:127.0.0.1"
sed -i.bak '/authorityKeyIdentifier/d' "$WORK/selfsigned.ext"
openssl req -new -newkey rsa:2048 -nodes -keyout selfsigned.key -subj "/CN=127.0.0.1" \
    -out "$WORK/selfsigned.csr"
openssl x509 -req -in "$WORK/selfsigned.csr" -signkey selfsigned.key -days "$DAYS" \
    -sha256 -extfile "$WORK/selfsigned.ext" -out selfsigned.pem

chmod 644 ./*.pem ./*.key
echo "Certificados de prueba generados en $(pwd)"
