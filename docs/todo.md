# TodoList

## 完了

- [x] HTTPS化（Cloudflare Tunnel。[lecture 16〜17章](lecture/16_Cloudflareトンネルで公開.md)）
- [x] ネットワーク公開設定（LAN公開→Cloudflare公開）
- [x] Docker化（[lecture 19章](lecture/19_Docker化.md)・[運用マニュアル第4部](operations/運用マニュアル.md)）
- [x] infomation機能（アナウンス機能として実装。[features/announcements.md](features/announcements.md)）

## 残タスク（主に reviews/ の指摘から）

優先度順。詳細は [セキュリティ最終精査](reviews/セキュリティ最終精査.md)・[コード精査レポート](reviews/コード精査レポート_2026-06-11.md) を参照。

- [x] `settings.py` の `ALLOWED_HOSTS` ハードコード上書きの解消（コード精査 C-1。環境変数が無効化されている）
- [x] 開発環境と本番環境の分離（セキュリティ精査 A-0。設定分離・ホスト分離）
- [ ] `DEBUG` 既定値の安全化（セキュリティ精査 H-2）
- [ ] `SECRET_KEY` 未設定時にフェイルファスト（セキュリティ精査 M-4）
- [ ] ログインのブルートフォース対策（セキュリティ精査 M-1）
- [ ] アップロードファイルの実体検証（セキュリティ精査 M-2）
- [x] フォームセット改ざん耐性（work_date / weekday の検証。コード精査 C-2）※2026-06-11 対応
- [x] 自分自身へのパスワード再発行ブロック（コード精査 C-5）※2026-06-11 対応
- [x] 講義資料（docs/lecture/）の見直し ※2026-06-11: 固定シフト(20章)・アナウンス(21章)を追加、C-2/C-5を05/08章へ反映、**網羅監査を実施**し09章のロジック差分(F-1〜F-4)・admin登録(F-5)を修正。詳細は [講義網羅監査_2026-06-11.md](reviews/講義網羅監査_2026-06-11.md)（残差は表示文言とテンプレHTML細部のみ）
