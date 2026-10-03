# Contributing

Contributions are welcome through pull requests.

1. Fork the repo and create a branch from `main`.
2. Make your change. Keep the scripts on the Python standard library.
3. Run the tests:

   ```
   python -m pip install pytest
   python -m pytest -q
   ```

   If you changed how videos, frames or the CLI work, also run the live test, which talks to
   YouTube:

   ```
   CLAUDETUBE_LIVE=1 python -m pytest -q
   ```

4. Open a pull request against `main`. Say what changed, why, and which OS you tested on
   (macOS, Linux or Windows).

Bugs and ideas: open an issue at https://github.com/moazessam376-dev/claudetube/issues.

Style: plain, specific writing and no em dashes.
