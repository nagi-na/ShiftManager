# ShiftManager アプリ（Django + Gunicorn）のイメージ
FROM python:3.12-slim

# Pythonのログを即時出力・キャッシュ抑制（コンテナ向けの定番）
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# mysqlclient のビルドに必要（requirements.txt に mysqlclient を含むため）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential default-libmysqlclient-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 依存だけ先に入れる（キャッシュが効いて再ビルドが速い）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリ本体をコピー
COPY . .

# 静的ファイルを集約（DB不要。鍵はビルド用ダミーでよい）
RUN DJANGO_SECRET_KEY=build-only DJANGO_DEBUG=1 python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["gunicorn", "shift_manager.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
