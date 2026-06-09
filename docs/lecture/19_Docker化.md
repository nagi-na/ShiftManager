# 19章 Docker化（発展編）

> 🔰 この章は **18章（終章）の後の発展編（付録）** です。これまで「サーバーに直接インストールして動かす」方法でデプロイしてきました。本章ではそれを **Docker（ドッカー）** で“箱詰め”し、**どのPC・どのサーバーでも同じように動く**形にします。Docker は未経験の前提で、用語には都度かんたんな注釈を付けます。
>
> 分量が多いので、**前半（Dockerを理解し、アプリ1つをコンテナにする）** と **後半（複数サービスをまとめて動かす）** に分けています。

---

# 前半：Dockerを理解し、アプリをコンテナにする

## 19-0. Docker とは何か（たとえ話）

これまでの手順では、サーバーに Python・依存パッケージ・MySQL・Nginx…と**いろいろインストール**してきました。問題は「**自分の環境では動くのに、別のサーバーだと動かない**」（OSやバージョンの違い）が起きやすいこと。

**Docker** は、アプリ本体と「動くのに必要な環境一式（Python本体・ライブラリ・設定）」を**ひとつの箱に固めて持ち運べる**ようにする道具です。

> たとえると：料理（アプリ）を、材料・調味料・調理器具ごと**お弁当箱**に詰めて渡すイメージ。受け取った人は箱を開けて温めるだけ。台所（サーバー）の違いに左右されません。

### Docker のメリット

- **「私の環境では動く」問題が消える**：同じ箱なら、開発PCでも本番サーバーでも**まったく同じ**ように動く（再現性）。
- **セットアップが速い・簡単**：`apt install …` を何度も打つ代わりに、**1〜2コマンド**で一式が立ち上がる。
- **隔離される**：アプリごとに箱が独立。**他のアプリや、開発と本番が混ざらない**（[12章の環境分離](12_開発編のまとめ.md) と相性が良い）。
- **使い捨て・やり直しが楽**：箱を捨てて作り直せる。バージョンを固定でき、ロールバックも容易。
- **移植性**：箱（イメージ）をそのまま別のサーバーへ持っていける。

### Kubernetes（クバネティス）との関係

ときどき一緒に語られる **Kubernetes（K8s）** は、「**たくさんの箱（コンテナ）を、複数台のサーバーに渡って自動で配置・増減・復旧する**」ための、もっと大規模な管理ツール（オーケストレーション＝指揮）です。

- **Docker**：1台のマシンでコンテナを作って動かす道具（本章で扱うのはここ）。
- **Kubernetes**：コンテナが何十・何百になり、複数サーバーで冗長化したくなったときの仕組み。

> 🔰 シフト提出アプリの規模なら **Docker（＋次節の compose）で十分**。Kubernetes は「もっと大きくなってから」で構いません。

## 19-1. 基本の用語（4つだけ）

| 用語 | 読み | ざっくり意味 |
| --- | --- | --- |
| **イメージ** | image | アプリ＋環境を固めた**“ひな型”**（お弁当の冷凍パック）。これを元にコンテナを作る。 |
| **コンテナ** | container | イメージから起動した**“実際に動いている箱”**（温めた弁当）。何個でも作れる。 |
| **Dockerfile** | ― | イメージの**作り方を書いたレシピ**ファイル。 |
| **docker compose** | ― | 複数のコンテナ（アプリ・DB・Nginx等）の構成を**1ファイルにまとめて一括起動**する道具。 |

流れ：**Dockerfile（レシピ）→ build（ビルド）→ イメージ（ひな型）→ run（実行）→ コンテナ（動いてる箱）**。

## 19-2. Docker の準備

Docker をインストールします（環境により方法が異なるので公式に従うのが確実）。

```
# 例: Ubuntu。Docker Engine と compose プラグインを入れる
$ sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin
$ sudo systemctl enable --now docker
$ docker --version            # ✅ バージョン表示
$ docker compose version      # ✅ compose も使える
```

> 🔰 毎回 `sudo` を打つのが面倒なら、自分を `docker` グループに入れます（`sudo usermod -aG docker $USER` → 再ログイン）。本章では分かりやすさのため `sudo` を省略表記します。

## 19-3. アプリの「レシピ」= Dockerfile を書く

