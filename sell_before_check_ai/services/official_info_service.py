from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import OfficialInfo


def build_official_info_seeds() -> list[dict[str, Any]]:
    return [
        {
            "category": "訪問購入",
            "title": "訪問購入の基本",
            "summary": "訪問購入では、書面受領後のクーリングオフや引渡し前の確認が重要。",
            "content": "訪問購入は、事業者が消費者宅などを訪れて物品を買い取る取引です。書面や条件を確認し、迷う場合はその場で決めないことが重要です。",
            "reference_links_json": [
                "https://www.no-trouble.caa.go.jp/what/doortodoorpurchases/",
                "https://www.no-trouble.caa.go.jp/download/flyer.html",
            ],
            "caution_level": "warning",
        },
        {
            "category": "クーリングオフ",
            "title": "クーリング・オフの考え方",
            "summary": "書面受領後の一定期間内は、条件に応じて契約の撤回・解除ができる場合がある。",
            "content": "制度の適用範囲や期間は取引類型で異なります。書面と電磁的記録の案内を確認し、必要なら相談窓口を使います。",
            "reference_links_json": [
                "https://www.no-trouble.caa.go.jp/qa/coolingoff.html",
                "https://www.no-trouble.caa.go.jp/pdf/20230607_1.pdf",
            ],
            "caution_level": "info",
        },
        {
            "category": "物品引渡し拒絶",
            "title": "契約前に品物を渡さない確認",
            "summary": "契約内容や書面を確認するまで、品物をその場で渡さない判断が有効。",
            "content": "契約内容、明細、追加料金の有無を確認し、疑問が残る場合は引渡しを保留します。",
            "reference_links_json": [
                "https://www.no-trouble.caa.go.jp/what/doortodoorpurchases/",
                "https://www.caa.go.jp/policies/policy/local_cooperation/local_consumer_administration/damage",
            ],
            "caution_level": "warning",
        },
        {
            "category": "飛び込み訪問買取",
            "title": "飛び込み訪問買取の注意点",
            "summary": "突然の勧誘では、その場で即決せず、書面と条件を確認する。",
            "content": "飛び込みでの勧誘は、強い言葉が並んでいても、条件の確認が優先です。",
            "reference_links_json": [
                "https://www.no-trouble.caa.go.jp/what/doortodoorpurchases/",
                "https://www.no-trouble.caa.go.jp/download/flyer.html",
            ],
            "caution_level": "warning",
        },
        {
            "category": "不用品回収",
            "title": "不用品回収の確認ポイント",
            "summary": "料金の内訳、追加請求、家電リサイクルの扱いを紙面で確認する。",
            "content": "不用品回収は、処分区分や許可の確認が重要です。見積書なしの口頭契約は避け、追加料金の条件を確認します。",
            "reference_links_json": [
                "https://www.env.go.jp/hourei/11/000010.html",
                "https://www.caa.go.jp/policies/policy/local_cooperation/local_consumer_administration/damage",
            ],
            "caution_level": "warning",
        },
        {
            "category": "一般廃棄物収集運搬",
            "title": "一般廃棄物収集運搬の許可",
            "summary": "家庭ごみや一般廃棄物の収集運搬には許可区分の確認が必要。",
            "content": "一般廃棄物の収集運搬は許可が必要です。自治体ごとのルールと許可区分を確認します。",
            "reference_links_json": [
                "https://www.env.go.jp/hourei/11/000010.html",
                "https://www.env.go.jp/hourei/11/000478.html",
            ],
            "caution_level": "warning",
        },
        {
            "category": "家電リサイクル",
            "title": "家電リサイクル対象品の確認",
            "summary": "テレビ・冷蔵庫・洗濯機・エアコンは家電リサイクルの扱いを確認する。",
            "content": "家電4品目は、引取方法やリサイクル料金の扱いを確認します。",
            "reference_links_json": [
                "https://www.meti.go.jp/policy/it_policy/kaden_recycle/",
                "https://www.meti.go.jp/policy/it_policy/kaden_recycle/faq/faq.html",
            ],
            "caution_level": "warning",
        },
        {
            "category": "古物商",
            "title": "古物商の確認",
            "summary": "再販や買取の案内では古物商の確認が重要。",
            "content": "買取や再販の場面では、古物商許可の確認や明細の受け取りが大切です。",
            "reference_links_json": [
                "https://www.npa.go.jp/bureau/safetylife/kobutsu/",
            ],
            "caution_level": "info",
        },
        {
            "category": "バッテリー・危険物",
            "title": "バッテリーや危険物の扱い",
            "summary": "リチウム電池や危険物は別管理・別確認を優先。",
            "content": "膨張や破損のある電池は安全確認が必要です。自治体ルールと回収方法を先に確認します。",
            "reference_links_json": [
                "https://www.env.go.jp/recycle/waste/lithium_1/index.html",
                "https://www.meti.go.jp/policy/it_policy/kaden/index03.html",
                "https://www.env.go.jp/recycle/waste/sp_contr/",
            ],
            "caution_level": "critical",
        },
        {
            "category": "PC・スマホ個人情報",
            "title": "PC・スマホの個人情報保護",
            "summary": "初期化やデータ消去を確認してから引渡し・売却する。",
            "content": "PCやスマホは、初期化やデータ消去の確認を行い、個人情報が残らない状態にします。",
            "reference_links_json": [
                "https://www.pc3r.jp/home/data_erase.html",
                "https://www.meti.go.jp/policy/it_policy/kaden_recycle/kra/outline.htm",
                "https://www.ipa.go.jp/security/guide/vuln/forconsumer.html",
            ],
            "caution_level": "warning",
        },
        {
            "category": "消費者ホットライン188",
            "title": "消費者ホットライン188",
            "summary": "困ったときは188へ相談。最寄りの消費生活センターにつながる。",
            "content": "契約や勧誘で不安があるときは、消費者ホットライン188に相談します。",
            "reference_links_json": [
                "https://www.caa.go.jp/policies/application/inquiry/",
                "https://www.caa.go.jp/policies/policy/local_cooperation/local_consumer_administration/damage",
                "https://www.caa.go.jp/policies/policy/local_cooperation/local_consumer_administration/hotline/188_pamphlet",
            ],
            "caution_level": "info",
        },
    ]


def default_official_info_rows() -> list[dict[str, Any]]:
    return build_official_info_seeds()


def ensure_official_info_seeded(session: Session) -> int:
    existing = session.scalar(select(OfficialInfo.id).limit(1))
    if existing is not None:
        return 0
    rows = [OfficialInfo(**row) for row in build_official_info_seeds()]
    session.add_all(rows)
    session.commit()
    return len(rows)
