# 14章 MySQLの導入 ― 稼働中の本番をアップデートする

> 🔰 この章は **運用編** です。[13章](13_本番運用.md) で公開した本番（Nginx + Gunicorn + systemd、DBは **SQLite**）が**すでに動いていて、クルーが実際にシフトを提出している**前提で、そこへ MySQL を後から導入します。新規構築ではなく「**稼働中のシステムにアップデートを適用する**」作業として進めます。
>
> 前提環境（Ubuntu/WSL2・`systemd`・`apt`）と、`/home/nagin/ShiftManager`・ユーザー `nagin`・サービス名 `shiftmanager` の読み替えは [13章の「前提環境／置換早見表」](13_本番運用.md) と同じです。自分の環境に合わせて置き換えてください。

> ⚠️ **方針（[12章](12_開発編のまとめ.md) の環境分離の原則）：MySQL は「本番のデータベース」。開発（SQLite）とは分け、本番DBに開発の練習データを入れません。**
> - **新規に本番を立てる場合（基本）**：空のMySQLに `migrate` でテーブルを作り、`createsuperuser` で**本物の管理者**を作成。クルー等の実アカウントはアプリの管理画面から作る（14-5 の「新規」）。
> - **データ移行が要る場合だけ**：**すでにSQLiteで本物の運用データがある**ときに限り `dumpdata`→`loaddata` で移す。**開発・練習で作ったデータは本番DBに流し込まない**（14-5 の「移行」）。

実運用でDBを用意するときの肝は次の3つです。本章はこれを軸に組み立てます。

1. **データを混ぜない／失わない** ― 本番DBは開発と分ける。本物の運用データがある場合のみ、失わずに移す。
2. **停止時間を最小に** ― 止めずにできる準備と、短いメンテで行う切替を分ける。
3. **いつでも戻せる** ― 移行する場合は SQLite ファイルを残し、設定1つでロールバックする。

---

## 14-0. なぜ・いつ MySQL にするか

SQLite は優秀で、数人〜数十人規模なら本番でも十分です。MySQL を検討する主な理由は **同時書き込み** です。

- SQLite は書き込み時に **DBファイル全体をロック**します。締切直前に全員が一斉提出すると `database is locked` が起きうる、というのが現実的な弱点です。
- MySQL は行単位ロックで同時書き込みに強く、ネットワーク越し・複数アプリサーバーからの共有もできます。

> 🔰 「困っていないなら急いで移す必要はない」が基本です。`database is locked` が出る／利用者が増える／本格運用に乗せる、あたりが移行のサイン。本章は**学習も兼ねて一度経験しておく**価値が高い作業です。

---

## 14-1. 作戦 ― 無停止の準備 → 短いメンテで切替 → 戻せる

```
【無停止でできる準備】   MySQL導入・ドライバ・settings・DB作成
        │  （この間アプリは SQLite のまま動き続ける）
        ▼
【短いメンテ】          データ移行（dump→migrate→load）＋接続先の切替＋再起動
        │
        ▼
【確認】               MySQLで動いているか／ダメなら即ロールバック
```

ポイントは、**切替の瞬間まで本番は SQLite で動かしたまま**にすること。準備が全部終わってから、短時間で切り替えます。そして **`db.sqlite3` は消さない**――これが「いつでも戻せる」安全網になります。

---

## 14-2. 【無停止】MySQL とドライバを用意する

MySQL サーバー本体と、Python ドライバ `mysqlclient` のビルドに必要な OS 側ライブラリを入れます。

```
$ sudo apt-get update
$ sudo apt-get install -y mysql-server default-libmysqlclient-dev build-essential pkg-config
$ sudo systemctl enable --now mysql      # 起動＋自動起動
```

Python ドライバを venv に入れます（`sudo` 不要）。

```
$ ./venv/bin/pip install mysqlclient
$ ./venv/bin/python -c "import MySQLdb; print(MySQLdb.version_info)"   # 確認
```

`requirements.txt` にも反映します。

```
mysqlclient>=2.2
```

> ⚠️ `mysqlclient` のインストールでエラーが出るときは、ほぼ OS 側の開発ライブラリ不足です（上の `default-libmysqlclient-dev build-essential pkg-config`）。
> 🔰 ここまでは**アプリに一切影響しません**。本番は SQLite のまま動き続けています。

---

## 14-3. 【無停止】settings を「DB切替」対応にする

`settings.py` を、環境変数 `DJANGO_DB=mysql` のときだけ MySQL を使う形にします。**既定は今まで通り SQLite** なので、この変更を入れても本番は壊れません。

ファイル: `shift_manager/settings.py`（`DATABASES` を差し替え）

```python
# 環境変数 DJANGO_DB=mysql のときだけ MySQL を使う。
# 既定（未設定/その他）は開発と同じ SQLite。接続情報は環境変数で渡す。
if os.environ.get('DJANGO_DB', 'sqlite') == 'mysql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.environ.get('DB_NAME', 'shift_manager'),
            'USER': os.environ.get('DB_USER', 'shift'),
            'PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', '3306'),
            'OPTIONS': {'charset': 'utf8mb4'},
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
```

