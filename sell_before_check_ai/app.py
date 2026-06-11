"""sell_before_check_ai Web MVP (FastAPI).

起動: python3 run_sell_before_check.py  (http://127.0.0.1:8788)

ルート:
  /                  ホーム
  /flyer-check       チラシチェック
  /item-check        商品チェック
  /quote-check       見積もりチェック
  /result            診断結果（フォームPOST / GETサンプル表示）
  /mobile-preview    iPhone枠プレビュー (?view=home|flyer|item|quote|result)
  /refusal-examples  断り文例コピー
  /market-links      相場リンク
  /hotline-188       188相談案内
  /disclaimer        免責・注意事項
  /privacy           プライバシーポリシー
  /settings          設定・データ削除
  /api/check         判定API (JSON)
  /api/health        ヘルスチェック
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from . import __version__
from .logic import CHECK_TYPES, DISCLAIMER, HOTLINE_NOTE, evaluate, load_rules

BASE_DIR = Path(__file__).parent

app = FastAPI(title="売る前チェック", version=__version__, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

CHECK_PAGES = {
    "flyer": {
        "title": "チラシチェック",
        "lead": "ポストに入っていた買取チラシの文言を貼り付けてください。気になる表現がないか確認します。",
        "placeholder": "例: どんなものでも高価買取! 本日限り査定額アップ! 無料査定だけでもOK!",
    },
    "item": {
        "title": "商品チェック",
        "lead": "売ろうとしている品物の説明を入力してください。注意が必要な品目かどうか確認します。",
        "placeholder": "例: 母の形見の18金のネックレスと着物を売ろうと思っています。",
    },
    "quote": {
        "title": "見積もりチェック",
        "lead": "受け取った見積もりや業者の説明を入力してください。あいまいな表現や注意点を確認します。",
        "placeholder": "例: 買取一式 30,000円。本日中なら特別価格。キャンセル不可と言われました。",
    },
}


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    ctx.setdefault("version", __version__)
    return templates.TemplateResponse(request, template, ctx)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return _render(request, "home.html", active="home")


@app.get("/flyer-check", response_class=HTMLResponse)
def flyer_check(request: Request):
    return _render(request, "check_form.html", active="flyer",
                   check_type="flyer", page=CHECK_PAGES["flyer"], flags=load_rules()["flags"])


@app.get("/item-check", response_class=HTMLResponse)
def item_check(request: Request):
    return _render(request, "check_form.html", active="item",
                   check_type="item", page=CHECK_PAGES["item"], flags=load_rules()["flags"])


@app.get("/quote-check", response_class=HTMLResponse)
def quote_check(request: Request):
    return _render(request, "check_form.html", active="quote",
                   check_type="quote", page=CHECK_PAGES["quote"], flags=load_rules()["flags"])


@app.post("/result", response_class=HTMLResponse)
def result_post(
    request: Request,
    check_type: str = Form("flyer"),
    text: str = Form(""),
    flags: list[str] = Form([]),
):
    verdict = evaluate(text, check_type, flags)
    rules = load_rules()
    return _render(request, "result.html", active="result", verdict=verdict,
                   input_text=text,
                   refusal_templates=rules["refusal_templates"],
                   market_links=rules["market_links"])


@app.get("/result", response_class=HTMLResponse)
def result_get(request: Request):
    # 直接アクセス時はサンプル結果を表示する(ディープリンク/プレビュー用)
    verdict = evaluate("本日限り! どんなものでも高価買取。キャンセル不可。", "flyer", ["visit"])
    rules = load_rules()
    return _render(request, "result.html", active="result", verdict=verdict,
                   input_text="(サンプル入力での表示例です)",
                   sample=True,
                   refusal_templates=rules["refusal_templates"],
                   market_links=rules["market_links"])


@app.get("/mobile-preview", response_class=HTMLResponse)
def mobile_preview(request: Request, view: str = Query("home")):
    paths = {
        "home": "/", "flyer": "/flyer-check", "item": "/item-check",
        "quote": "/quote-check", "result": "/result",
    }
    target = paths.get(view, "/")
    return _render(request, "mobile_preview.html", active="preview",
                   view=view if view in paths else "home", target=target, views=paths)


@app.get("/refusal-examples", response_class=HTMLResponse)
def refusal_examples(request: Request):
    return _render(request, "refusal.html", active="refusal",
                   refusal_templates=load_rules()["refusal_templates"])


@app.get("/market-links", response_class=HTMLResponse)
def market_links(request: Request):
    return _render(request, "market.html", active="market",
                   market_links=load_rules()["market_links"])


@app.get("/hotline-188", response_class=HTMLResponse)
def hotline(request: Request):
    return _render(request, "hotline.html", active="hotline")


@app.get("/disclaimer", response_class=HTMLResponse)
def disclaimer(request: Request):
    return _render(request, "disclaimer.html", active="disclaimer", disclaimer=DISCLAIMER)


@app.get("/privacy", response_class=HTMLResponse)
def privacy(request: Request):
    return _render(request, "privacy.html", active="privacy")


@app.get("/settings", response_class=HTMLResponse)
def settings(request: Request):
    return _render(request, "settings.html", active="settings")


class CheckRequest(BaseModel):
    check_type: str = Field("flyer", description="flyer | item | quote")
    text: str = ""
    flags: list[str] = []


@app.post("/api/check")
def api_check(req: CheckRequest):
    return JSONResponse(evaluate(req.text, req.check_type, req.flags))


@app.get("/api/health")
def api_health():
    return {"status": "ok", "app": "sell_before_check_ai", "version": __version__,
            "check_types": list(CHECK_TYPES), "hotline": HOTLINE_NOTE}
