
# 15章 Cloudflareトンネルでインターネット公開する

> 🔰 この章も **運用編** です。[14章](14_LANへの公開.md) でLAN内に公開したアプリを、**インターネットから・正規のHTTPSで**アクセスできるようにします。前提環境（Ubuntu/WSL2・`systemd`、稼働中の Nginx+Gunicorn+systemd 構成）は 12〜14章と同じです。

## 15-0. なぜ Cloudflare Tunnel か

家庭や学外からインターネット公開しようとすると、ふつうは次の壁にぶつかります。

- **ポート開放**：ルーターで80/443を開ける必要があり、設定もリスクもある。
- **CGNAT**：多くの家庭回線は固定の公開IPを持たず、そもそもポート開放できない。
- **証明書**：HTTPSにするには公開ドメイン＋証明書が要る（[12章](12_本番運用.md) で先送りにした課題）。

**Cloudflare Tunnel** はこれらを一気に解決します。仕組みは「**内側から外へ**」トンネルを張る方式です。

```
インターネット ──HTTPS──> Cloudflare ──暗号トンネル──> cloudflared(WSL) ──> Nginx:80 → Gunicorn → Django
```

- `cloudflared` がWSLから Cloudflare へ**外向き接続**を張るので、**ポート開放も公開IPも不要**（CGNATでもOK）。
- HTTPSは **Cloudflareが正規証明書で終端**してくれる（証明書の用意・更新が不要）。

### 2つのモード

| モード | 必要なもの | URL | 用途 |
| --- | --- | --- | --- |
| **クイックトンネル**（本章） | 不要（アカウントもドメインも不要） | `https://ランダム.trycloudflare.com`（一時的・起動ごとに変わる） | まず試す・動作確認 |
| 名前付きトンネル（15-6） | Cloudflareアカウント＋CF管理下のドメイン | 自分のドメイン（固定・恒久） | 本番運用 |

本章は **クイックトンネル**で「動く」ところまでを作ります。

---

## 15-1. cloudflared を導入する

`cloudflared` は単一バイナリで、`sudo` なしで自分のホームに置けます。

```
$ mkdir -p ~/.local/bin
$ curl -sSL -o ~/.local/bin/cloudflared \
    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
$ chmod +x ~/.local/bin/cloudflared
$ ~/.local/bin/cloudflared --version
cloudflared version 2026.x.x ...
```

---

## 15-2. Django を「外部ホスト・プロキシ経由HTTPS」に対応させる

Cloudflare 経由だと、Django には次の2点が必要です。

1. **公開ホスト名を許可**：`DEBUG=False` では `ALLOWED_HOSTS` に無いホストは 400 で拒否される。クイックトンネルのURLは毎回変わるので、**`.trycloudflare.com`（サブドメイン全体のワイルドカード）** を許可します。
2. **HTTPSをDjangoに伝える＋CSRF**：CloudflareがHTTPSを終端し、内部へは `X-Forwarded-Proto: https` を付けて中継します。これをDjangoに教え（`SECURE_PROXY_SSL_HEADER`）、ログイン等のPOSTのために `CSRF_TRUSTED_ORIGINS` を設定します。

`settings.py` には、これらを**環境変数で切り替える**設定を用意してあります（既定は無効＝従来通り）。

ファイル: `shift_manager/settings.py`（該当箇所）

```python
# 上位がHTTPSを終端して中継する構成（Cloudflare Tunnel等）向け
if os.environ.get('DJANGO_BEHIND_TLS_PROXY') == '1':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# HTTPS配信時に信頼するオリジン（POST/CSRF用）。ワイルドカード可
_csrf_origins = os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS')
if _csrf_origins:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(',') if o.strip()]
```

これらを **systemd の drop-in** で渡します（元のユニットは触らない）。`tunnel.conf` という名前にすると、既存の drop-in（`lan.conf` 等）より後に読み込まれ、`ALLOWED_HOSTS` を上書きできます。

```
$ printf '%s\n' '[Service]' \
    'Environment=DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,192.168.10.8,.trycloudflare.com' \
    'Environment=DJANGO_BEHIND_TLS_PROXY=1' \
    'Environment=DJANGO_CSRF_TRUSTED_ORIGINS=https://*.trycloudflare.com' \
  | sudo tee /etc/systemd/system/shiftmanager.service.d/tunnel.conf >/dev/null
$ sudo systemctl daemon-reload
$ sudo systemctl restart shiftmanager
```

> 🔰 セキュアCookie（`DJANGO_SECURE_COOKIES`）は**あえて有効化していません**。有効にするとCookieがHTTPS限定になり、並行して使っている **LANのHTTPアクセス（`http://192.168.10.8/`）でログインできなくなる**ためです。Cloudflare経由に一本化するなら有効化してもOK。

---

