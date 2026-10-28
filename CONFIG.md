# Configuration

`jev-judge run` and `jev-judge summarize` read their defaults from a layered configuration. This
page lists every key, the layers it can come from and how they are ranked. `check-key` does not
read the configuration at all.

## Precedence

Highest wins:

1. A command-line flag (`--rate`, `--band`, ...). A flag left out falls back to the layers below.
2. `--set SECTION.KEY=VALUE` (see [Command-line overrides](#command-line-overrides-and-profiles)).
3. Environment variables.
4. `.env` files.
5. User, host and application configuration files.
6. The defaults shipped in the package.

Layers 3 to 6 are the ones `lib_layered_config` merges, in the order
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
directory or a parent (see [`.env` files](#env-files)), else from `~/.credentials/typesafe.key`.
Both models behind these sections reject unknown keys. `jev-judge run` validates `[judge]`, so an
entry such as `judge.api_key`, or any other key not listed above, makes it exit with code 78 and
`Error: judge.api_key: Extra inputs are not permitted`; `jev-judge summarize` validates `[summary]`
the same way. This is deliberate: it keeps the key out of files that are copied, committed and
deployed. See [SECURITY.md](SECURITY.md). `jev-judge config` checks both sections: it shows the
configuration first, an `api_key` value as `***REDACTED***`, then exits 78 with the same
`Error:` line for each problem.

An invalid value is refused the same way, by the command whose section it is, naming the key and
the reason but never the value: `Error: judge.rate: Input should be greater than 0`. The same range
violation given as a flag exits 2 and names the flag.

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

Only one `.env` is read for configuration values: the first found in the working directory or a
parent. When there is none, a `.env` in the user configuration directory is read instead:
`$XDG_CONFIG_HOME/btx-skill-jev-judge/.env` (default `~/.config/btx-skill-jev-judge/.env`) on
Linux, `~/Library/Application Support/bitranox/btx-skill-jev-judge/.env` on macOS and
`%APPDATA%\bitranox\btx-skill-jev-judge\.env` on Windows (under `profile/<NAME>/` with
`--profile`). That file supplies configuration values only, never `TYPESAFE_API_KEY`.

`--env-file FILE` names one `.env` file for the configuration values above, instead of searching
for them. It does not apply to `TYPESAFE_API_KEY` or `JEV_JUDGE_BASE_URL`: at startup the
logging setup separately loads a `.env` from the current directory or any parent into the process
environment, without overriding variables that are already exported, and the key lookup reads that
environment. So a `.env` there can supply the key even when `--env-file` is given, an exported
`TYPESAFE_API_KEY` wins over the `.env` value, and a key that sits only in the `--env-file` file is
not found. A key from a `.env` beats `~/.credentials/typesafe.key`; `jev-judge check-key` shows the
source. See [.env.example](.env.example) and [SECURITY.md](SECURITY.md).

## Configuration files

The application and user layers each read `config.toml` from their directory, plus an optional
`config.d/` beside it whose `.toml`, `.yaml`/`.yml` and `.json` files are merged in name order. A
YAML or JSON file is read only inside `config.d/`; a `config.yaml` or `config.json` next to
`config.toml` is ignored. The host layer is one TOML file named after the machine's hostname.

| Layer       | Linux                                                | macOS                                                                             | Windows                                                            |
|-------------|------------------------------------------------------|-----------------------------------------------------------------------------------|--------------------------------------------------------------------|
| application | `/etc/xdg/btx-skill-jev-judge/`                      | `/Library/Application Support/bitranox/btx-skill-jev-judge/`                      | `%ProgramData%\bitranox\btx-skill-jev-judge\`                      |
| host        | `/etc/xdg/btx-skill-jev-judge/hosts/<hostname>.toml` | `/Library/Application Support/bitranox/btx-skill-jev-judge/hosts/<hostname>.toml` | `%ProgramData%\bitranox\btx-skill-jev-judge\hosts\<hostname>.toml` |
| user        | `~/.config/btx-skill-jev-judge/`                     | `~/Library/Application Support/bitranox/btx-skill-jev-judge/`                     | `%APPDATA%\bitranox\btx-skill-jev-judge\`                          |

On Linux the application and host layers are also read from `/etc/btx-skill-jev-judge/` (and its
`hosts/<hostname>.toml`) after the `/etc/xdg/` ones, so a key set in both takes the
`/etc/btx-skill-jev-judge/` value, and the user directory follows `$XDG_CONFIG_HOME` when it is
set. On Windows the user layer falls back to `%LOCALAPPDATA%\bitranox\btx-skill-jev-judge\` when
the `%APPDATA%` directory holds no configuration. A file only needs the keys it changes:

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
directory of your choice, among them a host file as
`xdg/btx-skill-jev-judge/hosts/your-hostname.toml`.

## Command-line overrides and profiles

- `--set SECTION.KEY=VALUE` (repeatable, before the command) overrides one key for this run, for
  example `jev-judge --set judge.attempts=2 run ...`.
- `--profile NAME` loads the configuration of a named profile, read from `profile/<NAME>/` under
  each layer's directory (the host file from `profile/<NAME>/hosts/<hostname>.toml`), for example
  `production` or `test`. Names are ASCII letters, digits, `-` and `_`, up to 64 characters.

## Errors

| Situation                                                                                 | Exit | stderr                                |
|-------------------------------------------------------------------------------------------|------|---------------------------------------|
| A configuration file or `.env` cannot be read or parsed                                   | 78   | `Error: <reason>`                     |
| An unknown key, or a value outside its constraint, in `[judge]` (`run`, `config`)         | 78   | `Error: judge.<key>: <reason>`        |
| An unknown key, or a value outside its constraint, in `[summary]` (`summarize`, `config`) | 78   | `Error: summary.<key>: <reason>`      |
| `band_low` is not below `band_high` (`summarize`, `config`)                               | 78   | `Error: summary: <reason>`            |
| A `[lib_log_rich]` value or `LOG_*` variable lib_log_rich refuses                         | 78   | `Error: lib_log_rich<.key>: <reason>` |
| A flag outside its constraint                                                             | 2    | `jev-judge: --<flag>: <reason>`       |

The file and logging rows apply to the commands that read the configuration: `config`, `run` and
`summarize`. A `[judge]` problem stops `run` and a `[summary]` problem `summarize`; `config`
shows the configuration first, with stdout unchanged in both formats, then writes an `Error:`
line for every problem in either section, whatever `--section` shows, and exits 78. `info`,
`config-deploy`,
`config-generate-examples` and `check-key` still work while the configuration is broken; under a
refused logging setting they run on logging's defaults, and only when the refused setting is a
`LOG_*` variable are all `LOG_*` variables ignored for that start. `logdemo` reads no configuration
either, but its demo reads the `LOG_*` variables itself, so a refused one ends it with exit 78 and
the same `Error:` line as `config`. Under `--json-bare` these errors still print
`{"error": "<reason>"}` on stdout.

## Other settings

- `JEV_JUDGE_BASE_URL` points the client at another API root, but only for a loopback host
  (`localhost`, any `127.x` address, `::1`). Any other value is ignored and the public endpoint is
  used. It exists so tests can talk to a local stub; it is not a configuration key.
- The `[lib_log_rich]` section configures logging. Every key, with its default, is documented in
  `src/btx_skill_jev_judge/adapters/config/defaultconfig.d/90-logging.toml` and `.env.example`.
- The `[lib_layered_config]` section controls the permissions `config-deploy` sets; see
  `src/btx_skill_jev_judge/adapters/config/defaultconfig.d/40-layered-config.toml`.
