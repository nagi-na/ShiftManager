# docs の構成ガイド

ShiftManager のドキュメント置き場です。フォルダごとの役割と読み方をまとめます。

| 場所 | 内容 | 鮮度 |
| --- | --- | --- |
| [`design/`](design/) | 開発開始時の設計ドキュメント（仕様書・技術構成・DB設計・画面設計） | **当時のドラフト**。実装が進んで現状と差分あり（各ファイル冒頭の注記参照） |
| [`features/`](features/) | 追加機能ごとの仕様・実装メモ・本番反映手順（1機能=1ファイル） | 実装と同期。**新機能はここに追記**（テンプレは [`features/README.md`](features/README.md)） |
| [`operations/`](operations/) | [デプロイ・運用マニュアル](operations/運用マニュアル.md)（セットアップ・日常運用・トラブル対応・Docker） | 運用の一次資料 |
| [`reviews/`](reviews/) | 精査・レビュー系レポート（セキュリティ精査、コード精査、講義資料の評価） | レポート作成日時点のスナップショット |
| [`lecture/`](lecture/) | 初学者向け講義資料（このアプリを一から作る教材、全19章＋README） | 別セッションで見直し予定 |
| [`todo.md`](todo.md) | 残タスクの一覧 | 随時更新 |

## 読み始めの目安

- **このアプリが何か知りたい** → [`design/仕様書.md`](design/仕様書.md)（原型）→ [`features/`](features/)（その後の追加機能）
- **サーバーに置きたい・運用したい** → [`operations/運用マニュアル.md`](operations/運用マニュアル.md)
- **直すべき問題を知りたい** → [`reviews/セキュリティ最終精査.md`](reviews/セキュリティ最終精査.md) と [`reviews/コード精査レポート_2026-06-11.md`](reviews/コード精査レポート_2026-06-11.md)
- **作り方を学びたい** → [`lecture/README.md`](lecture/README.md)

## 設計ドキュメント（design/）と現状の主な差分

design/ は開発開始時（2026-06-06 ごろ）の計画で、歴史的資料として残しています。実装後に変わった主な点:

- **ロールは3種類**: 設計時の `staff / leader` → 実装は `crew / leader / admin`（アカウント管理は admin のみ）。
- **機能追加**: 固定シフト（曜日別デフォルト＋変更申請・承認）、アナウンス（手動/自動投稿・添付・未読バッジ・1週間で自動削除）は設計時には無く、[`features/`](features/) に記載。
- **期間モデルの拡張**: 締切後ポリシー（`post_deadline_policy`）・編集最終期限（`edit_deadline`）・表示/非表示（`is_visible`）が追加。
- **メディア配信**: 確定シフトPDF等は認証付き配信（`X-Accel-Redirect`）に変更（[`reviews/セキュリティ最終精査.md`](reviews/セキュリティ最終精査.md) H-1 対応）。
- **本番構成**: Nginx + Gunicorn + MySQL（systemd 直置き）に加えて Docker compose 構成も追加。

最新の正は **コード本体と features/** です。
