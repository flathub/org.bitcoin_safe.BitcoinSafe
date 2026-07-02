# org.bitcoin_safe.BitcoinSafe

Flathub-style Flatpak packaging for [Bitcoin Safe](https://github.com/andreasgriffin/bitcoin-safe/).

## Maintainer Workflow
# Bitcoin Safe
# Copyright (C) 2026 Andreas Griffin
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of version 3 of the GNU General Public License as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see https://www.gnu.org/licenses/gpl-3.0.html
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#

Run:

```sh
./populate-flathub-manifest-repo.py
```

By default the script writes the generated manifest repo to:

```sh
tools/build-linux/flathub-flatpak/build/generated-repo
```

and then runs local validation:

- `flatpak-builder --show-manifest`
- `flatpak-builder-lint manifest` when `org.flatpak.Builder` is installed
- `flatpak-builder --user --install-deps-from=flathub --repo=repo build-dir org.bitcoin_safe.BitcoinSafe.yml`

Use these flags to skip parts of that default flow:

- `--skip-validate`
- `--skip-lint`
- `--skip-build`

Use this flag to launch the built app after a successful local build:

- `--run-flatpak`

To run the local checks on Ubuntu, install the builder tools and lint helper first:

```sh
sudo apt update
sudo apt install flatpak flatpak-builder
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install flathub org.kde.Platform//6.10 org.kde.Sdk//6.10 com.riverbankcomputing.PyQt.BaseApp//6.10 org.flatpak.Builder
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
- `--app-source-mode local-dir` to make the generated manifest point at that local checkout instead of a release archive
- `--refresh` to explicitly update the checked-in generated SVG and metainfo files first

The generator is the only Flatpak manifest source of truth:

- it defines the Flatpak manifest in Python instead of reading a checked-in YAML manifest
- by default replaces local staged sources with pinned release archives
- replaces build-time dependency resolution with generated, pinned dependency manifests
- relies on `com.riverbankcomputing.PyQt.BaseApp//6.10` for the core PyQt runtime instead of vendoring PyQt into the app
- keeps normal runs side-effect-free by checking tracked generated assets instead of rewriting them

Flathub builds from the checked-in files in this repo, not from Docker.
