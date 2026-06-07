# 13章 MySQLの導入 ― 稼働中の本番をアップデートする

> 🔰 この章は **運用編** です。[12章](12_本番運用.md) で公開した本番（Nginx + Gunicorn + systemd、DBは **SQLite**）が**すでに動いていて、クルーが実際にシフトを提出している**前提で、そこへ MySQL を後から導入します。新規構築ではなく「**稼働中のシステムにアップデートを適用する**」作業として進めます。
>
> 前提環境（Ubuntu/WSL2・`systemd`・`apt`）と、`/home/nagin/ShiftManager`・ユーザー `nagin`・サービス名 `shiftmanager` の読み替えは [12章の「前提環境／置換早見表」](12_本番運用.md) と同じです。自分の環境に合わせて置き換えてください。

実運用でDBを入れ替えるときの肝は次の3つです。本章はこれを軸に組み立てます。

1. **データを失わない** ― 既存の提出データを MySQL へ移す（dumpdata → loaddata）。
2. **停止時間を最小に** ― 止めずにできる準備と、短いメンテで行う切替を分ける。
3. **いつでも戻せる** ― SQLite ファイルを残し、設定1つでロールバックする。

---

## 13-0. なぜ・いつ MySQL にするか

SQLite は優秀で、数人〜数十人規模なら本番でも十分です。MySQL を検討する主な理由は **同時書き込み** です。

- SQLite は書き込み時に **DBファイル全体をロック**します。締切直前に全員が一斉提出すると `database is locked` が起きうる、というのが現実的な弱点です。
- MySQL は行単位ロックで同時書き込みに強く、ネットワーク越し・複数アプリサーバーからの共有もできます。

> 🔰 「困っていないなら急いで移す必要はない」が基本です。`database is locked` が出る／利用者が増える／本格運用に乗せる、あたりが移行のサイン。本章は**学習も兼ねて一度経験しておく**価値が高い作業です。

---

## 13-1. 作戦 ― 無停止の準備 → 短いメンテで切替 → 戻せる

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

## 13-2. 【無停止】MySQL とドライバを用意する

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

## 13-3. 【無停止】settings を「DB切替」対応にする

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

- **`HOST` は `localhost`**: MySQL では `'ユーザー'@'localhost'`（Unixソケット接続）と `'...'@'127.0.0.1'`（TCP接続）を**別物**として扱います。同一マシンならソケット接続（`localhost`）が設定いらずで確実です。次の 13-4 で作るユーザーも `@'localhost'` に揃えます。
- **`utf8mb4`**: 絵文字も含む完全な UTF-8。日本語運用でも文字化けしません。
- **秘密情報（`DB_PASSWORD`）は環境変数**で渡し、コード/Gitには載せません。

---

## 13-4. 【無停止】MySQL に DB と接続ユーザーを作る

Ubuntu の MySQL 8 は管理者(root)が OS 認証なので `sudo mysql` で入れます。

```
$ sudo mysql -e "CREATE DATABASE IF NOT EXISTS shift_manager CHARACTER SET utf8mb4;
  CREATE USER IF NOT EXISTS 'shift'@'localhost' IDENTIFIED BY '<強いパスワードを決める>';
  GRANT ALL PRIVILEGES ON shift_manager.* TO 'shift'@'localhost';
  FLUSH PRIVILEGES;"
```

- 空のデータベース `shift_manager` を作成（中身は次のステップで入れる）。
- アプリ専用ユーザー `shift`（`@localhost`）を作り、そのDBの全権限を与える。

> 🔰 ここで決めたパスワードは、後の移行コマンドと systemd 設定（13-6）で使うので控えておきます。

---

## 13-5. 【メンテ開始】データを移す

ここからが実際の入れ替えです。利用が少ない時間に、できれば「提出を一時停止する」案内を出してから短時間で行います。

### ① まず SQLite をバックアップ（保険）

```
$ cp db.sqlite3 db.sqlite3.bak
```

### ② SQLite からデータを書き出す（dumpdata）

```
$ ./venv/bin/python manage.py dumpdata \
    --natural-foreign --natural-primary \
    --exclude contenttypes --exclude auth.permission \
    --exclude sessions.session --exclude admin.logentry \
    --indent 2 -o datadump.json
```

- `--exclude contenttypes` / `--exclude auth.permission`: これらは次の `migrate` が**自動で作り直す**テーブルです。書き出しに含めると、流し込み時に重複して `IntegrityError` になります。だから除外します。
- `--natural-foreign --natural-primary`: contenttype などへの参照を、数値IDではなく「アプリ名＋モデル名」で表現し、移行先でもズレないようにします。
- `sessions`（ログインセッション）は移さなくてよいので除外。

> ⚠️ `datadump.json` には**個人データやパスワードハッシュが入る**ので、`.gitignore` に入れ、移行後は削除します。

### ③ MySQL に空のテーブルを作る（migrate）

```
$ DJANGO_DB=mysql DB_PASSWORD='<13-4のパスワード>' \
    ./venv/bin/python manage.py migrate
```

`Applying ... OK` が並べば、MySQL 側にアプリの全テーブルができています。

### ④ データを流し込む（loaddata）