プロジェクト直下に **`Dockerfile`**（拡張子なし）を作ります。中身は「Python環境を用意 → 依存を入れる → コードを入れる → 静的ファイルを集める → Gunicornで起動」というレシピです。

ファイル: `Dockerfile`

```dockerfile
# ベースとなる“ひな型”。Python 3.12 の軽量版（slim）を土台にする
FROM python:3.12-slim

# Pythonのログを即時出力・キャッシュ抑制（コンテナ向けの定番設定）
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# コンテナ内の作業ディレクトリ
WORKDIR /app

# （MySQLドライバ mysqlclient をビルドする場合のみ必要。SQLiteだけなら丸ごと省略可）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential default-libmysqlclient-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 依存だけ先にコピーして入れる（コードより変わりにくく、再ビルドが速くなる）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# アプリのコードを全部コピー
COPY . .

# 静的ファイルを集約（イメージに含めておく。DB不要なので鍵はダミーで可）
RUN DJANGO_SECRET_KEY=build-only DJANGO_DEBUG=1 python manage.py collectstatic --noinput

# このコンテナは8000番で待ち受ける、という宣言（実際の公開は後半でNginxが担当）
EXPOSE 8000

# コンテナ起動時に実行するコマンド（Gunicornでアプリを起動）
CMD ["gunicorn", "shift_manager.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
```

> 🔰 **`COPY requirements.txt` を先に**するのがコツ。Dockerは行ごとに結果を**キャッシュ**するので、コードだけ変えたときに「依存の再インストール」を飛ばせて速くなります。

## 19-4. 箱に入れないものリスト = .dockerignore

`.gitignore` と同じ発想で、イメージに**入れたくないもの**を `.dockerignore` に書きます（venvやDBファイル等は箱に不要）。

ファイル: `.dockerignore`

```
venv/
*.pyc
__pycache__/
db.sqlite3
staticfiles/
media/
.git/
.env
deploy/certs/
.claude/
docs/
```

## 19-5. ビルドして単体で動かしてみる

レシピからイメージを作り（build）、コンテナとして起動（run）します。まずはアプリ単体（DBはSQLite）で動作確認。

```
# レシピからイメージを作る（末尾の . は「いまのフォルダのDockerfileを使う」の意味）
$ docker build -t shiftmanager:latest .

# コンテナとして起動。-p で「PCの8000番 → コンテナの8000番」をつなぐ
#   -e は環境変数。SECRET_KEYは英数字推奨、ALLOWED_HOSTSにアクセス先を入れる
$ docker run --rm -p 8000:8000 \
    -e DJANGO_DEBUG=0 \
    -e DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1 \
    -e DJANGO_SECRET_KEY=$(python3 -c "import secrets,string;print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(64)))") \
    shiftmanager:latest
```

別ターミナルで確認：

```
$ curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/login/   # 200
```

> 🔰 用語：`-p 8000:8000`＝**ポート公開**（PC側ポート:コンテナ側ポート）。`-e KEY=値`＝**環境変数**を渡す。`--rm`＝終了時にコンテナを自動削除（使い捨て）。`Ctrl+C` で停止。
>
> ⚠️ この単体起動はSQLite・静的配信なし（Gunicorn直）の**確認用**。実運用は後半の compose（Nginx＋MySQL付き）で行います。

---

# 後半：compose で「本番一式」をまとめて動かす

前半はアプリ1個でした。実運用には **アプリ（Gunicorn）＋ Nginx ＋ MySQL** の3つが要ります。これらを **docker compose** で1ファイルにまとめ、**1コマンドで全部**立ち上げます。

## 19-6. 構成図

```
[ブラウザ] →(80)→ [nginxコンテナ] ─/static,/media→ 共有ボリュームから配信
                        └ それ以外 →(8000)→ [webコンテナ(Gunicorn+Django)] →(3306)→ [dbコンテナ(MySQL)]
```

- 各サービスは**別々のコンテナ**。`web` から DB へは、ホスト名 `db`（＝サービス名）でつながる（composeが**コンテナ間ネットワーク**を自動で用意）。
- **ボリューム**（volume：コンテナの外に置く永続データ置き場）で、**DBの中身**と**静的/メディアファイル**をコンテナを作り直しても消えないようにする。

## 19-7. 設定ファイル（3つ＋HTTPS公開時の追加設定）

