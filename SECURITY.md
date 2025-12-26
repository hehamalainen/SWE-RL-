# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in SSR Studio, please report it responsibly:

1. **Do not** open a public GitHub issue
2. Email the maintainers directly with details
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will acknowledge receipt within 48 hours and provide a detailed response within 7 days.

## Security Considerations

### Sandbox Execution

SSR Studio executes untrusted code in Docker containers. The following security measures are in place:

- **Network isolation**: Containers have no network access by default
- **Resource limits**: CPU and memory are constrained
- **Non-root execution**: Containers run as non-root users
- **Read-only mounts**: Source code is mounted read-only where possible
- **No privileged mode**: Containers cannot access host devices

### API Security

- Input validation on all endpoints
- Rate limiting enabled by default
- CORS restricted to configured origins

### Secrets Management

- API keys should be provided via environment variables
- Never commit `.env` files with real credentials
- Use `.env.example` as a template

## Best Practices

When deploying SSR Studio:

1. Run behind a reverse proxy (nginx, Traefik)
2. Enable HTTPS
3. Use strong database passwords
4. Regularly update dependencies
5. Monitor container resource usage
6. Review Docker socket access (required for sandbox)
