# Configuration

`jev-judge run` and `jev-judge summarize` read their defaults from a layered configuration. This
page lists every key, the layers it can come from and how they are ranked. `check-key` does not
read the configuration at all.

## Precedence

Highest wins:

1. A command-line flag (`--rate`, `--band`, ...). A flag left out falls back to the layers below.
2. Environment variables.
3. `.env` files.
4. User, host and application configuration files.
5. The defaults shipped in the package.

Layers 2 to 5 are the ones `lib_layered_config` merges, in the order
`defaults -> app -> host -> user -> dotenv -> env`. `jev-judge config` prints the merged result;
`--section judge` or `--section summary` narrows it and `--format json` makes it machine-readable.

## The `[judge]` section

Settings of `jev-judge run`.

| Key        | Type    | Default        | Constraint  | Flag         | Meaning                                                                                   |
|------------|---------|----------------|-------------|--------------|-------------------------------------------------------------------------------------------|
| `rate`     | `float` | `20.0`         | `> 0`       | `--rate`     | Requests per second across all workers                                                    |
| `workers`  | `int`   | `8`            | `>= 1`      | `--workers`  | Items judged concurrently                                                                 |
| `attempts` | `int`   | `4`            | `1` to `10` | `--attempts` | Tries per judgment                                                                        |
| `timeout`  | `float` | `30.0`         | `> 0`       | `--timeout`  | Seconds per request phase (connect, read, write, pool wait), not a whole-request deadline |
| `cap`      | `int`   | `60000`        | `>= 100`    | `--cap`      | Longest string, in characters, sent                                                       |
| `model`    | `str`   | `"jev-latest"` | non-empty   | `--model`    | `jev-latest`, or a pinned `jev-x.y.z`                                                     |

Jev's documented limit is 40 requests per second; the default stays well under it. A string longer
than `cap` keeps its head and tail with a marker in between.

## The `[summary]` section

Settings of `jev-judge summarize`.

| Key              | Type    | Default | Constraint | Flag               | Meaning                                                         |
|------------------|---------|---------|------------|--------------------|-----------------------------------------------------------------|
| `band_low`       | `float` | `0.2`   | `0` to `1` | `--band LOW HIGH`  | A `noul` strictly above this and below `band_high` is uncertain |
| `band_high`      | `float` | `0.8`   | `0` to `1` | `--band LOW HIGH`  | Upper edge of the uncertain band                                |
| `min_confidence` | `float` | `0.6`   | `0` to `1` | `--min-confidence` | A choice or score below this confidence is uncertain            |

`band_low` must be below `band_high`. `--band` sets both edges at once.

## The API key is not a setting

