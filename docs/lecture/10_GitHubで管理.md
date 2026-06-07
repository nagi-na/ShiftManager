# 10章 GitHubでコードを管理する

ここまでで機能はそろいました。これから手を入れていくにあたり、コードを **バージョン管理** しておきましょう。バージョン管理を使うと、

- いつ・何を・なぜ変えたかが記録に残る（`git log`）。
- 壊しても過去の状態に**戻せる**。
- **GitHub** に置けば、別のPC（自宅↔大学）からも続きを編集でき、バックアップにもなる。

この章では Git の基本操作と、GitHub への公開（push）までを行います。

> 🔰 この講座では開発用の `runserver`/SQLite のままで構いません。GitHub に置くのはあくまで「コードの管理と共有」のためで、アプリの動作とは独立した話です。

---

## 10-0. Git と GitHub の関係

- **Git**: 自分のPC上で変更履歴を記録するツール。コミット（commit）という単位で履歴を積み上げる。
- **GitHub**: Git のリポジトリを置く**クラウド上の置き場**。push でアップロード、pull でダウンロードする。

```
[手元のPC]  --- git commit --->  履歴を記録
            --- git push   --->  [GitHub]（クラウド）
            <--- git pull  ---
```

Git が入っているか確認します。

```
$ git --version
git version 2.x.x
```

無ければ各OSの方法で入れてください（macOS: `xcode-select --install` / Ubuntu: `sudo apt install git` / Windows: Git for Windows）。初回は名前とメールを設定します（コミットの署名に使われます）。

```
$ git config --global user.name  "あなたの名前"
$ git config --global user.email "you@example.com"
```

---

## 10-1. ⚠️ 最重要 ― 載せてはいけないものを決める

GitHub にコードを上げる前に、**絶対にコミットしてはいけないもの**を押さえます。ここを怠ると、パスワードや秘密鍵が世界中に公開されてしまいます。

| 載せない | 理由 |
| --- | --- |
| パスワードを書いたメモ（例: `staffpass.txt`） | 平文の認証情報。漏れたら即ローテーションが必要 |
| `db.sqlite3` | 利用者データが入っている |
| `SECRET_KEY` などの秘密鍵 | セッション/CSRF の署名鍵。漏れると改ざんされうる |
| `.env`、各種パスワード | 接続情報・認証情報 |
| `venv/`、`__pycache__/` | 環境依存・自動生成物。共有しても無意味 |

> ⚠️ **一度 push したら「漏れた」と考える。** 後から消しても、その間に誰かが見た／コピーした可能性は消えません。万一上げてしまったら、**履歴から削除したうえで、該当パスワード・鍵を必ず変更（ローテーション）** します。最初から上げないのが唯一の安全策です。

これらを除外する仕組みが **`.gitignore`** です。ここに書いたファイル/フォルダは Git の管理対象から外れ、コミットされません。

ファイル: `.gitignore`（プロジェクト直下）

```gitignore
# Python
__pycache__/
*.py[cod]

# 仮想環境
venv/
.venv/

# Django
db.sqlite3
db.sqlite3-journal
/staticfiles/
/media/

# 環境変数・秘密情報
.env

# エディタ
.vscode/
.idea/

# パスワードを書いた配布用メモ（絶対に上げない）
staffpass.txt
```

> 🔰 `SECRET_KEY` は、ファイルごと無視するのではなく **コードに直書きしない**のが対策です。`settings.py` で `os.environ.get("DJANGO_SECRET_KEY", ...)` のように環境変数から読む形にしておきます（詳しくは [13章](13_本番運用.md)）。

---

## 10-2. リポジトリを作って最初のコミット

プロジェクト直下で Git を初期化します。

```
$ cd /path/to/ShiftManager
$ git init
```

いま Git が何を「上げようとしているか」を必ず確認します。

```
$ git status
```

> ✅ ここで `db.sqlite3` や `venv/`、`staffpass.txt` が一覧に**出てこない**ことを確認してください。出てくる場合は `.gitignore` の綴り・場所（プロジェクト直下か）を見直します。