### ① 秘密情報は `.env`（Git管理外）

ファイル: `.env`（`.gitignore` 済みのこと。値は自分のものに）

```
SECRET_KEY=英数字64文字くらいのランダム
DB_PASSWORD=アプリ用DBパスワード
DB_ROOT_PASSWORD=MySQLのroot用パスワード
ALLOWED_HOSTS=localhost,127.0.0.1
HTTP_PORT=80          # 公開ポート（既定80。ホストの80が埋まっていれば 8080 等に）
# Cloudflare等でHTTPS公開するときに信頼するオリジン（スキーム付き・カンマ区切り）
CSRF_TRUSTED_ORIGINS=https://example.com
```

> ⚠️ `.env` には秘密情報が入るので **絶対にコミットしない**（`.dockerignore`/`.gitignore` に `.env`）。SECRET_KEY は英数字推奨（記号は `.env` の引用符でハマりやすい）。

### ② Nginx 設定（compose用）

ファイル: `deploy/nginx-docker.conf`

```nginx
# 上位(Cloudflare等)が付けた X-Forwarded-Proto を尊重し、無ければ $scheme を使う。
# Cloudflare→nginx はHTTPなので $scheme だけだと https が伝わらず CSRF が失敗する。
map $http_x_forwarded_proto $fwd_proto {
    default $http_x_forwarded_proto;
    ""      $scheme;
}

server {
    listen 80;
    server_name _;                 # ホスト名を問わず受ける
    client_max_body_size 12m;

    location /static/ { alias /app/staticfiles/; }   # 共有ボリュームから配信
    # 確定シフト等のメディアは internal。Django(@login_required)が
    # X-Accel-Redirect: /protected/... を返したときだけ送信（7-7）。
    location /protected/ { internal; alias /app/media/; }
    location / {
        proxy_pass http://web:8000;                  # web＝アプリのサービス名
        proxy_set_header Host $http_host;            # ポートも保持（CSRFのOrigin照合）
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $fwd_proto;   # 上位のhttpsを保持
    }
}
```

### ③ 構成本体 `compose.yaml`

ファイル: `compose.yaml`（プロジェクト直下）

```yaml
services:
  db:                                  # MySQL
    image: mysql:8
    environment:
      MYSQL_DATABASE: shift_manager
      MYSQL_USER: shift
      MYSQL_PASSWORD: ${DB_PASSWORD}        # .env から読む
      MYSQL_ROOT_PASSWORD: ${DB_ROOT_PASSWORD}
    volumes:
      - dbdata:/var/lib/mysql            # DBの中身を永続化
    restart: unless-stopped              # 落ちても自動再起動

  web:                                   # アプリ（Gunicorn+Django）
    build: .                             # 同じフォルダの Dockerfile からビルド
    environment:
      DJANGO_DEBUG: "0"
      DJANGO_ALLOWED_HOSTS: ${ALLOWED_HOSTS}
      DJANGO_SECRET_KEY: ${SECRET_KEY}
      DJANGO_DB: mysql
      DB_HOST: db                        # ← DBコンテナのサービス名で接続
      DB_PASSWORD: ${DB_PASSWORD}
      # Cloudflare等がHTTPSを終端する構成。CSRFのOrigin照合に必要。
      DJANGO_CSRF_TRUSTED_ORIGINS: ${CSRF_TRUSTED_ORIGINS}
      DJANGO_BEHIND_TLS_PROXY: "1"       # X-Forwarded-Proto=https を信頼しhttps受信と認識
    volumes:
      - staticfiles:/app/staticfiles     # Nginxと共有
      - media:/app/media
    depends_on: [db]                     # dbの後に起動
    restart: unless-stopped

  nginx:                                 # 前段Webサーバー
    image: nginx:1.27
    ports: ["${HTTP_PORT:-80}:80"]       # 公開ポート(既定80)。外に出すのはここだけ
    volumes:
      - ./deploy/nginx-docker.conf:/etc/nginx/conf.d/default.conf:ro
      - staticfiles:/app/staticfiles:ro
      - media:/app/media:ro
    depends_on: [web]
    restart: unless-stopped

volumes:                                 # 永続データの置き場（名前付きボリューム）
  dbdata:
  staticfiles:
  media:
```

