# Supplemental dependency licenses

These unmodified upstream license texts supplement dependencies whose locked
Python distributions do not include their license files. The Windows installer
also preserves the license files distributed with Python and dependency metadata
under the application's `_internal` directory.

## Streamlit 1.65.0

- Source: <https://github.com/streamlit/streamlit/blob/1.65.0/LICENSE>
- Immutable source:
  <https://github.com/streamlit/streamlit/blob/ff22743ac9b00f19f7416d6b2cf4be19b0fa37ea/LICENSE>
- Local copy: `streamlit/LICENSE.txt`
- License: Apache License 2.0.
- The complete source tree at the 1.65.0 tag contains no `NOTICE` file.
- The root license is reproduced in full, including its appendix, without changes.

## proxy_tools 0.1.0

- Source:
  <https://github.com/jtushman/proxy_tools/blob/db43f1e35d4f90a65c5a4d56d9e9af88212ec6e6/LICENSE.txt>
- Local copy: `proxy_tools/LICENSE.txt`
- The upstream file identifies itself as the BSD License and includes copyright
  notices for Armin Ronacher (2013) and Jonathan Tushman (2014). Its text is
  reproduced without changes. The Python distribution's metadata instead labels
  the package MIT; that metadata is also retained.
- The repository has no release tags. At this immutable revision, `setup.py`
  declares version 0.1.0 and `proxy_tools/__init__.py` is byte-for-byte identical
  to the module in the locked 0.1.0 distribution, with SHA-256
  `d1539d95e1a713c068ca81d42e047b2c76568964cf277596d4e19efb22f476be`.
- The complete source tree at this revision contains no `NOTICE` file.

`manifest.json` records the source URLs, package versions, and SHA-256 hashes.
The Windows build verifies these versions against the build environment and
checks the bundled license bytes against the recorded hashes. Refresh the
source and provenance when either dependency version changes.
