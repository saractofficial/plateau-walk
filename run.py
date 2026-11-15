#!/usr/bin/env python3
"""
あるく行路 × PLATEAU 観光スポットマップ  ローカル起動スクリプト

使い方:
    python3 run.py                 # 東京都23区(13100)のデータを取得して起動
    python3 run.py 14100 14130     # 横浜市・川崎市のデータを取得して起動
    python3 run.py --refresh       # データを取り直す
    python3 run.py --no-download   # 取得せずに起動だけ
    python3 run.py 13100 --build-only  # データを data/ に保存して終了（公開用）

標準ライブラリのみで動きます（追加インストール不要）。
"""
import argparse
import json
import os
import re
import sys
import threading
import urllib.request
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
ENDPOINTS = [
    "https://api.plateauview.mlit.go.jp/datacatalog/graphql",
    "https://api.plateau.reearth.io/datacatalog/graphql",
]
TYPES = ["landmark", "park", "station", "shelter"]
QUERY = """query($codes:[AreaCode!], $types:[String!]){
  datasets(input:{areaCodes:$codes, includeTypes:$types}){
    id name typeCode
    ... on RelatedDataset { cityCode wardCode items { name format url originalUrl originalFormat } }
  }
}"""
UA = {"User-Agent": "plateau-walk-map/1.0", "Content-Type": "application/json"}


def gql(codes, types):
    body = json.dumps({"query": QUERY, "variables": {"codes": codes, "types": types}}).encode()
    last = None
    for ep in ENDPOINTS:
        try:
            req = urllib.request.Request(ep, data=body, headers=UA, method="POST")
            with urllib.request.urlopen(req, timeout=60) as r:
                j = json.load(r)
            if j.get("errors"):
                raise RuntimeError(j["errors"][0].get("message"))
            return j["data"]["datasets"]
        except Exception as e:  # 次のエンドポイントを試す
            last = e
            print(f"  ! {ep} に接続できませんでした: {e}")
    raise RuntimeError(f"PLATEAU API に接続できませんでした: {last}")


def safe(s):
    return re.sub(r"[^\w\-]+", "_", s)[:60]


def download(codes, types):
    os.makedirs(DATA, exist_ok=True)
    print(f"PLATEAU データカタログを検索中… 地域コード={codes} 種類={types}")
    datasets = gql(codes, types)
    if not datasets:
        print("  該当するデータセットがありませんでした。地域コードを確認してください。")
    manifest = []
    for d in datasets:
        for i, it in enumerate(d.get("items") or []):
            url = it.get("originalUrl") or it.get("url")
            fmt = (it.get("originalFormat") or it.get("format") or "").lower()
            if not url or not re.search(r"geojson|czml|json", fmt + url, re.I):
                continue
            ext = ".czml" if "czml" in (fmt + url).lower() and "geojson" not in (fmt + url).lower() else ".geojson"
            fname = f"{safe(d.get('wardCode') or d.get('cityCode') or 'x')}_{d['typeCode']}_{safe(d['id'])}_{i}{ext}"
            path = os.path.join(DATA, fname)
            print(f"  ↓ {d['name']}  ({it.get('name')})")
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]})
                with urllib.request.urlopen(req, timeout=120) as r, open(path, "wb") as f:
                    f.write(r.read())
                manifest.append({"file": fname, "type": d["typeCode"], "dataset": d["name"], "url": url})
            except Exception as e:
                print(f"    取得失敗: {e}")
    with open(os.path.join(DATA, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(f"完了: {len(manifest)} ファイルを data/ に保存しました")


def serve(port):
    handler = partial(SimpleHTTPRequestHandler, directory=ROOT)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/index.html"
    print(f"\nローカルサイトを起動しました → {url}\n（終了は Ctrl+C）")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n終了しました")


def main():
    ap = argparse.ArgumentParser(description="PLATEAU 行路観光スポットマップ")
    ap.add_argument("codes", nargs="*", default=["13100"], help="市区町村コード（例: 13100 東京23区）")
    ap.add_argument("--types", default=",".join(TYPES), help="取得する種類（カンマ区切り）")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--refresh", action="store_true", help="既存データを取り直す")
    ap.add_argument("--no-download", action="store_true", help="ダウンロードせずに起動")
    ap.add_argument("--build-only", action="store_true", help="データを取得して終了（公開用フォルダを作る）")
    a = ap.parse_args()

    has_data = os.path.exists(os.path.join(DATA, "manifest.json"))
    if a.build_only:
        download(a.codes, [t.strip() for t in a.types.split(",") if t.strip()])
        print("このフォルダ（index.html と data/）をそのまま公開サーバーにアップロードしてください。")
        return
    if not a.no_download and (a.refresh or not has_data or sys.argv[1:] and a.codes != ["13100"]):
        try:
            download(a.codes, [t.strip() for t in a.types.split(",") if t.strip()])
        except Exception as e:
            print(f"\n[警告] {e}\n  → データなしで起動します。画面からGeoJSONファイルを読み込むこともできます。")
    serve(a.port)


if __name__ == "__main__":
    main()
