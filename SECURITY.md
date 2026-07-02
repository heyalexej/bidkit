# Security Policy

bidkit handles OAuth client secrets, user refresh tokens, and private signing keys, so we
take vulnerability reports seriously.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

- Preferred: [GitHub private vulnerability reporting](https://github.com/heyalexej/bidkit/security/advisories/new)
- Alternatively: email heyalexej@gmail.com with "bidkit security" in the subject

You will get an acknowledgement within a few days. Please include a reproduction or enough
detail to assess impact, and give us a reasonable window to ship a fix before public
disclosure.

## Supported versions

Only the latest release receives security fixes while the project is on 0.x.

## Scope notes

- bidkit never transmits credentials anywhere except eBay's own OAuth and API endpoints.
- Tokens are cached in memory by default; if you build a persistent `TokenCache`, protecting
  it is your application's responsibility.
- Vulnerabilities in eBay's APIs themselves should be reported to
  [eBay's security program](https://pages.ebay.com/securitycenter/security_researchers.html),
  not here.
