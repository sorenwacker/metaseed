# Security Policy

## Supported Versions

Metaseed is pre-1.0 and moves fast; only the latest released minor receives
security fixes.

| Version | Supported          |
| ------- | ------------------ |
| 0.12.x  | Yes                |
| < 0.12  | No                 |

## Reporting a Vulnerability

If you discover a security vulnerability in Metaseed, please report it responsibly.

### How to Report

1. **Do not** open a public issue for security vulnerabilities
2. Email the maintainers directly or use GitHub's private vulnerability reporting
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### What to Expect

- Acknowledgment within 48 hours
- Status update within 7 days
- Fix timeline depends on severity

### Scope

Security issues we are interested in:

- Remote code execution
- SQL injection / command injection
- Path traversal
- Authentication/authorization bypass
- Sensitive data exposure
- Cross-site scripting (XSS) in the web UI

### Out of Scope

- Denial of service (DoS) attacks
- Issues requiring physical access
- Social engineering attacks
- Issues in dependencies (report to upstream)

## Security Best Practices

When deploying Metaseed:

- Run behind a reverse proxy in production
- Use HTTPS for all connections
- Keep dependencies updated
- Restrict file system access appropriately