```
$ DJANGO_DB=mysql DB_PASSWORD='<13-4のパスワード>' \
    ./venv/bin/python manage.py loaddata datadump.json
Installed N object(s) from 1 fixture(s)
```

`Installed N object(s)` が出れば、既存のユーザー・期間・提出データが MySQL に入りました。

---

## 13-6. 【切替】接続先を MySQL にする（systemd drop-in）

最後に、稼働中の `shiftmanager` サービスの接続先を MySQL へ向けます。ここでは**元のユニットファイルを直接編集せず**、`drop-in`（追加設定ファイル）で上書きします。

drop-in を使う利点:

- 12章で**自動生成した `SECRET_KEY` をそのまま保てる**（ユニットを作り直さない）。
- 設定が分離されて見通しが良い。
- **このファイルを消すだけで元（SQLite）に戻せる**＝ロールバックが簡単。

```
$ sudo mkdir -p /etc/systemd/system/shiftmanager.service.d
$ printf '%s\n' '[Service]' 'Environment=DJANGO_DB=mysql' \
    'Environment=DB_PASSWORD=<13-4のパスワード>' \
    | sudo tee /etc/systemd/system/shiftmanager.service.d/mysql.conf >/dev/null
$ sudo chmod 640 /etc/systemd/system/shiftmanager.service.d/mysql.conf   # 鍵/パスワード保護
$ sudo systemctl daemon-reload
$ sudo systemctl restart shiftmanager
```

> 🔰 `DB_PASSWORD` のような秘密情報は、この **root 権限で保護された drop-in（Git管理外）** に置きます。リポジトリには絶対に入れません（[10章](10_GitHubで管理.md)）。

---

## 13-7. 動作確認 ― 本当に MySQL で動いているか

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

## 13-8. ロールバック ― うまくいかないとき

切替後に不具合が出たら、**drop-in を消して再起動するだけ**で SQLite に戻せます。`db.sqlite3` は触っていないので、移行直前の状態に即復帰します。

```
$ sudo rm /etc/systemd/system/shiftmanager.service.d/mysql.conf
$ sudo systemctl daemon-reload
$ sudo systemctl restart shiftmanager
```

> 🔰 「戻せる経路を最初から用意しておく」のが本番作業の鉄則です。今回は ①SQLiteファイルを残す ②接続先を環境変数で切替、の2点で安全に戻せる設計にしています。

---

## 13-9. 後片付けと、これからの運用

- **移行ダンプを削除**: `rm datadump.json`（個人データを含むため）。バックアップ `db.sqlite3.bak` も不要になったら安全に削除。
- **バックアップ方法が変わる**: これからは SQLite ファイルのコピーではなく `mysqldump` を使います。
  ```
  $ mysqldump -u shift -p shift_manager > backup_$(date +%F).sql
  ```
  復元は `mysql -u shift -p shift_manager < backup_YYYY-MM-DD.sql`。アップロードPDFの `media/` も併せて定期取得。
- **コード更新時の手順は同じ**: `git pull` →（モデル変更があれば）`DJANGO_DB=mysql DB_PASSWORD=... migrate` → `collectstatic` → `sudo systemctl restart shiftmanager`。DB接続情報は drop-in にあるので、systemd 経由の起動では環境変数を毎回渡す必要はありません（手動コマンドのときだけ付けます）。

---

## つまずきポイント

- **`mysqlclient` が pip で入らない** → OSの開発ライブラリ不足（13-2の `default-libmysqlclient-dev build-essential pkg-config`）。
- **`Access denied for user 'shift'@'...'`** → ユーザーの**ホスト指定**ズレ。`HOST=localhost`（ソケット）なら `'shift'@'localhost'`、`127.0.0.1`（TCP）なら `'shift'@'127.0.0.1'` か `@'%'` が必要。本章は `localhost` に統一。
- **`loaddata` で IntegrityError（duplicate entry）** → `dumpdata` で `contenttypes` と `auth.permission` を除外し忘れている（13-5②）。
- **`Authentication plugin 'caching_sha2_password' ...` で接続できない** → MySQL 8 の既定認証に古いドライバが対応していない。`./venv/bin/pip install -U mysqlclient` でドライバを最新化する（本章のmysqlclient 2.2系なら通常は問題なし）。
- **日本語が文字化け** → DBの文字コードが `utf8mb4` か、`OPTIONS={'charset':'utf8mb4'}` を確認。
- **切替後に全ページ 500** → `DB_PASSWORD` の誤り、または MySQL 未起動（`systemctl status mysql`）。まずロールバック（13-8）して落ち着いて確認。

---

## この章のまとめ

- 稼働中の本番を止めずに準備し、短いメンテでデータ移行＋接続先切替を行った。
- `dumpdata`（contenttypes等を除外）→ `migrate` → `loaddata` で**データを保全**して移行した。
- systemd drop-in で接続先を切替え、**SQLiteファイルを残すことでいつでもロールバック**できるようにした。
- バックアップは `mysqldump` に切り替えた。

これで、シフト提出アプリは同時アクセスにも強い MySQL バックエンドで運用できるようになりました。

最後に、講座全体と「開発環境と本番環境の構成の違い」を終章で振り返ります。

➡️ [終章 全体のまとめ](終章_全体のまとめ.md)
