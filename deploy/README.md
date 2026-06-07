# デプロイ用ファイル（このPCで練習する手順）

このPC（WSL）で「本番そっくりの構成」を組むための設定ファイルと手順です。
講座 [12章 本番運用](../docs/lecture/12_本番運用.md) の実践版にあたります。

構成:

```
ブラウザ → Nginx(:80) ┬─ /static/, /media/ → ファイルを直接配信
                       └─ それ以外          → Gunicorn(:8000) → Django
```

---

## 0. 事前準備（済んでいる前提）

- `DJANGO_DEBUG` / `DJANGO_ALLOWED_HOSTS` で本番/開発を切り替えられる（`settings.py`）。
- `./venv/bin/python manage.py collectstatic` で `staticfiles/` を作成済み。

## 1. Gunicorn を起動（手動・動作確認用）

```bash
cd /home/nagin/ShiftManager
DJANGO_DEBUG=0 DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1 \
  ./venv/bin/gunicorn shift_manager.wsgi:application --bind 127.0.0.1:8000
```

## 2. Nginx を入れて設定を適用

```bash
sudo apt-get update && sudo apt-get install -y nginx

# 設定を配置して有効化（既定サイトは無効化）
sudo cp deploy/nginx-shiftmanager.conf /etc/nginx/sites-available/shiftmanager
sudo ln -sf /etc/nginx/sites-available/shiftmanager /etc/nginx/sites-enabled/shiftmanager
sudo rm -f /etc/nginx/sites-enabled/default

sudo nginx -t            # 設定文法チェック
sudo systemctl reload nginx
```

確認:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost/login/             # 200
curl -s -o /dev/null -w "%{http_code}\n" http://localhost/static/admin/css/base.css  # 200（Nginxが配信）
```

## 3. Gunicorn を常駐化（systemd）

```bash
sudo cp deploy/gunicorn-shiftmanager.service /etc/systemd/system/shiftmanager.service
# SECRET_KEY を本番用に書き換える（生成コマンドはサービスファイル内のコメント参照）
sudo systemctl daemon-reload
sudo systemctl enable --now shiftmanager
sudo systemctl status shiftmanager
```

## 4. コードやテンプレートを更新したら

```bash
git pull                                   # 別PCから更新を取り込む場合
./venv/bin/python manage.py migrate        # モデル変更があれば
./venv/bin/python manage.py collectstatic --noinput  # 静的ファイル変更があれば
sudo systemctl restart shiftmanager        # アプリを再起動
```

---

⚠️ パス（`/home/nagin/ShiftManager`）やユーザー名はこの環境固有です。別サーバーへ移すときは各ファイルのパス・`User=`・`server_name`・`ALLOWED_HOSTS` を実際の値へ変更してください。
