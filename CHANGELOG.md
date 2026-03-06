# Changelog

## [0.2.11] - 2026-03-06

- Add SSL/TLS CA bundle support for environments with Netskope client SSL inspection
- New `config set-ca-bundle` command with auto-detection of Netskope CA certificates
- Support `NETSKOPE_CA_BUNDLE`, `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE` env vars for CA bundle resolution
- Add `SSLError` exception with actionable platform-specific fix suggestions
- `doctor` command now checks CA bundle configuration and detects Netskope CA certs
- `status` command now passes cookies for session-based auth in async API calls

## [0.2.10] - 2026-03-06

- Fix repository URL typo in PyPI metadata

## [0.2.9] - 2026-03-06

- Fix API endpoint corrections: infrastructure events, transaction event metrics, notification delivery settings, publisher upgrade profiles, URL list creation, and NSIQ URL lookup/recategorize request bodies
- Add verbose logging support (-v for INFO, -vv for DEBUG) with HTTP request/response logging
- Improve error handling: detect API-level errors in 200 responses and raise typed exceptions
- Add NETSKOPE_PROFILE env var support for profile resolution
- Replace typer.Exit with typed ConfigError exceptions for missing configuration
- Add --offset alias for --start-index in user list command
- Fix auth token-info to use config-aware token resolution

## [0.2.8] - 2026-03-06

- Add Homebrew tap installation support (`brew tap netskopeoss/tap && brew install netskope`)
- Add Homebrew install instructions to README

## [0.2.7] - 2026-03-05

- Initial public release on PyPI
