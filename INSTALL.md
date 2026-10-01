# Installation Guide

`btx-skill-jev-judge` is a Python 3.10+ command-line tool published on PyPI. It installs three command names
for one program: `jev-judge`, `btx-skill-jev-judge` and `btx_skill_jev_judge`. You also need a
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
uvx --from btx-skill-jev-judge jev-judge --help
```

The package name and the command differ, so `--from` is needed.

### Install on your PATH

```bash
uv tool install btx-skill-jev-judge
uv tool upgrade btx-skill-jev-judge
```

### As a project dependency

```bash
uv venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
uv pip install btx-skill-jev-judge
```

## pip

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install btx-skill-jev-judge
```

Per-user install without a virtual environment:

```bash
pip install --user btx-skill-jev-judge
```

This respects PEP 668: avoid it on a system Python marked "externally managed", and make sure
`~/.local/bin` is on your PATH.

## pipx

```bash
pipx install btx-skill-jev-judge
pipx upgrade btx-skill-jev-judge
```

## From Git or a local clone

```bash
pip install "git+https://github.com/bitranox/btx-skill-jev-judge"
pip install .                 # from a clone, runtime only
pip install -e ".[dev]"       # from a clone, with the development tools
```

## From build artifacts

```bash
python -m build
pip install dist/btx_skill_jev_judge-*.whl
```

## Provide the key

The key comes from an exported `TYPESAFE_API_KEY`, else from a `.env` in the current directory or a
parent, else from `~/.credentials/typesafe.key` (see [SECURITY.md](SECURITY.md)). Get one at https://console.typesafe.ai/keys. To create the file
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
