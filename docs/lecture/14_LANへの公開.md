# 14章 LANに公開する（WSL + ミラーモード）

> 🔰 この章も **運用編** です。[12章](12_本番運用.md)・[13章](13_MySQLの導入.md) で、WSL上に Nginx + Gunicorn + systemd + MySQL の本番構成が動いている前提で、それを **同じLAN（Wi-Fi）上の他の端末（スマホ・別PC）から開けるように**します。
>
> 前提環境（Ubuntu/WSL2・`systemd`）と、`/home/nagin/ShiftManager`・ユーザー `nagin` 等の読み替えは [12章の「前提環境／置換早見表」](12_本番運用.md) と同じです。LAN IP（本章の例では `192.168.10.8`）は**あなたの環境の値**に置き換えてください。

---

## 14-1. なぜ、そのままでは他の端末から見えないのか

WSL2 は既定で **NAT** という方式で動きます。WSL には LAN とは別の**内部IP（`172.x.x.x`）**が割り当てられ、LAN上の他端末からは直接たどり着けません。

```
[スマホ/別PC]      [Windowsホスト]            [WSL2（NAT・内部）]
192.168.10.x  ──→  192.168.10.8(LAN IP)  ──NAT──  172.24.x.x:80  → アプリ
   見えない …………………………………………────╳
```

WSL内で確認すると、LANの `192.168.x.x` ではなく `172.x` が見えます。

```
$ hostname -I
172.24.193.86
$ ip -4 -o addr show | grep eth
... eth0  172.24.193.86/20
```

この `172.x` は Windows の内側だけの住所なので、LAN の他端末からは届きません。

---

## 14-2. 2つの解決策

| 方法 | 概要 | 長所 | 短所 |
| --- | --- | --- | --- |
| **ミラーモード**（本章） | WSLをホストと同じネットワークに載せる | ポート転送不要・IPが安定・設定が少ない | **Windows 11 22H2以降**が必要・一度WSL再起動 |
| ポート転送（付録） | Windowsで `netsh portproxy` + ファイアウォール | 古いWindowsでも可・WSL再起動不要 | WSLのIPが再起動で変わるため再設定が要る |

本章は **ミラーモード**で進めます（使えない場合は末尾の付録を参照）。

---

## 14-3. 【準備1】Windows の LAN IP を調べ、許可リストに追加する

まず公開に使う **WindowsホストのLAN IP** を調べます。WSL から Windows のコマンドを呼べます。

```
$ ipconfig.exe | grep -A4 -iE "Wi-Fi|Ethernet" | grep IPv4
   IPv4 アドレス . . . . . . . . . . . .: 192.168.10.8     ← これがLAN IP
   IPv4 アドレス . . . . . . . . . . . .: 172.26.96.1      ← 仮想アダプタ（無視）
```

> ⚠️ `172.x`・`10.x`（WSL/Hyper-V用）は仮想アダプタなので無視。**`192.168.x.x` のような家庭/社内LANのアドレス**を選びます。

`DEBUG=False` では `ALLOWED_HOSTS` に無いホストは拒否されます。このLAN IPを許可に追加します。12・13章と同じく **systemd の drop-in** で（元のユニットは触らず上書き）。

```
$ printf '%s\n' '[Service]' 'Environment=DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,192.168.10.8' \
    | sudo tee /etc/systemd/system/shiftmanager.service.d/lan.conf >/dev/null
$ sudo systemctl daemon-reload
$ sudo systemctl restart shiftmanager
```

確認（秘密値を出さずに該当項目だけ）:

```
$ systemctl show shiftmanager -p Environment | tr ' ' '\n' | grep '^DJANGO_ALLOWED_HOSTS='
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,192.168.10.8
```

---

## 14-4. 【準備2】ミラーモードを有効化する（.wslconfig）

Windows ユーザーのホームに `.wslconfig` を作り、ネットワークをミラーに切り替えます。WSL からは `/mnt/c/Users/<Windowsユーザー>/.wslconfig` として編集できます。

ファイル: `C:\Users\<Windowsユーザー>\.wslconfig`

```ini
[wsl2]
# WSLをホストと同じネットワークに載せる（LANの他端末から到達可能に）
networkingMode=mirrored
```

> 🔰 既に `.wslconfig` がある場合は `[wsl2]` セクションに `networkingMode=mirrored` の行を足します。

---

## 14-5. WSL を再起動して反映する

`.wslconfig` の変更は **WSLの再起動**で反映されます。

> ⚠️ `wsl --shutdown` は **Windows側の PowerShell かコマンドプロンプト**で実行します（WSLの中ではありません）。WSLのセッションは一旦終了します（systemd の `shiftmanager`・`mysql` は再起動後に自動で立ち上がります）。

