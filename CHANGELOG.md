# Changelog

## 0.1.0 (2026-07-02)


### ⚠ BREAKING CHANGES

* **client:** the undocumented client.request()/client.stream() passthroughs are now private; call the typed generated methods, or client._transport for low-level needs.
* **transport:** requests outside eBay's signed set no longer carry signature headers when EbaySigningConfig is set. Use EbaySigningConfig(sign_all=True) to restore blanket signing if eBay expands its signature requirements before the SDK updates.
* import bidkit instead of ebay_sdk; install bidkit instead of ebay-sdk.

### Features

* **auth:** add OAuth authorization-code exchange ([a2e8db6](https://github.com/heyalexej/bidkit/commit/a2e8db6d68e830af21a6b798d99c6a242e3040be))
* **auth:** add persistent FileTokenCache ([e77d6a5](https://github.com/heyalexej/bidkit/commit/e77d6a5b8609c8b9b874463b627f91c122eb5196))
* **client:** scoped config overrides via with_options() ([e5be066](https://github.com/heyalexej/bidkit/commit/e5be06652d94cc84aa13eb1c53599d1df64a5530))
* **config:** load ebay-cli style config files ([495d6ac](https://github.com/heyalexej/bidkit/commit/495d6ace368ddc71b88ae1c0831e338474cc4c98))
* expose __version__ ([da90d90](https://github.com/heyalexej/bidkit/commit/da90d90ef9ac50392b6443e23ece5186ff7a7dd5))
* **generator:** accept ints for limit/offset query params ([351819c](https://github.com/heyalexej/bidkit/commit/351819c911ce180344faca7df5e44c2f10dd636e))
* **generator:** clean and trim generated documentation text ([08e76bb](https://github.com/heyalexej/bidkit/commit/08e76bbc9f306a530bd29a124efdcc8560880468))
* **generator:** drop content-type/language params; derive them automatically ([9fbf679](https://github.com/heyalexej/bidkit/commit/9fbf679b615d1669b0def54272e48875b1cef683))
* **generator:** emit full method docstrings wrapped as multi-line blocks ([bfea77d](https://github.com/heyalexej/bidkit/commit/bfea77dc919f421161f139b85e0d204b30fb3e99))
* **models:** open enums so unknown eBay values don't fail validation ([139499d](https://github.com/heyalexej/bidkit/commit/139499de0f1d90976c478f3662f7a75ef20d7cde))
* **notifications:** verify inbound eBay push signatures ([2312a5b](https://github.com/heyalexej/bidkit/commit/2312a5b135aa47523169ba6bf01c668006ba3c9b))
* **pagination:** add auto-paging helpers for list endpoints ([e8976b8](https://github.com/heyalexej/bidkit/commit/e8976b8971d75ed86fb979569da0c8b738bd70e1))
* **pagination:** support responses that nest paging in a pagination object ([58d14ae](https://github.com/heyalexej/bidkit/commit/58d14ae01580aada814cbfa44eff1bfb863ce6e8))
* rename package to bidkit ([8004e0e](https://github.com/heyalexej/bidkit/commit/8004e0e40ed59137f342825e7ef7ed4632633857))
* **scripts:** --write-config persists minted tokens and expiries ([8d015b1](https://github.com/heyalexej/bidkit/commit/8d015b1b51b3ca3b1e0dbed47ed7014cbb67966b))
* **scripts:** add interactive CLI for the OAuth consent flow ([2a08bce](https://github.com/heyalexej/bidkit/commit/2a08bcef4b1d6c067f905d1ec46ce9e429b9107c))
* **signing:** add eBay digital-signature support for the Finances API ([8daca6c](https://github.com/heyalexej/bidkit/commit/8daca6c94e007f431333aa2cf2db14ea544534ba))
* **transport:** add structured logging for requests, retries, and refreshes ([1f97b4e](https://github.com/heyalexej/bidkit/commit/1f97b4e74527f5f4d0a3eda4b897ba0aa2cb6d74))
* **transport:** retry transient responses with rate-limit awareness ([f6dc107](https://github.com/heyalexej/bidkit/commit/f6dc107d1b20aafd2f15bcaef9e916c58b6c8897))


### Bug Fixes

* **auth:** coalesce concurrent token refreshes behind a per-key lock ([f48f8b3](https://github.com/heyalexej/bidkit/commit/f48f8b32ddb12e963fdc33e76cdd70f34fd74878))
* **auth:** harden FileTokenCache against foreign files and concurrency ([821ee3a](https://github.com/heyalexej/bidkit/commit/821ee3a649bf07c6af356fcbaf31c6c75fa2a491))
* **config:** tolerant signing-key pickup, sandbox parsing, explicit optional timeout ([6674822](https://github.com/heyalexej/bidkit/commit/6674822c73101782e3349c21f93509aae0e07138))
* **generator:** complete the signing allowlist and stop eating literal angle-bracket prose ([9a108bd](https://github.com/heyalexej/bidkit/commit/9a108bd92f1515076a4a844816f300b80259c5b4))
* normalize generated enum schemas ([a656567](https://github.com/heyalexej/bidkit/commit/a6565671ac03e5551920cc0e59367293e8db7c5e))
* **notifications:** fetch public keys with application credentials ([6d36f1b](https://github.com/heyalexej/bidkit/commit/6d36f1b855f14b362555fa03793157b8adb2cb2d))
* **packaging:** correct description and complete PyPI metadata ([028f64c](https://github.com/heyalexej/bidkit/commit/028f64c8b9d361e0e4a893882fcf2b29c5b38574))
* **scripts:** guard sandbox/prod keyset mismatch and add non-interactive code input ([ef81127](https://github.com/heyalexej/bidkit/commit/ef81127bdb51c0027ee0887f8f32d0ab66ff4cb1))
* **scripts:** restore the missing-scopes guard and the maintainer smoke bootstrap ([e429ac0](https://github.com/heyalexej/bidkit/commit/e429ac05e88ac333dd9d7aaa4e4a1283556589aa))
* tenant-safe token cache, http-client ownership, schemaless GET typing ([b514e10](https://github.com/heyalexej/bidkit/commit/b514e1041a18767ee05d6a1879e35fa2a07b3e59))
* **transport:** re-fetch the auth header on each retry attempt ([d03703d](https://github.com/heyalexej/bidkit/commit/d03703db7a02832b633e52682d2fe62a777f2259))
* **transport:** sign only operations that eBay requires signatures for ([be215e4](https://github.com/heyalexej/bidkit/commit/be215e428afae4c6246929de452cd941b94239a3))


### Performance Improvements

* lazy-load generated model modules and defer Pydantic builds ([230a985](https://github.com/heyalexej/bidkit/commit/230a98580f3a880d036b8c8f8878325029dd58fa))


### Documentation

* add contributing guide with conventional-commit policy ([d03e3a6](https://github.com/heyalexej/bidkit/commit/d03e3a63a32037c6b9f90e3ce3b8b58bd6aeeac0))
* add mkdocs site ([6235b91](https://github.com/heyalexej/bidkit/commit/6235b9155e34be16b35a330f3462c615846f3492))
* add NOTICE and eBay attribution/disclaimer ([7f3f845](https://github.com/heyalexej/bidkit/commit/7f3f845ca0d201db383d32aeb2ac2b11ec97b37b))
* add security policy, code of conduct, and issue templates ([5a86dcd](https://github.com/heyalexej/bidkit/commit/5a86dcd544784dd83b597134a07815774777a598))
* **examples:** add config and signing-key templates for the scripts ([fbb0120](https://github.com/heyalexej/bidkit/commit/fbb0120c8c51fd35cd3de23df27e004f70a149fe))
* **examples:** add runnable usage examples ([38b96b1](https://github.com/heyalexej/bidkit/commit/38b96b15993582b39879c61921cd4840fd1a6218))
* **readme:** add implementation status overview of all APIs and versions ([05469d4](https://github.com/heyalexej/bidkit/commit/05469d42884ea69dcc4f743d6eabd3aef13b7c6b))
* **readme:** document the two rate-limit lookups and their token types ([b82ba84](https://github.com/heyalexej/bidkit/commit/b82ba84d78f8e28d906c98823891912ca21294c9))
* **readme:** document with_options and rate-limit lookups ([fb7cf92](https://github.com/heyalexej/bidkit/commit/fb7cf92e88b505fa9e13ab8a97cb0d494c20ff0e))
* **readme:** restructure around install + quickstart ([ea749f8](https://github.com/heyalexej/bidkit/commit/ea749f86caa1196cc90fae1dd5369f5284540bdd))
* seed changelog ([932c933](https://github.com/heyalexej/bidkit/commit/932c933ef9862c341d482467f5ea9a1b179af0b3))


### Code Refactoring

* **client:** tighten the public surface ([79e5858](https://github.com/heyalexej/bidkit/commit/79e585860cf9899193d1e71008439cf6d9518b11))

## Changelog

All notable changes to bidkit are documented here. The format follows
[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) and entries are
generated by [release-please](https://github.com/googleapis/release-please); versioning is
[SemVer](https://semver.org/) with 0.x semantics (see CONTRIBUTING.md).

No releases yet — 0.1.0 will be the first published version, covering the initial SDK:
41 eBay REST APIs / 455 typed operations, sync + async clients, OAuth with cached refresh,
retries, pagination helpers, and Finances API digital signatures.