## 15-3. クイックトンネルを起動する

ローカルの Nginx（80番）に向けてトンネルを張ります。

```
$ ~/.local/bin/cloudflared tunnel --no-autoupdate --url http://localhost:80
...
|  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |
|  https://refine-paperbacks-investment-refer.trycloudflare.com                              |
...
```

表示された `https://〇〇〇.trycloudflare.com` が**公開URL**です（この例の文字列は毎回変わります）。このプロセスが動いている間だけトンネルは生きています。

> 🔰 `--url http://localhost:80` で Nginx に向けるのがポイント。Nginxが静的ファイルを配信し、動的リクエストを Gunicorn へ中継します（Gunicornの8000番に直接向けると静的ファイルが配信されません）。

---

## 15-4. 動作確認

別のターミナル（または別端末）から、表示されたURLを確認します。

```
$ U=https://refine-paperbacks-investment-refer.trycloudflare.com
$ curl -sS -o /dev/null -w "%{http_code}\n" "$U/login/"        # 200
$ curl -sS -o /dev/null -w "%{http_code}\n" "$U/static/admin/css/base.css"  # 200
$ curl -sS -o /dev/null -w "ssl_verify=%{ssl_verify_result}\n" "$U/login/"  # 0（正規証明書）
```

`ssl_verify=0` は **Cloudflareの正規証明書で検証成功**＝ブラウザでも警告の出ない本物のHTTPS、という意味です。

### ✅ 動作確認
- [ ] **スマホのモバイル回線（Wi-Fiを切る）** で公開URLを開き、ログイン画面が**警告なし**で表示される（＝LAN外・インターネットから到達できている）。
- [ ] ログインを試し、認証（POST）が通る（CSRFエラーにならない）。

---

## 15-5. クイックトンネルの注意点

- **URLは一時的**：`cloudflared` を再起動するURLが変わり、停止すると公開も止まる。
- **公開状態**：URLを知っていれば誰でもログイン画面に到達できる。管理者・利用者のパスワードは強固に。
- **稼働保証なし**：`trycloudflare.com` は試用扱い。常用・本番は次の名前付きトンネルへ。

---

## 15-6. 恒久運用（名前付きトンネル）への発展

固定URLで安定運用するには、**自分のドメイン**を Cloudflare に追加し、名前付きトンネルにします（概要）。

1. Cloudflareアカウントを作り、ドメインを追加（ネームサーバをCloudflareに向ける）。
2. `cloudflared tunnel login` でブラウザ認証。
3. `cloudflared tunnel create shift` でトンネル作成。
4. `cloudflared tunnel route dns shift shift.example.com` で公開ホスト名を割当。
5. 設定ファイル（`~/.cloudflared/config.yml`）で `shift.example.com → http://localhost:80` を対応づけ。
6. `cloudflared` を **systemd サービス**として常駐させ、PC起動時に自動でトンネルを張る。

`ALLOWED_HOSTS`・`CSRF_TRUSTED_ORIGINS` は、`.trycloudflare.com` の代わりに**自分のドメイン**（`shift.example.com` / `https://shift.example.com`）に置き換えます。

> 🔰 名前付きトンネルの具体的な構築手順と、公開運用で実際に直したつまずき（ログアウト・セキュアCookie・DBパスワード更新）は、次の [16章](16_名前付きトンネルと運用のつまずき.md) にまとめています。

---

## つまずきポイント

- **`400 Bad Request (DisallowedHost)`** → `ALLOWED_HOSTS` に公開ホスト（`.trycloudflare.com` や自分のドメイン）が入っていない。
- **ログインで `403 (CSRF)`** → `CSRF_TRUSTED_ORIGINS` に `https://...` を設定し、`SECURE_PROXY_SSL_HEADER`（`DJANGO_BEHIND_TLS_PROXY=1`）でHTTPSを認識させる。
- **CSSが当たらない** → トンネルを Gunicorn(8000) ではなく **Nginx(80)** に向ける。
- **起動のたびURLが変わる** → クイックトンネルの仕様。固定したいなら名前付きトンネル（15-6）。
- **トンネルが切れると公開も止まる** → `cloudflared` を常駐（systemd）させる。

---

## この章のまとめ

- `cloudflared` のクイックトンネルで、ポート開放もCGNATも気にせず、**インターネットから正規HTTPSで公開**できた。
- Django側は `ALLOWED_HOSTS`（公開ホスト）＋`SECURE_PROXY_SSL_HEADER`＋`CSRF_TRUSTED_ORIGINS` を環境変数で設定するだけ。
- 恒久運用は、ドメインを使った名前付きトンネル＋`cloudflared` の常駐へ発展できる（次章）。

➡️ [16章 名前付きトンネルでの恒久公開と、運用でのつまずき](16_名前付きトンネルと運用のつまずき.md)
