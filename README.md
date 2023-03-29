# rtspserver-ffmpeg
Build an ffmpeg RTSP distribution server using an old alpine:3.8 Docker Image.

## 0. 前準備
- `git clone`
    ```bash
    git clone https://github.com/PINTO0309/rtspserver-ffmpeg.git && cd rtspserver-ffmpeg
    ```
- `xxxx.mp4` ファイルを `rtspserver-ffmpeg` フォルダの直下にコピーしておく

## 1. `docker compose` パターン
- `docker compose` 経由でコンテナを起動
    ```bash
    docker compose up -d
    ```
- `docker compose` 経由でコンテナを起動したあとに `docker compose exec` コマンドを使用して `ffmpeg` によるRTSP配信開始指示、`-stream_loop -1` は無限ループ再生オプション
    ```bash
    docker compose exec rtspserver-ffmpeg \
    ffmpeg -re -stream_loop -1 -i xxxx.mp4 http://localhost:8090/feed.ffm
    ```
- `docker compose` 経由でコンテナを起動したあとに配信用コンテナを終了
    ```bash
    docker compose down
    ```

## 2. `docker run` パターン
- `docker build` で Docker Image をローカルに生成 (Docker HubからPullするだけで問題ない場合は実施不要)
    ```bash
    docker build -t pinto0309/rtspserver-ffmpeg:latest -f Dockerfile.ffmpegrtsp .
    docker push pinto0309/rtspserver-ffmpeg:latest
    ```
- `docker run` 経由でデーモンとしてコンテナをバックエンド起動
    ```bash
    docker run --rm -d \
    -p 8554:8554 \
    -p 8090:8090 \
    -v ${PWD}/ffserver.conf:/etc/ffserver.conf \
    -v ${PWD}:/home/user/ \
    --net=host \
    --name rtspserver-ffmpeg \
    pinto0309/rtspserver-ffmpeg:latest
    ```
- `docker run` 経由でコンテナを起動したあとに `docker exec` コマンドを使用して `ffmpeg` によるRTSP配信開始指示、`-stream_loop -1` は無限ループ再生オプション
    ```bash
    docker exec rtspserver-ffmpeg \
    ffmpeg -re -stream_loop -1 -i xxxx.mp4 http://localhost:8090/feed.ffm
    ```
- `docker run` 経由でコンテナを起動したあとに配信用コンテナを終了
    ```bash
    docker stop rtspserver-ffmpeg
    ```