問題なければ、変更をステージ（コミット候補に追加）してコミットします。

```
$ git add .
$ git commit -m "シフト提出アプリの初期実装"
```

- `git add .` … 変更を「次のコミットに含める」印を付ける（`.gitignore` のものは除外される）。
- `git commit -m "..."` … 印を付けたぶんを1つの履歴として確定。メッセージは**何をしたか**を簡潔に。

> 🔰 すでに `db.sqlite3` などをコミットしてしまった後で `.gitignore` に足しても、**追跡は止まりません**。`git rm --cached db.sqlite3` で追跡だけ外して（手元のファイルは残る）からコミットし直します。

---

## 10-3. GitHub に上げる（push）

1. [github.com](https://github.com/) でアカウントを作る（無料）。
2. 右上「＋」→ **New repository**。リポジトリ名（例 `ShiftManager`）を入力。
   - **Public（公開）/ Private（非公開）** を選ぶ。学習・個人運用なら **Private 推奨**（10-1の事故の被害を抑えられる）。
   - README や .gitignore の自動生成は**チェックしない**（手元にあるため）。
3. 作成後に表示される「push an existing repository」のコマンドを使います。

```
$ git remote add origin https://github.com/<ユーザー名>/ShiftManager.git
$ git branch -M main
$ git push -u origin main
```

- `remote add origin ...` … GitHub 上の置き場に `origin` という名前を付ける。
- `push -u origin main` … 手元の `main` ブランチを `origin` に送る。`-u` で次回以降は `git push` だけでよくなる。

> ⚠️ パスワード認証は廃止されています。push 時に認証を求められたら、GitHub の **Personal Access Token**（Settings → Developer settings）を作ってパスワード欄に貼るか、SSH 鍵を設定します。

---

## 10-4. ふだんの開発サイクル

以降はこの3ステップの繰り返しです。

```
$ git status                 # 何を変えたか確認
$ git add <ファイル>          # 上げたい変更を選ぶ（全部なら git add -A）
$ git commit -m "○○を修正"    # 履歴として確定
$ git push                   # GitHub に反映
```

良いコミットのコツ:

- **意味のまとまりで分ける**。「ログイン修正」と「README追記」は別コミットに。
- メッセージは「何を・なぜ」。`タイポ修正` より `提出画面: 締切後の編集可否の判定を修正` のように具体的に。
- 別PCで作業を始めるときは、最初に `git pull` で最新を取り込む。

> 🔰 機能ごとに **ブランチ**（`git switch -c feature/メール通知`）を切ると、`main` を壊さず試せます。最初は `main` に直接コミットでも構いませんが、慣れたら使ってみましょう。

---

## ✅ 動作確認

- [ ] `git status` で、`db.sqlite3` / `venv/` / `staffpass.txt` が**追跡対象に出てこない**。
- [ ] `git log --oneline` に自分のコミットが並んでいる。
- [ ] GitHub のリポジトリ画面でソースが見え、`db.sqlite3` や秘密情報が**含まれていない**。
- [ ] ファイルを1つ直して `add → commit → push` し、GitHub 側にも反映される。

---

## つまずきポイント

- **秘密情報を push してしまった**: まず該当パスワード/鍵を**変更**する（最優先）。そのうえで履歴から削除する。コミットが少なければ `git rm --cached <file>` → `.gitignore` 追記 → `git commit --amend` → `git push --force` で消せる。「消したから大丈夫」ではなく「漏れた前提で対処」。
- **`db.sqlite3` が一覧に出る**: `.gitignore` がプロジェクト直下にあるか、綴りが合っているか確認。すでにコミット済みなら `git rm --cached`。
- **push で認証エラー**: パスワードではなく Personal Access Token か SSH 鍵を使う。
- **`venv/` を上げてしまった**: 環境依存で他PCでは動かない。`.gitignore` に入れ `git rm -r --cached venv` で外す。

---

コードが安全に GitHub で管理できるようになりました。次章では、これまで作った機能が壊れていないかを毎回自動で確かめる **自動テスト** を書きます。

➡️ [11章 自動テスト](11_自動テスト.md)
