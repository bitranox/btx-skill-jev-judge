# Installation Guide

> The CLI stack uses `rich-click`, which bundles `rich` styling on top of click-style ergonomics.

This guide collects every supported method to install `btx_jev_judge`, including
isolated environments and system package managers. Pick the option that matches your workflow.


## We recommend `uv` to install the package

### `uv` = Ultra-fast Python package manager

> lightning-fast replacement for `pip`, `venv`, `pip-tools`, and `poetry`
written in Rust, compatible with PEP 621 (`pyproject.toml`)

### `uvx` = On-demand tool runner

> runs tools temporarily in isolated environments without installing them globally


## Install uv (if not already installed)

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## One-shot run via uvx (no install needed)

```bash
uvx btx_jev_judge@latest --help
```

## Persistent install as CLI tool

```bash
# install the CLI tool (isolated environment, added to PATH)
uv tool install btx_jev_judge

# upgrade to latest
uv tool upgrade btx_jev_judge
```

## Install as project dependency

```bash
uv venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
uv pip install btx_jev_judge
```

## Verify installation

After any install method, confirm the CLI is available:

```bash
btx-jev-judge --version
```

---

## Installation via pip

```bash
# optional, install in a venv (recommended)
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
# install from PyPI
pip install btx_jev_judge
# optional install from GitHub
pip install "git+https://github.com/bitranox/btx_jev_judge"
# optional development install from local
pip install -e ".[dev]"
# optional install from local runtime only:
pip install .
```

## Per-User Installation (No Virtualenv) - from local

```bash
# install from PyPI
pip install --user btx_jev_judge
# optional install from GitHub
pip install --user "git+https://github.com/bitranox/btx_jev_judge"
# optional install from local
pip install --user .
```

> Note: This respects PEP 668. Avoid using it on system Python builds marked as
> "externally managed". Ensure `~/.local/bin` (POSIX) is on your PATH so the CLI is available.

## pipx (Isolated CLI-Friendly Environment)

```bash
# install pipx via pip
python -m pip install pipx
# optional install pipx via apt
sudo apt install python-pipx
# install via pipx from PyPI
pipx install btx_jev_judge
# optional install via pipx from GitHub
pipx install "git+https://github.com/bitranox/btx_jev_judge"
# optional install from local
pipx install .
pipx upgrade btx_jev_judge
# install from Git tag
pipx install "git+https://github.com/bitranox/btx_jev_judge@v1.1.0"
```

## From Build Artifacts

```bash
python -m build
pip install dist/btx_jev_judge-*.whl
pip install dist/btx_jev_judge-*.tar.gz   # sdist
```

## Poetry or PDM Managed Environments

```bash
# Poetry
poetry add btx_jev_judge     # as dependency
poetry install                          # for local dev

# PDM
pdm add btx_jev_judge
pdm install
```

## Install Directly from Git

```bash
pip install "git+https://github.com/bitranox/btx_jev_judge"
```

## System Package Managers (Optional Distribution Channels)

- Use [fpm](https://fpm.readthedocs.io/) to repackage the Python wheel into `.deb` or `.rpm` for distribution via `apt` or `yum`/`dnf`.

All methods register both the `btx_jev_judge` and
`btx-jev-judge` commands on your PATH.
