"""業者向け現地査定支援API (FastAPI).

起動: uvicorn field_assessment_ai.app:app --port 8789
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from . import __version__

app = FastAPI(title="現地査定支援AI", version=__version__, docs_url=None, redoc_url=None)

CATEGORY_CHECKLISTS: dict[str, dict] = {
    "precious_metal": {
        "label": "貴金属",
        "checks": ["刻印（K18/Pt900など）の確認", "重量の計測（依頼者の前で実施）",
                   "当日の公表相場の提示", "石付きの場合は石の扱いの説明"],
        "documents": ["本人確認書類の確認（古物営業法）", "買取明細書（品目・重量・単価）", "クーリング・オフ書面"],
        "cautions": ["訪問購入では契約書面交付とクーリング・オフ期間（8日間）の説明が必要",
                     "依頼品以外の買取の勧誘（いわゆる押し買い）は行わない"],
    },
    "kimono": {
        "label": "着物",
        "checks": ["証紙・落款の有無", "シミ・カビ・寸法の確認", "作家物・産地物の判別"],
        "documents": ["本人確認書類の確認（古物営業法）", "買取明細書", "クーリング・オフ書面"],
        "cautions": ["着物以外の品（貴金属など）の勧誘は行わない", "査定根拠を依頼者に説明できるようにする"],
    },
    "general": {
        "label": "一般品",
        "checks": ["型番・製造年の確認", "動作確認", "付属品・外箱の有無"],
        "documents": ["本人確認書類の確認（古物営業法）", "買取明細書"],
        "cautions": ["相場の根拠を提示できるようにする", "引き取り後のキャンセル対応方針を事前説明する"],
    },
}


class ChecklistRequest(BaseModel):
    category: str = Field("general", description="precious_metal | kimono | general")
    visit: bool = Field(False, description="訪問購入（出張買取）かどうか")


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "field_assessment_ai", "version": __version__,
            "categories": list(CATEGORY_CHECKLISTS)}


@app.post("/api/assessment/checklist")
def checklist(req: ChecklistRequest):
    data = CATEGORY_CHECKLISTS.get(req.category, CATEGORY_CHECKLISTS["general"])
    cautions = list(data["cautions"])
    if req.visit:
        cautions.insert(0, "訪問購入のため、特定商取引法上の書面交付・クーリング・オフ説明を必ず行うこと")
    return {
        "category": req.category if req.category in CATEGORY_CHECKLISTS else "general",
        "label": data["label"],
        "checks": data["checks"],
        "documents": data["documents"],
        "cautions": cautions,
        "disclaimer": "本APIは査定手順の参考情報を提供するもので、査定額の算定・保証や法令判断は行いません。",
    }