> 🔰 用語：`services` の各項目（db/web/nginx）が**コンテナ1つ**。`image:` は既成イメージ、`build: .` は自前Dockerfileから作る。`volumes:` でデータ永続化と共有。`depends_on:` で起動順。`ports: "80:80"` で**外に出すのはNginxの80番だけ**（web/dbは内部だけ＝安全）。

### ④ Cloudflare等でHTTPS公開するときの CSRF 対策

`http://localhost/` では問題なく動いていたのに、**Cloudflare（[16章](16_Cloudflareトンネルで公開.md)）経由でログインすると403（CSRF失敗）**になることがあります。理由を順に追うと：

1. ブラウザ ↔ Cloudflare は **HTTPS**。だからブラウザはPOST時に `Origin: https://あなたのドメイン` を送る。
2. Cloudflare ↔ オリジン（このnginx:80）は **HTTP**。つまりDjangoにはHTTPで届く。
3. Django(DEBUG=False) は「自分はhttpで受けた」と思い、正しいOriginを `http://…` と組み立てる。
4. 送られてきた `https://…` と一致せず、**「Origin checking failed」でCSRF失敗**。

直すには **3つのファイル**にそれぞれ一手ずつ入れます（上の①②③で既に反映済み）。

| ファイル | 入れるもの | ねらい |
| --- | --- | --- |
| `.env`（①） | `CSRF_TRUSTED_ORIGINS=https://あなたのドメイン` | 信頼するhttpsオリジンを宣言 |
| `compose.yaml`（③） | `DJANGO_CSRF_TRUSTED_ORIGINS`／`DJANGO_BEHIND_TLS_PROXY="1"` | ①を渡す＋「httpsで受けた」と認識させる |
| `deploy/nginx-docker.conf`（②） | `map` で `X-Forwarded-Proto` を上位尊重 | Cloudflareの「https」をDjangoまで伝える |

```python
# settings.py 側（既に対応済み）。環境変数で切り替える。
if os.environ.get('DJANGO_BEHIND_TLS_PROXY') == '1':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')  # XFP=https を信頼

_csrf = os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS')
if _csrf:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf.split(',') if o.strip()]
```

> 🔰 **なぜnginxに `map` が要るか**：素朴に `proxy_set_header X-Forwarded-Proto $scheme;` と書くと、nginx自身が受けたスキーム（＝http）で**上書き**してしまい、Cloudflareが付けた「https」が消えます。`map` で「上位の値があればそれを使い、無ければ$scheme」とすることで、Cloudflare経由はhttps・直アクセス(localhost)はhttp、と両立できます。
>
> 🔑 信頼オリジンは**スキーム付き**（`https://example.com`）で、`http://` とは別物。複数あれば `.env` でカンマ区切り。変更後は `docker compose up -d`（webの再作成）＋ `docker compose exec nginx nginx -s reload`（nginx設定の再読込）で反映します。
>
> ⚠️ セキュアCookie（`DJANGO_SECURE_COOKIES=1`）を有効にすると Cookie に Secure 属性が付き、`http://localhost` 直アクセスではログインが維持できなくなります。**Cloudflare(HTTPS)のみで運用するとき**だけ有効化してください。

## 19-8. 起動と初期設定

```
# ビルドして全コンテナをバックグラウンド(-d)起動
$ docker compose up -d --build

# 状態を見る（全部 running / healthy か）
$ docker compose ps

# 初回だけ：DBにテーブルを作り、管理者を作成（webコンテナの中で実行）
$ docker compose exec web python manage.py migrate
$ docker compose exec web python manage.py createsuperuser
# このアプリの管理権限は role で判定。createsuperuser は role を付けないので admin にする
$ docker compose exec web python manage.py shell -c "from accounts.models import User; u=User.objects.get(username='admin'); u.role='admin'; u.save()"
```

ブラウザで `http://localhost/` を開き、ログインできれば成功です（静的ファイルも当たっているはず）。

> 🔰 `docker compose exec web …`＝**動いている web コンテナの中でコマンドを実行**。`migrate` や `createsuperuser` はこの形で行います（[14章](14_MySQLの導入.md) と同じ作業をコンテナ内で実施）。**開発の練習データは持ち込まない**方針は同じです。
>
> 🔰 **コード更新時の `migrate`**（19-9表の「コード更新を反映」）は、`git pull` で増えたマイグレーション（差分）だけを当てるもので、**`dbdata` ボリュームの既存データは保持**されます（しくみは [2章 2-4](02_データモデルとマイグレーション.md)）。データが消えるのは `down -v` を付けたときだけ。

