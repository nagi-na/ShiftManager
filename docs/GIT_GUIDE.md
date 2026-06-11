# Git の使い方ガイド

変更履歴の記録（commit）から、GitHub への共有（push/pull）、そして**ブランチ**と**マージ**まで。
このプロジェクト（ShiftManager）で実際に使う操作を、図と具体例でまとめます。

## もくじ

1. [Git とは何か](#git-とは何か)
2. [全体の流れ（ローカルとリモート）](#全体の流れローカルとリモート)
3. [基本コマンドを詳しく（add / commit / push / fetch / pull）](#基本コマンドを詳しくadd--commit--push--fetch--pull) ← 詳しく
4. [ブランチ（branch）](#ブランチbranch) ← 詳しく
5. [マージ（merge）](#マージmerge) ← 詳しく
6. [実例：このプロジェクトで行ったブランチ運用](#実例このプロジェクトで行ったブランチ運用)
7. [コンフリクト（競合）の解決](#コンフリクト競合の解決)
8. [履歴（コミット履歴）とは](#履歴コミット履歴とは)
9. [よく使うコマンド一覧](#よく使うコマンド一覧)
10. [.gitignore について](#gitignore-について)

---

## Git とは何か

Git は**ファイルの変更履歴を記録するツール**です。

たとえば `compose.yaml` を編集したとき、Git を使うと：

- 「いつ」「何を」変えたかが記録される
- 間違えても過去の状態に戻せる
- GitHub にアップロードしてバックアップ・共有できる
- **ブランチ**で「本番に影響しない作業場所」を作れる

---

## 全体の流れ（ローカルとリモート）

```
【ローカル（自分のPC）】                【リモート（GitHub）】

作業フォルダ
    ↓  git add
ステージング
    ↓  git commit
ローカルリポジトリ  ─── git push ───→  GitHub リポジトリ
                   ←── git pull ───
```

ポイントは**場所が2つある**ことです。

- **ローカル** : 自分のPCの中
- **リモート** : GitHub のサーバー（インターネット上）

`commit`・`push`・`pull` はそれぞれ別の場所への操作です。

---

## 基本コマンドを詳しく（add / commit / push / fetch / pull）

Git のファイルは、コマンドによって**4つの場所**の間を移動します。各コマンドが「どこからどこへ動かすか」を意識すると、混乱しなくなります。

```
 ①作業フォルダ      ②ステージング      ③ローカル履歴            ④GitHub（リモート）
 （編集中の状態）    （次に記録する分） （コミットの積み重ね）    （共有・バックアップ）

   │── git add ──▶ │── git commit ──▶ │──────── git push ──────▶ │
   │               │                  │                          │
   │◀───────────── git fetch（④を③の隣に取得）──────────────────│
   │◀──────────────────── git pull（fetch + merge）──────────────│
```

| コマンド | 動かす範囲 | ネット通信 | ひとことで |
|---|---|---|---|
| `git add` | ① → ② | なし | 次のコミットに**含める変更を選ぶ** |
| `git commit` | ② → ③ | なし | 選んだ変更を**履歴に刻む** |
| `git push` | ③ → ④ | **あり** | ローカルの履歴を**GitHubへ送る** |
| `git fetch` | ④ → ローカル（参照のみ） | **あり** | GitHubの最新を**取得だけ**（作業には未反映） |
| `git pull` | ④ → ①③ | **あり** | fetch＋merge を**まとめて実行** |

> 🔰 通信が起きるのは push / fetch / pull の3つだけ。add / commit は**完全にオフラインのローカル操作**です。

---

### `git add` ― 記録する変更を「選ぶ」（ステージング）

編集した内容を、いきなりコミットするのではなく、まず**ステージング（次のコミットに入れる候補）**に載せます。

```bash
git add compose.yaml        # このファイルだけステージング
git add .                   # カレント以下の変更を全部
git add -A                  # 削除も含め、リポジトリ全体の変更を全部
git add -p                  # 変更を「かたまり単位」で選んで載せる（対話式）
```

**なぜ add という一手間があるのか**：複数の変更をしたとき、「この変更だけ先にコミット」と**選り分けられる**からです。たとえばコード修正とドキュメント修正を別々のコミットに分けたいとき、まずコード関連だけ `add` → `commit`、次にドキュメントを `add` → `commit`、とできます。

ステージングを取り消したい（コミットに含めるのをやめたい）とき：

```bash
git restore --staged compose.yaml   # ②→① に戻す（編集内容は消えない）
git status                          # 今ステージされている物を確認
```

> 🔰 `git status` で、緑文字＝ステージ済み（②）、赤文字＝未ステージ（①）と区別できます。迷ったら `git status` を打つのが基本です。

---

### `git commit` ― 区切りを履歴に「刻む」

ステージング（②）の内容を、**1つのスナップショット**として履歴（③）に記録します。**ローカルだけの操作**で、GitHub には何も送りません。写真でいう「シャッターを切る」段階です。

```bash
git commit -m "MySQL の設定を追加"   # 1行メッセージで記録
git commit                           # エディタが開き、長い説明も書ける
git commit -am "軽微な修正"          # 追跡済みファイルの add と commit を同時に（※新規ファイルは別途 add 要）
```

**コミットメッセージの書き方**（後で履歴を読む自分のため）：

```
1行目：要点を短く（例: fix: ログインの404を修正）

3行目以降：必要なら「なぜ変えたか」を本文に。
```

直前のコミットをやり直したい（メッセージ修正・add し忘れの追加）：

```bash
git add 忘れてたファイル
git commit --amend            # 直前のコミットを上書きで作り直す
```

> ⚠️ `--amend` は**まだ push していないコミットだけ**にしましょう。push 済みを書き換えると、リモートと履歴が食い違います。

---

### `git push` ― ローカルの履歴を GitHub へ「送る」

コミット済み（③）の内容を **GitHub（④）にアップロード**します。「カメラの写真をクラウドに上げる」イメージ。**add / commit していない変更は送られません**（push の対象はコミットだけ）。

```bash
git push origin main          # origin（GitHub）の main へ送る
```

- `origin` … 接続先（GitHubリポジトリ）の名前。`git remote -v` で確認。
- `main` … 送るブランチの名前。

初回や新しいブランチでは、**上流（追跡先）を覚えさせる** `-u` を付けると便利：

```bash
git push -u origin main       # 以後は `git push` だけで同じ先に送れる
```

うまくいかない代表例：**リモートが進んでいて拒否される**（`rejected … fetch first`）。誰か（または別PCの自分）が先に push していると起きます。→ 先に `git pull` で取り込んでから push します。

---

### `git fetch` ― GitHub の最新を「取得だけ」する

GitHub の最新コミットを**ダウンロードしますが、今の作業ブランチには反映しません**。取得結果は `origin/main` という**リモート追跡ブランチ**に入り、「中身を確認してから合流するか決める」ことができます。

```bash
git fetch origin                 # GitHub の最新を取得（作業には未反映）
git log --oneline main..origin/main   # 自分にまだ無いコミットを確認
git diff main origin/main        # 差分の中身を確認
git merge origin/main            # 確認して納得したら合流
```

**fetch の良さは「いきなり混ざらない」安全性**です。pull は取得と合流を一気にやるので、コンフリクトや予期せぬマージが起きることがあります。慎重に進めたいときは **fetch →（確認）→ merge** と分けます。

```
④GitHub ──fetch──▶ origin/main（手元の「リモートの写し」）──merge──▶ 今のブランチ
```

> 🔰 `git fetch` だけでは作業フォルダのファイルは1文字も変わりません。だから「とりあえず最新を見ておく」用途で気軽に使えます。

---

### `git pull` ― fetch ＋ merge を「まとめて」実行

`git pull` は、**`git fetch`（取得）と `git merge`（合流）を続けて行う**ショートカットです。

```bash
git pull origin main
# ↑ これは下の2つと同じ
git fetch origin
git merge origin/main
```

手軽な反面、取得した瞬間に合流まで進むため、分岐していればマージコミットやコンフリクトが発生します。履歴を一直線に保ちたい人は、合流の代わりに rebase する版を使うこともあります：

```bash
git pull --rebase origin main    # 合流せず、自分のコミットを最新の上に並べ直す
```

> 🔰 使い分けの目安：**ふだんは `git pull` で十分**。中身を見てから慎重に取り込みたいときや、コンフリクトが怖いときは **`git fetch` → 確認 → `git merge`** に分けます。

---

## ブランチ（branch）

### ブランチとは

ブランチは**履歴の「枝分かれした作業場所」**です。`main` という幹から枝を伸ばし、そこで自由に作業しても**幹（main）には影響しません**。

```
              ●──●──●   feature ブランチ（作業中）
             ╱
  ●──●──●──●            main ブランチ（安定版はそのまま）
```

「並行世界」をイメージすると分かりやすいです。枝の世界で実験し、うまくいったら幹の世界に合流（マージ）させ、ダメなら枝ごと捨てれば幹は無傷です。

### なぜブランチを使うのか

- **main を壊さない**：公開・本番に使う `main` を常に「動く状態」に保てる。
- **作業を分けられる**：「機能Aの追加」「バグ修正」を別々の枝で進められる。
- **やり直せる**：枝の実験が失敗しても、枝を削除すれば main は元のまま。

> 🔰 1人開発でも「main に直接コミットせず、いったん枝を切ってから main に合流させる」と、**main がいつでも安全**になり、まとめてレビュー・取り消しがしやすくなります。

### 基本コマンド

```bash
git branch                       # ブランチの一覧（* が今いるブランチ）
git branch <名前>                # ブランチを作る（移動はしない）
git switch -c <名前>             # ブランチを作って移動（推奨）
git checkout -b <名前>           # 同上（古い書き方。意味は同じ）
git switch <名前>                # 既存ブランチに移動
git switch -                     # 直前にいたブランチへ戻る
git branch -m <新名前>           # 今のブランチの名前を変える
git branch -d <名前>             # ブランチを削除（マージ済みのみ・安全）
git branch -D <名前>             # 強制削除（未マージでも消す・注意）
git branch --merged              # main に取り込み済みのブランチを確認
```

> 🔰 `switch` は「ブランチ移動専用」の新しいコマンドで、`checkout`（多機能で紛らわしい）より安全・明快です。新しめのGitなら `switch` をおすすめします。

### HEAD とは

`HEAD` は**「今いるブランチ（＝今の作業位置）」を指す矢印**です。`git switch main` すると HEAD が main を指し、作業フォルダの中身もそのブランチの状態に切り替わります。

```
HEAD → main
        ●──●──●
```

### 典型的なワークフロー（枝を切る→作業→合流）

```bash
# 1. main にいることを確認し、最新にしておく
git switch main
git pull origin main            # 共同作業なら最新を取得

# 2. 作業用のブランチを切って移動
git switch -c feature/announce  # 「アナウンス機能」用の枝

# 3. 編集して、区切りごとに commit（何回でも）
git add .
git commit -m "アナウンスのモデルを追加"
# ...さらに編集して commit...

# 4. main に戻ってマージ（次章へ）
git switch main
git merge feature/announce

# 5. 役目を終えた枝を片付ける
git branch -d feature/announce
```

> 🔰 ブランチ名は `feature/◯◯`（機能追加）・`fix/◯◯`（修正）のように**用途＋内容**で付けると、後から見て分かりやすいです。

---

## マージ（merge）

マージは、別れていた2つの履歴を**1つに合流させる**操作です。`git merge <取り込みたいブランチ>` を、**取り込み先（ふつう main）にいる状態で**実行します。

```bash
git switch main            # 取り込み先（main）に移動してから
git merge feature/announce # feature を main に取り込む
```

マージには結果が2パターンあります。**どちらになるかは「main が枝を切った後に進んでいるか」で自動的に決まります。**

### パターン1：fast-forward（早送り）

枝を切ったあと **main 側に新しいコミットが無い**場合、Git は分岐とみなさず、**main の矢印を枝の先端まで前に進めるだけ**です。新しい「マージコミット」は作られず、履歴は一直線のまま。

```
【マージ前】 main は B のまま。枝だけ C, D まで進んだ
  main
   ↓
   A───B
        ╲
         C───D   feature

【fast-forward マージ後】 main の矢印が D まで前進しただけ
   A───B───C───D
               ↑
              main
```

```bash
git switch main
git merge feature/announce          # 条件を満たせば自動でfast-forward
# または「fast-forwardできるときだけ許す」と明示：
git merge --ff-only feature/announce
```

> 🔰 1人開発で「枝を切って作業 → そのまま main に戻す」場合、ほぼ毎回これになります。履歴が枝分かれせず読みやすいのが利点。`--ff-only` を付けると「分岐していたら止める」ので、意図しない合流を防げて安全です。

### パターン2：merge commit（合流コミット）

枝を切ったあと **main 側にも別のコミットが増えていた**場合、2つの流れを束ねる**新しいコミット（マージコミット）**が作られます。

```
  A───B───────M   ← M がマージコミット（main）
       ╲     ╱
        C───D      feature
   （B のあと main 側も E などが進んでいた、の図は下記）
```

```
       E────────M   main 側も進んでいた → 合流点 M ができる
      ╱        ╱
  A──B        ╱
      ╲      ╱
       C────D       feature
```

```bash
git switch main
git merge feature/announce          # 分岐があれば自動でマージコミットを作成
git merge --no-ff feature/announce  # 分岐が無くても「あえて合流点を残す」
```

> 🔰 `--no-ff` は「この枝で1つの作業をした」というまとまりを履歴に残したいときに使います（マージコミットに作業の区切りが見えるため、後から追いやすい）。

### fast-forward と merge commit の使い分け

| | fast-forward | merge commit |
|---|---|---|
| いつ起きる | 枝を切った後 main が進んでいない | main も進んでいた／`--no-ff` 指定 |
| 履歴の形 | 一直線（合流点なし） | 枝分かれ→合流（合流点あり） |
| 向いている場面 | 1人開発・小さな変更を素早く反映 | 複数人・機能のまとまりを履歴に残したい |

### マージが終わったら枝を片付ける

合流済みの枝は残しておくと一覧がごちゃつくので、削除します。

```bash
git branch --merged        # main に取り込み済みの枝を確認
git branch -d feature/announce   # 取り込み済みなら -d で安全に削除
```

### merge と rebase の違い（参考）

`rebase` は「枝の根元を付け替えて履歴を一直線に書き換える」別の合流方法です。

| | merge | rebase |
|---|---|---|
| 履歴の形 | 合流点（マージコミット）が残ることがある | 一直線に書き換わる |
| 履歴の正確さ | 実際の作業の流れがそのまま残る | すっきりするが履歴を書き換える |
| 使いどころ | チーム開発・本番ブランチへの統合 | 個人作業・履歴をきれいにしたいとき |

> ⚠️ rebase は**すでに push 済みの共有ブランチでは避ける**のが原則（履歴を書き換えるため、他の人と食い違います）。手元だけの枝を整える用途に留めるのが安全です。

---

## 実例：このプロジェクトで行ったブランチ運用

実際に ShiftManager で行った「枝を切る → 2回コミット → main へ fast-forward マージ」の流れです。

```bash
# ① main にいる状態から、作業用ブランチを作って移動
git switch -c lecture-audit-and-code-fixes

# ② 区切りごとに2回コミット（コード修正・ドキュメント）
git add accounts/ shifts/ shift_manager/settings.py
git commit -m "fix(security): フォームセット改ざん耐性・自己パスワード再発行ブロック等を追加"
git add docs/
git commit -m "docs: docsフォルダ整理・レビュー追加・講義に2機能章を追加"

# ③ main に戻る
git switch main

# ④ fast-forward でマージ（main は枝を切ってから進んでいなかったので一直線）
git merge --ff-only lecture-audit-and-code-fixes
```

このときのターミナル表示：

```
Updating 6b44952..affebaf
Fast-forward
 ... 24 files changed, 1846 insertions(+), 40 deletions(-)
```

- `Fast-forward` ＝ パターン1。main の矢印が `6b44952` から `affebaf` へ前進しただけで、マージコミットは作られていません。
- 枝を切ったあと main を触っていなかったので、自動的に fast-forward になりました。
- マージ後、不要になった枝は `git branch -d lecture-audit-and-code-fixes` で削除できます。
- GitHub にも反映するなら、最後に `git push origin main` を実行します（この時点ではまだローカルだけ）。

> 🔰 「main で直接編集せず、いったん枝を切ってから戻す」だけで、作業中も main は常に安全、コミットもまとめやすくなります。1人開発でも実践しやすい型です。

---

## コンフリクト（競合）の解決

同じファイルの同じ行を、2つのブランチがそれぞれ別の内容に変更してマージすると、Git はどちらが正しいか判断できず「コンフリクト」になります。

```
<<<<<<< HEAD（今のブランチの内容）
MYSQL_ROOT_PASSWORD: secret123
=======
MYSQL_ROOT_PASSWORD: password456
>>>>>>> feature/announce（取り込もうとした側の内容）
```

解決手順：

1. ファイルを開き、`<<<<<<<`・`=======`・`>>>>>>>` の行を消して、**正しい最終形**に書き直す
2. `git add <ファイル名>` でステージング（「解決した」と伝える）
3. `git commit` でマージを完了（fast-forward でない通常マージのとき）

> 🔰 途中でやめたいときは `git merge --abort` でマージ前の状態に戻せます。

---

## 履歴（コミット履歴）とは

commit するたびに「スナップショット」が積み重なります。これが**履歴**です。

```
●  コミット3: .gitignore を追加        ← 最新（HEAD）
●  コミット2: README.md を追加
●  コミット1: compose.yaml を作成      ← 最初
```

```bash
git log --oneline           # 履歴を1行ずつ表示
git log --oneline --graph   # 枝分かれ・合流を図で表示（ブランチ運用時に便利）
```

### ローカルとリモートで履歴がズレると push が拒否される

GitHub でリポジトリ作成時に「Initialize this repository」にチェックを入れると、GitHub 側に自動で最初のコミットができます。ローカルがそれを知らずに別のコミットを作ると、2つの履歴が食い違い push を拒否されます。

**失敗しない作成手順**：

```
1. GitHub でリポジトリを作成
   └─「Initialize this repository」のチェックを外す  ← 重要
2. ローカルで git init
3. ファイルを作って commit
4. git remote add origin [URL] でリモートを登録
5. git push origin main で push
```

> ⚠️ すでにズレてしまった場合の `git push --force` は**リモートの履歴を上書き**します。共有リポジトリでは他の人の作業を消す危険があるため、1人で・状況を理解したうえでだけ使ってください。

---

## よく使うコマンド一覧

```bash
# 基本
git init                         # リポジトリを初期化
git status                       # 現在の状態を確認（緑=ステージ済 / 赤=未ステージ）
git add <ファイル>               # ステージング（git add . で全変更 / -p で一部だけ）
git restore --staged <ファイル>  # ステージングを取り消す（編集内容は残す）
git commit -m "メッセージ"       # コミット
git commit --amend               # 直前のコミットを作り直す（push前のみ）
git log --oneline --graph        # 履歴を図で確認

# ブランチ
git branch                       # 一覧（* が現在地）
git switch -c <名前>             # 作って移動
git switch <名前>                # 移動
git branch -m <新名前>           # 名前変更
git branch -d <名前>             # 削除（マージ済み）

# マージ
git switch main                  # 取り込み先へ移動してから
git merge <ブランチ>             # 取り込む
git merge --ff-only <ブランチ>   # 早送りできるときだけ
git merge --abort                # マージを中止して元に戻す

# リモート
git remote -v                    # 登録済みリモートを確認
git push origin main             # GitHub に送る（初回は -u origin main で上流を記憶）
git fetch origin                 # GitHub の最新を取得だけ（作業には未反映）
git pull origin main             # GitHub から取得して合流（fetch + merge）
```

---

## .gitignore について

Git に無視させるファイルを指定するファイルです。

```
# .gitignore の例
.env                   # 環境変数（パスワード等）を除外
db.sqlite3             # 開発用DBを除外
__pycache__/           # Pythonのキャッシュを除外
```

`git status` を実行しても、`.gitignore` に書かれたファイルは一覧に出ません。これにより、パスワードや秘密鍵を誤って GitHub に push してしまう事故を防げます。

> 🔰 このプロジェクトの `.gitignore` には `.env`・`db.sqlite3`・`media/`・`.claude/` などが入っています（秘密情報・個人データ・ローカル設定を共有しないため）。詳しくは [運用マニュアル](operations/運用マニュアル.md) や講義 [10章 GitHubで管理](lecture/10_GitHubで管理.md) も参照。

---

## 付録：初回セットアップ時に実行したコマンド例

プロジェクトを作って GitHub に上げるまでの、最初の一連の流れ（参考）。

```bash
git init                                              # リポジトリを初期化
git config --global user.email "you@example.com"      # ユーザー情報（初回のみ）
git config --global user.name "Your Name"
git add .gitignore compose.yaml README.md             # ステージング
git commit -m "最初のコミット"                        # コミット
git branch -m master main                             # 既定ブランチ名を main に
git remote add origin https://github.com/<user>/<repo>.git  # リモート登録
git push origin main                                  # GitHub に push
```