The key comes from an exported `TYPESAFE_API_KEY` variable, else from a `.env` file in the current
directory or a parent (see [`.env` files](#env-files)), else from `~/.credentials/typesafe.key`. Both models behind these sections reject unknown keys, so an entry
such as `judge.api_key`, or any other key not listed above, is refused with exit code 78 and
`Error: judge.api_key: Extra inputs are not permitted`. This is deliberate: it keeps the key out of
files that are copied, committed and deployed. See [SECURITY.md](SECURITY.md).

An invalid value is refused the same way, naming the key and the reason but never the value:
`Error: judge.rate: Input should be greater than 0`. The same range violation given as a flag
exits 2 and names the flag.

## Environment variables

An environment variable is the prefix `BTX_SKILL_JEV_JUDGE___` (three underscores), then the section,
two underscores, then the key, in upper case:

```bash
BTX_SKILL_JEV_JUDGE___JUDGE__RATE=5
BTX_SKILL_JEV_JUDGE___JUDGE__MODEL=jev-1.13.0
BTX_SKILL_JEV_JUDGE___SUMMARY__BAND_LOW=0.3
```

Check that one takes effect:

```bash
BTX_SKILL_JEV_JUDGE___JUDGE__RATE=5 jev-judge config --section judge --format json
```

Values are coerced: `true`/`false` become booleans, `null`/`none` become null, and numbers become
`int` or `float`.

## `.env` files

A `.env` file in the working directory or a parent is read without the prefix, as
`SECTION__KEY=value`:

```bash
JUDGE__WORKERS=3
SUMMARY__MIN_CONFIDENCE=0.7
```

`--env-file FILE` names one `.env` file for the configuration values above, instead of searching
upward for them. It does not apply to `TYPESAFE_API_KEY` or `JEV_JUDGE_BASE_URL`: at startup the
logging setup separately loads a `.env` from the current directory or any parent into the process
environment, without overriding variables that are already exported, and the key lookup reads that
environment. So a `.env` there can supply the key even when `--env-file` is given, an exported
`TYPESAFE_API_KEY` wins over the `.env` value, and a key that sits only in the `--env-file` file is
not found. A key from a `.env` beats `~/.credentials/typesafe.key`; `jev-judge check-key` shows the
source. See [.env.example](.env.example) and [SECURITY.md](SECURITY.md).

## Configuration files

Files are TOML, YAML or JSON, named `config.toml` (and so on), with an optional `config.d/`
directory beside them whose files are merged in name order.

| Layer       | Linux                            | macOS                                                         |
|-------------|----------------------------------|---------------------------------------------------------------|
| application | `/etc/xdg/btx-skill-jev-judge/`  | `/Library/Application Support/bitranox/btx_skill_jev_judge/`  |
| user        | `~/.config/btx-skill-jev-judge/` | `~/Library/Application Support/bitranox/btx_skill_jev_judge/` |

Windows uses the equivalent per-user and machine-wide application-data directories. A file only
needs the keys it changes:

```toml
[judge]
rate = 10.0
workers = 4

[summary]
band_low = 0.3
band_high = 0.7
```

`jev-judge config-deploy --target user` writes the shipped defaults to the user directory as a
starting point (`--target app` and `--target host` need privileges; `--force` overwrites existing
files). `jev-judge config-generate-examples --destination DIR` writes commented example files to a
directory of your choice.

## Command-line overrides and profiles

- `--set SECTION.KEY=VALUE` (repeatable, before the command) overrides one key for this run, for
  example `jev-judge --set judge.attempts=2 run ...`.
- `--profile NAME` loads the configuration of a named profile (a sub-directory of each layer), for
  example `production` or `test`. Names are ASCII letters, digits, `-` and `_`, up to 64 characters.

## Errors

| Situation                                                       | Exit | stderr                             |
|-----------------------------------------------------------------|------|------------------------------------|
| A configuration file or `.env` cannot be read or parsed         | 78   | `Error: <reason>`                  |
| An unknown key, or a value outside its constraint, in a section | 78   | `Error: <section>.<key>: <reason>` |
| `band_low` is not below `band_high`                             | 78   | `Error: summary: <reason>`         |
| A flag outside its constraint                                   | 2    | `jev-judge: --<flag>: <reason>`    |

Exit 78 applies to `run` and `summarize`; `check-key` still works while the configuration is
broken. Under `--json-bare` these errors still print `{"error": "<reason>"}` on stdout.

## Other settings

- `JEV_JUDGE_BASE_URL` points the client at another API root, but only when its host is
  loopback (`localhost`, `127.0.0.1`, `::1`). Any other value is ignored and the public endpoint is
  used. It exists so tests can talk to a local stub; it is not a configuration key.
- The `[lib_log_rich]` section configures logging. Every key, with its default, is documented in
  `src/btx_skill_jev_judge/adapters/config/defaultconfig.d/90-logging.toml` and `.env.example`.
- The `[lib_layered_config]` section controls the permissions `config-deploy` sets; see
  `src/btx_skill_jev_judge/adapters/config/defaultconfig.d/40-layered-config.toml`.