## 19-9. 日常の操作（compose 早見表）

| やりたいこと | コマンド |
| --- | --- |
| 起動（ビルド込み） | `docker compose up -d --build` |
| 停止（コンテナ削除・**データは残る**） | `docker compose down` |
| 状態確認 | `docker compose ps` |
| ログ追尾 | `docker compose logs -f web`（`nginx`/`db`も同様） |
| 再起動 | `docker compose restart web` |
| コンテナ内でコマンド | `docker compose exec web python manage.py migrate` |
| コード更新を反映 | `git pull && docker compose up -d --build`（必要なら `exec web … migrate`） |
| **完全削除（ボリュームも！）** | `docker compose down -v` ⚠️ **DBの中身も消える** |

> ⚠️ `docker compose down -v` の **`-v` はボリューム（DBの中身・media）まで削除**します。データを消したくないときは付けないこと。
>
> 🔰 コード更新は `git pull` → `up -d --build`（イメージを作り直し）。`down -v` を使わない限りDBは保持されます。これが「使い捨てつつデータは守る」Dockerらしい運用です。

## 19-10. これまでの構成との対応・利点

| これまで（直接インストール） | Docker（compose） |
| --- | --- |
| `apt install` を各種・手作業 | `compose.yaml` に宣言、`up` 一発 |
| systemd で Gunicorn 常駐 | `restart: unless-stopped` が同じ役割 |
| Nginx を OS に設定 | nginxコンテナ＋設定ファイルをマウント |
| MySQL を OS に導入 | dbコンテナ＋名前付きボリューム |
| 秘密情報は systemd drop-in | `.env`（Git外）＋ `environment:` |

→ **開発と本番、他アプリとの混在が起きにくく**（A-0の根本対策）、別サーバーへは「リポジトリ＋`.env`を置いて `up` するだけ」で再現できます。

> ⚠️ HTTPS公開は、Cloudflare Tunnel（[16-17章](16_Cloudflareトンネルで公開.md)）の `cloudflared` を nginx の前に置く（もう1コンテナ追加 or ホスト側で実行）形にできます。証明書を自前で持つ場合は nginx コンテナに443と証明書ボリュームを足します。

## つまずきポイント

- **`web` が `db` に繋がらない（起動直後に500）** → DBの初期化が間に合っていない。少し待って再試行、または `depends_on` に加えてヘルスチェックで待つ設定にする。
- **`Access denied`（DB認証）** → `.env` の `DB_PASSWORD` と compose の値、`DB_HOST=db` を確認。コンテナ間はTCP接続なのでMySQLユーザーは `@'%'`（mysqlイメージ既定）でOK。
- **静的ファイルが出ない** → `staticfiles` ボリュームを web と nginx の**両方にマウント**しているか。イメージビルド時の `collectstatic` 済みか。
- **`down -v` でデータが消えた** → `-v` はボリューム削除。通常の停止は `down`（`-v` なし）。
- **`.env` が効かない** → `compose.yaml` と同じフォルダに `.env` を置く。値に記号が多いとハマりやすい（英数字推奨）。
- **localhostでは動くがCloudflare経由のログインで403（CSRF）** → HTTPS終端構成での典型。`.env` の `CSRF_TRUSTED_ORIGINS`、compose の `DJANGO_BEHIND_TLS_PROXY=1`、nginx の `X-Forwarded-Proto` 尊重(`map`)の3点を確認（19-7 ④）。

## この章のまとめ

- **前半**：Docker は「アプリ＋環境を箱詰め」して、どこでも同じに動かす道具。`Dockerfile`（レシピ）→ build → イメージ → run → コンテナ、が基本の流れ。
- **後半**：`compose.yaml` で **アプリ＋Nginx＋MySQL を1コマンド**で起動。秘密情報は `.env`、データは**ボリューム**で永続化。
- これまでの systemd/Nginx/MySQL 構成と**役割は同じ**だが、**再現性・隔離・移植性**が大きく上がる。Kubernetes は規模が大きくなってからの選択肢。

➡️ 講座の本編は [18章 全体のまとめ](18_全体のまとめ.md) で完結しています。本章は余力のある人向けの発展編です。