**解説**

- **`HOST` は `localhost`**: MySQL では `'ユーザー'@'localhost'`（Unixソケット接続）と `'...'@'127.0.0.1'`（TCP接続）を**別物**として扱います。同一マシンならソケット接続（`localhost`）が設定いらずで確実です。次の 14-4 で作るユーザーも `@'localhost'` に揃えます。
- **`utf8mb4`**: 絵文字も含む完全な UTF-8。日本語運用でも文字化けしません。
- **秘密情報（`DB_PASSWORD`）は環境変数**で渡し、コード/Gitには載せません。

---

## 14-4. 【無停止】MySQL に DB と接続ユーザーを作る

Ubuntu の MySQL 8 は管理者(root)が OS 認証なので `sudo mysql` で入れます。

```
$ sudo mysql -e "CREATE DATABASE IF NOT EXISTS shift_manager CHARACTER SET utf8mb4;
  CREATE USER IF NOT EXISTS 'shift'@'localhost' IDENTIFIED BY '<強いパスワードを決める>';
  GRANT ALL PRIVILEGES ON shift_manager.* TO 'shift'@'localhost';
  FLUSH PRIVILEGES;"
```

- 空のデータベース `shift_manager` を作成（中身は次のステップで入れる）。
- アプリ専用ユーザー `shift`（`@localhost`）を作り、そのDBの全権限を与える。

> 🔰 ここで決めたパスワードは、後の移行コマンドと systemd 設定（14-6）で使うので控えておきます。

---

## 14-5. 本番データベースを用意する

本番のMySQLにテーブルを作ります。これは**開発のSQLiteとは別のデータベース**です。通常はここから「新規」で始めます。

### 基本：新規に本番DBを用意する（推奨）

空のMySQLにスキーマを作り、**本物の管理者を1人だけ**作ります。**開発の練習データは持ち込みません。**

```
# ① テーブルを作成（migrate）
$ DJANGO_DB=mysql DB_PASSWORD='<14-4のパスワード>' \
    ./venv/bin/python manage.py migrate

# ② 本番の管理者を作成（createsuperuser）
$ DJANGO_DB=mysql DB_PASSWORD='<14-4のパスワード>' \
    ./venv/bin/python manage.py createsuperuser
```

`Applying ... OK` が並べばテーブル作成完了。あとは**アプリの管理画面（S6 アカウント管理）**からクルー等の実アカウントを作成します。こうすれば本番DBには**本物のデータだけ**が入ります。

### 移行：既存の「本物の運用データ」を移す場合だけ

**すでにSQLiteで本番運用していて、移したい本物のデータがある**ときに限り、`dumpdata`→`loaddata` を使います。

> ⚠️ **開発・テストで作った練習データを本番DBに流し込まないこと。** 移すのは本物の運用データだけです（[12章](12_開発編のまとめ.md) の環境分離）。混ぜると本物と練習の区別が付かなくなります。

```
# (保険) まずバックアップ: cp db.sqlite3 db.sqlite3.bak
# 本物データのある環境で、SQLiteから書き出す
$ ./venv/bin/python manage.py dumpdata \
    --natural-foreign --natural-primary \
    --exclude contenttypes --exclude auth.permission \
    --exclude sessions.session --exclude admin.logentry \
    --indent 2 -o datadump.json

# migrate 済みの本番MySQLへ流し込む（dumpに管理者が含まれるので createsuperuser は不要）
$ DJANGO_DB=mysql DB_PASSWORD='<14-4のパスワード>' \
    ./venv/bin/python manage.py loaddata datadump.json
Installed N object(s) from 1 fixture(s)
```

- `--exclude contenttypes` / `--exclude auth.permission`: `migrate` が**自動で作り直す**テーブル。含めると `IntegrityError` になるので除外。
- `--natural-foreign --natural-primary`: contenttype 参照を「アプリ名＋モデル名」で表し、移行先でズレないように。
- `sessions`（ログインセッション）は移さなくてよいので除外。

> ⚠️ `datadump.json` には**個人データ・パスワードハッシュ**が入るので、`.gitignore` に入れ、移行後は削除します。

---

## 14-6. 【切替】接続先を MySQL にする（systemd drop-in）

最後に、稼働中の `shiftmanager` サービスの接続先を MySQL へ向けます。ここでは**元のユニットファイルを直接編集せず**、`drop-in`（追加設定ファイル）で上書きします。

drop-in を使う利点:

- 13章で**自動生成した `SECRET_KEY` をそのまま保てる**（ユニットを作り直さない）。
- 設定が分離されて見通しが良い。
- **このファイルを消すだけで元（SQLite）に戻せる**＝ロールバックが簡単。

```
$ sudo mkdir -p /etc/systemd/system/shiftmanager.service.d
$ printf '%s\n' '[Service]' 'Environment=DJANGO_DB=mysql' \
    'Environment=DB_PASSWORD=<14-4のパスワード>' \
    | sudo tee /etc/systemd/system/shiftmanager.service.d/mysql.conf >/dev/null
$ sudo chmod 640 /etc/systemd/system/shiftmanager.service.d/mysql.conf   # 鍵/パスワード保護
$ sudo systemctl daemon-reload
$ sudo systemctl restart shiftmanager
```

