"""売る前チェック Web MVP を起動する。

使い方:
    py -3 run_sell_before_check.py        (Windows)
    python3 run_sell_before_check.py      (mac/Linux)

http://127.0.0.1:8788 で開きます。ローカル専用で外部公開しません。
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("sell_before_check_ai.app:app", host="127.0.0.1", port=8788)
