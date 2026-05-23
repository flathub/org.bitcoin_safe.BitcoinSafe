# org.bitcoin_safe.BitcoinSafe

Flathub-style Flatpak packaging for [Bitcoin Safe](https://github.com/andreasgriffin/bitcoin-safe/releases/tag/2.0.0rc1).

## Maintainer Workflow

Run:

```sh
./populate-flathub-manifest-repo.py
```

By default the generator reads from `https://github.com/andreasgriffin/bitcoin-safe/` and uses the most recently published GitHub release, including prereleases. You can override that with:

- `--release-tag <tag>`
- `--source-repo-url <url>`
- `--local-source-checkout <path>`

The generator treats the upstream Flatpak manifest as the baseline and rewrites only the Flathub-incompatible parts:

- replaces local staged sources with pinned release archives
- replaces build-time dependency resolution with generated, pinned dependency manifests
- removes build-time network assumptions

Flathub builds from the checked-in files in this repo, not from Docker.

## Current Release

- Source repo: `https://github.com/andreasgriffin/bitcoin-safe/`
- Selected tag: `2.0.0rc1`
- Channel: `beta`
- Published: `2026-05-22`
