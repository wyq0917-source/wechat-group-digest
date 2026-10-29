# Third-party sources and notices

This project is MIT licensed; see LICENSE. No WeChat binary, database, account data, key or third-party executable is distributed.

The PBKDF capture ABI and SQLCipher page authentication profile were informed by the MIT-licensed [GreenBubbles](https://github.com/bojieli/greenbubbles/tree/69f19c7089d7ef011e9ba43d44c6fb4e6e5be98b) source at commit `69f19c7089d7ef011e9ba43d44c6fb4e6e5be98b`, copyright (c) 2026 Bojie Li. Its MIT notice is retained in `LICENSES/GreenBubbles-MIT.txt`. GreenBubbles acquisition code also attributes `TANGandXUE/wcdb-key-tool`, copyright (c) 2025 CloudDreamAI / TANGandXUE, MIT; the corresponding MIT notice is retained below. This repository implements the local workflow in Python; it does not distribute the upstream Rust/Swift application or other bundled codecs.

SQLite's documented WAL format informs the rolling checksum and committed-prefix logic. Dependencies are installed separately: Python cryptography, Playwright/Chromium and system Zstandard retain their upstream licenses in their distributions. This project's MIT license does not replace those dependency licenses. WeChat is a trademark of its owner; this is an independent project and is not affiliated with Tencent.

## wcdb-key-tool MIT notice

Copyright (c) 2025 CloudDreamAI / TANGandXUE

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
