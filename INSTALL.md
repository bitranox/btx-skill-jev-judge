# Installation Guide

`btx-jev-judge` is a Python 3.10+ command-line tool published on PyPI. It installs two commands,
`jev-judge` and `btx-jev-judge` (and `btx_jev_judge`), which are the same program. You also need a
TypeSafe API key; see [Provide the key](#provide-the-key).

Using the Claude Code plugin instead? See "Install in Claude Code" in [README.md](README.md).

## We recommend `uv`

`uv` is a fast Python package manager written in Rust, and `uvx` runs a tool in a temporary
isolated environment without installing it.

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Run once, nothing installed

```bash
uvx --from btx-jev-judge jev-judge --help
```

The package name and the command differ, so `--from` is needed.

### Install on your PATH

```bash
uv tool install btx-jev-judge
uv tool upgrade btx-jev-judge
```

### As a project dependency

```bash
uv venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
uv pip install btx-jev-judge
```

## pip

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install btx-jev-judge
```

Per-user install without a virtual environment:

```bash
pip install --user btx-jev-judge
```

This respects PEP 668: avoid it on a system Python marked "externally managed", and make sure
`~/.local/bin` is on your PATH.

## pipx

```bash
pipx install btx-jev-judge
pipx upgrade btx-jev-judge
```

## From Git or a local clone

```bash
pip install "git+https://github.com/bitranox/btx-skill-jev"
pip install .                 # from a clone, runtime only
pip install -e ".[dev]"       # from a clone, with the development tools
```

## From build artifacts

```bash
python -m build
pip install dist/btx_jev_judge-*.whl
```

## Provide the key

The key comes from the `TYPESAFE_API_KEY` environment variable, else from
`~/.credentials/typesafe.key`. Get one at https://console.typesafe.ai/keys. To create the file
(mode 600, which is required on POSIX), run this and paste the key in with an editor:

```bash
mkdir -p -m 700 ~/.credentials && install -m 600 /dev/null ~/.credentials/typesafe.key
```

## Verify

```bash
jev-judge --version
jev-judge check-key        # exit 0 and "key: present (...)" when a usable key is found
```

`check-key` never prints the key.
