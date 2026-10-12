# Certificados de prueba para los tests de TLS

Estos archivos solo sirven para los tests: permiten montar en la propia
máquina (`127.0.0.1`) un servidor HTTPS falso y comprobar cómo se conecta la
ingesta, sin llamar a la API real.

**Las claves privadas (`*.key`) son solo de prueba y no protegen nada.** Están
publicadas en el repositorio a propósito. Nunca las uses para otra cosa.

| Archivo | Qué es |
|---|---|
| `ca.pem` | Autoridad de prueba. Los tests le dicen a la ingesta que confíe en ella. Su clave no se guarda. |
| `localhost.pem`, `localhost.key` | Certificado para `127.0.0.1`, firmado por la autoridad de prueba. Es el «bueno». |
| `other.pem`, `other.key` | Certificado para `otro.example`, firmado por la autoridad de prueba. Sirve para comprobar que se rechaza un nombre que no coincide. |
| `selfsigned.pem`, `selfsigned.key` | Certificado para `127.0.0.1` firmado por sí mismo, no por la autoridad. Sirve para comprobar que se rechaza un certificado no reconocido. |
| `make_certs.sh` | Script que genera todos los anteriores. |

Los certificados son válidos durante unos 100 años, así que no deberían
caducar. Usan claves RSA de 2048 bits y las extensiones que exige la
verificación estricta de Python.

## Regenerarlos

Hace falta el comando `openssl`. Desde la carpeta del proyecto:

```sh
sh tests/fixtures/tls/make_certs.sh
```

El script crea una autoridad nueva y vuelve a firmar todos los certificados.
Después, comprueba que todo sigue funcionando:

```sh
.venv/bin/python -m pytest
```
