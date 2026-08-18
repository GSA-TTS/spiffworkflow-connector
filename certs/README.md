# Custom CA Certificates

Place any custom CA certificates (e.g., Zscaler Root CA) in this directory as `.crt` files.

These will be automatically installed into the Docker container during build, allowing tools like `uv`, `wget`, and `curl` to trust your corporate proxy's TLS interception certificate.

## Usage

If you're behind a corporate proxy (e.g., Zscaler):

1. Export your proxy's root CA certificate as a PEM file
2. Place it in this directory (e.g., `certs/zscaler-root-ca.crt`)
3. Rebuild the container: `docker compose -f dev.docker-compose.yml build`

All `.crt` files in this directory are gitignored.