```
PS> wsl --shutdown
```

10秒ほど待ってから、WSL（Ubuntu）のターミナルを開き直します。

---

## 14-6. 反映を確認する

ミラーモードが効くと、WSL に **ホストと同じ LAN IP** が付きます。

```
$ hostname -I
192.168.10.8                      ← 172.x ではなく LAN IP になった
$ ip -4 -o addr show | grep -v 127.0.0.1
... eth1  192.168.10.8/24

$ systemctl is-active shiftmanager mysql
active
active

$ curl -s -o /dev/null -w "%{http_code}\n" http://192.168.10.8/login/
200                               ← LAN IP宛で応答する
```

ここまでで「WSL内・ホスト内」からは LAN IP で見えています。あとは外（他端末）からの受信を Windows のファイアウォールで許可します。

---

## 14-7. Windows ファイアウォールで受信を許可する

ミラーモードでは **Windows のファイアウォール規則が WSL にも適用**されます。ポート80の受信を許可します。

**管理者権限の PowerShell**（PowerShellを右クリック →「管理者として実行」）で:

```
PS> New-NetFirewallRule -DisplayName "WSL ShiftManager HTTP 80" `
      -Direction Inbound -Action Allow -Protocol TCP -LocalPort 80 -Profile Private
```

- `-Profile Private`: 家庭/社内ネットワーク向け。公共ネット（Public）には開けない安全側の設定。

---

## 14-8. 他の端末からアクセスする

同じ Wi-Fi/LAN につないだ **スマホや別PC**のブラウザで開きます。

```
http://192.168.10.8/
```

ログイン画面が出れば成功です。LAN内の誰でも（IDとパスワードを持つ人が）シフト提出にアクセスできます。

> ⚠️ **これは「LAN内」への公開**です。インターネットからのアクセスや、パスワードを安全に送るための **HTTPS化** はまだです。外部公開する場合は HTTPS が必須級です（[終章](終章_全体のまとめ.md) の発展編、12-9参照）。

---

## つまずきポイント

- **他端末から開けない** → ①ファイアウォール規則を入れたか ②ネットワークが「パブリック」に分類されていないか。Publicの場合は規則を `-Profile Private,Public` にするか、Windowsのネットワーク設定で接続を「プライベート」に変更（学内/社内ネットは管理ポリシーに従う）。
- **`400 Bad Request` になる** → `ALLOWED_HOSTS` にアクセスに使ったIP/ホスト名が入っていない（14-3）。
- **再起動したらアクセスできない** → ルーターのDHCPでLAN IPが変わった可能性。`ipconfig.exe` で再確認し、変わっていれば `ALLOWED_HOSTS` を更新。**ルーターでIP固定（DHCP予約）**しておくと安定します。
- **ミラーモードにならない（`hostname -I` が `172.x` のまま）** → Windowsが 11 22H2 未満。下の付録（ポート転送）を使う。
- **`localhost` で開けなくなった** → ミラーモードでも `http://localhost/`・`http://127.0.0.1/` は引き続き使えます。

---

## 付録: ポート転送方式（ミラーモードが使えない場合）

Windows 10 や古い Windows 11 では、NAT のまま **ポート転送**で公開します。

```
# 1) WSL の現在のIPを調べる（WSL内）
$ hostname -I
172.24.193.86

# 2) 管理者PowerShellで、ホストの80番をWSLの80番へ転送
PS> netsh interface portproxy add v4tov4 listenport=80 listenaddress=0.0.0.0 connectport=80 connectaddress=172.24.193.86
PS> New-NetFirewallRule -DisplayName "WSL ShiftManager HTTP 80" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 80 -Profile Private
```

そして `ALLOWED_HOSTS` に **WindowsのLAN IP**（`192.168.x.x`）を追加（14-3と同じ）。

> ⚠️ NATの **WSL IP（`172.x`）は再起動のたびに変わります**。変わったら `netsh interface portproxy reset` してから再登録が必要です（起動時に自動設定するスクリプトを組む手もあります）。この煩雑さが無いのがミラーモードの利点です。

---

## この章のまとめ

- WSL2 が既定では NAT で、LAN から直接見えない理由を理解した。
- **ミラーモード**（`.wslconfig`）でWSLをホストと同じLANに載せ、`ALLOWED_HOSTS`に LAN IP を追加、Windowsファイアウォールで80番を許可して、他端末から開けるようにした。
- これは **LAN内公開**であり、インターネット公開には HTTPS 化が必要、という次の課題も確認した。

➡️ [終章 全体のまとめ](終章_全体のまとめ.md)
