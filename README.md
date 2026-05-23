# org.bitcoin_safe.BitcoinSafe

Flathub-style Flatpak packaging for [Bitcoin Safe](https://github.com/andreasgriffin/bitcoin-safe/).

## Maintainer Workflow

Run:

```sh
./populate-flathub-manifest-repo.py
```

By default the script also runs local validation after regenerating files:

- `flatpak-builder --show-manifest`
- `flatpak-builder-lint manifest` when `org.flatpak.Builder` is installed
- `flatpak-builder --user --install-deps-from=flathub --repo=repo build-dir org.bitcoin_safe.BitcoinSafe.yml`

Use these flags to skip parts of that default flow:

- `--skip-validate`
- `--skip-lint`
- `--skip-build`

To run the local checks on Ubuntu, install the builder tools and lint helper first:

```sh
sudo apt update
sudo apt install flatpak flatpak-builder
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install flathub org.flatpak.Builder
```

By default the generator reads from `https://github.com/andreasgriffin/bitcoin-safe/` and uses the most recently published GitHub release, including prereleases.

Source selection works like this:

- if you pass `--local-source-checkout`, that local checkout is used for manifests, lockfile, and assets
- otherwise, if you pass `--source-repo-url`, that upstream repo is used
- otherwise, the generator falls back to `https://github.com/andreasgriffin/bitcoin-safe/`

You can override the defaults with:

- `--release-tag <tag>`
- `--source-repo-url <url>`
- `--local-source-checkout <path>`

The generator treats the upstream Flatpak manifest as the baseline and rewrites only the Flathub-incompatible parts:

- replaces local staged sources with pinned release archives
- replaces build-time dependency resolution with generated, pinned dependency manifests
- removes build-time network assumptions

Flathub builds from the checked-in files in this repo, not from Docker.