> 🔰 `DB_PASSWORD` のような秘密情報は、この **root 権限で保護された drop-in（Git管理外）** に置きます。リポジトリには絶対に入れません（[10章](10_GitHubで管理.md)）。

---

## 14-7. 動作確認 ― 本当に MySQL で動いているか

```
# サービスが動いているか
$ systemctl is-active shiftmanager
active

# 稼働中プロセスが実際に MySQL 設定で動いているか（秘密値は出さずDJANGO_DBだけ確認）
$ PID=$(systemctl show shiftmanager -p MainPID --value)
$ tr '\0' '\n' < /proc/$PID/environ | grep '^DJANGO_DB='
DJANGO_DB=mysql

# Nginx 経由で応答するか
$ curl -s -o /dev/null -w "%{http_code}\n" http://localhost/login/
200

# MySQL に移行データが入っているか
$ sudo mysql -e "SELECT COUNT(*) FROM shift_manager.accounts_user;"
```

ログイン画面が出て、誤ったパスワードで**ログイン失敗メッセージ（500ではなく）が返る**なら、ユーザーテーブルへの問い合わせ＝MySQL読み取りが成功している証拠です。

---

## 14-8. ロールバック ― うまくいかないとき

切替後に不具合が出たら、**drop-in を消して再起動するだけ**で SQLite に戻せます。`db.sqlite3` は触っていないので、移行直前の状態に即復帰します。

```
$ sudo rm /etc/systemd/system/shiftmanager.service.d/mysql.conf
$ sudo systemctl daemon-reload
$ sudo systemctl restart shiftmanager
```

> 🔰 「戻せる経路を最初から用意しておく」のが本番作業の鉄則です。今回は ①SQLiteファイルを残す ②接続先を環境変数で切替、の2点で安全に戻せる設計にしています。

---

## 14-9. 後片付けと、これからの運用

- **移行ダンプを削除**: `rm datadump.json`（個人データを含むため）。バックアップ `db.sqlite3.bak` も不要になったら安全に削除。
- **バックアップ方法が変わる**: これからは SQLite ファイルのコピーではなく `mysqldump` を使います。
  ```
  $ mysqldump -u shift -p shift_manager > backup_$(date +%F).sql
  ```
  復元は `mysql -u shift -p shift_manager < backup_YYYY-MM-DD.sql`。アップロードPDFの `media/` も併せて定期取得。
- **コード更新時の手順は同じ**: `git pull` →（モデル変更があれば）`DJANGO_DB=mysql DB_PASSWORD=... migrate` → `collectstatic` → `sudo systemctl restart shiftmanager`。DB接続情報は drop-in にあるので、systemd 経由の起動では環境変数を毎回渡す必要はありません（手動コマンドのときだけ付けます）。

---

## つまずきポイント

- **`mysqlclient` が pip で入らない** → OSの開発ライブラリ不足（14-2の `default-libmysqlclient-dev build-essential pkg-config`）。
- **`Access denied for user 'shift'@'...'`** → ユーザーの**ホスト指定**ズレ。`HOST=localhost`（ソケット）なら `'shift'@'localhost'`、`127.0.0.1`（TCP）なら `'shift'@'127.0.0.1'` か `@'%'` が必要。本章は `localhost` に統一。
- **`loaddata` で IntegrityError（duplicate entry）** → `dumpdata` で `contenttypes` と `auth.permission` を除外し忘れている（14-5②）。
- **`Authentication plugin 'caching_sha2_password' ...` で接続できない** → MySQL 8 の既定認証に古いドライバが対応していない。`./venv/bin/pip install -U mysqlclient` でドライバを最新化する（本章のmysqlclient 2.2系なら通常は問題なし）。
- **日本語が文字化け** → DBの文字コードが `utf8mb4` か、`OPTIONS={'charset':'utf8mb4'}` を確認。
- **切替後に全ページ 500** → `DB_PASSWORD` の誤り、または MySQL 未起動（`systemctl status mysql`）。まずロールバック（14-8）して落ち着いて確認。

---

## この章のまとめ

- MySQL は**本番のデータベース**。開発(SQLite)とは分け、**本番DBに開発の練習データを入れない**（[12章](12_開発編のまとめ.md) の環境分離）。
- 基本は**新規DB**：`migrate`＋`createsuperuser`で空から始め、実アカウントはアプリで作成。**本物の運用データがある場合だけ** `dumpdata`→`loaddata` で移行する（contenttypes等を除外）。
- 接続先は systemd drop-in で切替え、移行する場合は **SQLite ファイルを残してロールバック**可能にした。
- バックアップは `mysqldump` に切り替えた。

これで、シフト提出アプリは同時アクセスにも強い MySQL バックエンドで運用できるようになりました。

次章では、このWSL上の本番を **同じLANの他端末から開ける**ようにします。

➡️ [15章 LANに公開する](15_LANへの公開.md)
